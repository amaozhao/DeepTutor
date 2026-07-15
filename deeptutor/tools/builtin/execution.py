"""Code execution built-in tool wrappers."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import uuid

from deeptutor.core.tool_protocol import BaseTool, ToolDefinition, ToolParameter, ToolResult
from deeptutor.services import sandbox as sandbox_services
from deeptutor.services.path_service import get_path_service
from deeptutor.services.sandbox import (
    ExecRequest,
    Mount,
    ResourceLimits,
)
from deeptutor.services.sandbox.artifacts import (
    collect_public_artifacts,
    render_artifacts_for_tool,
)
from deeptutor.tools.builtin.common import _PromptHintsMixin


def _unique_run_token() -> str:
    """Short collision-resistant token for naming per-call code run dirs."""

    return uuid.uuid4().hex[:12]


class CodeExecutionTool(_PromptHintsMixin, BaseTool):
    """Compile and run a code snippet inside the execution sandbox.

    A typed front-end over the same sandbox ``exec`` uses: the model passes
    ready-to-run source as ``code`` + a ``language``; we write it into the
    turn's workspace, build the per-language compile/run command, and execute
    it through :mod:`deeptutor.services.sandbox`. No second LLM call, and the
    same OS-level isolation + quota as ``exec`` — so it inherits exec's gating
    (unavailable when no sandbox backend is configured).
    """

    # language -> (source filename, shell command template). ``{src}`` is the
    # source file, ``{bin}`` the compiled binary, ``{stdin}`` an optional
    # ``< file`` redirect (empty when no stdin is supplied). Commands run with
    # the workspace subdir as cwd, so plain relative names are enough.
    _LANGUAGES: dict[str, tuple[str, str]] = {
        "python": ("main.py", "python3 {src} {stdin}"),
        "c": ("main.c", "cc {src} -O2 -o prog && ./prog {stdin}"),
        "cpp": ("main.cpp", "c++ -std=c++17 -O2 {src} -o prog && ./prog {stdin}"),
    }
    _LANGUAGE_ALIASES: dict[str, str] = {
        "py": "python",
        "python3": "python",
        "c++": "cpp",
        "cxx": "cpp",
        "cc": "c",
    }

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="code_execution",
            description=(
                "Run a code snippet in an isolated sandbox and return its "
                "stdout/stderr. Pass complete, ready-to-run source in `code` "
                "and pick `language` (python, c, or cpp). Use for calculation, "
                "algorithm checking, and numerical verification — print results "
                "to stdout. Not a substitute for explaining your reasoning."
            ),
            parameters=[
                ToolParameter(
                    name="language",
                    type="string",
                    description="Source language: 'python', 'c', or 'cpp'.",
                ),
                ToolParameter(
                    name="code",
                    type="string",
                    description="The complete source code to compile/run.",
                ),
                ToolParameter(
                    name="stdin",
                    type="string",
                    description="Optional text piped to the program's stdin.",
                    required=False,
                ),
                ToolParameter(
                    name="timeout",
                    type="integer",
                    description="Max execution time in seconds (default 30, max 300).",
                    required=False,
                    default=30,
                ),
            ],
        )

    def _resolve_language(self, raw: Any) -> str:
        name = str(raw or "").strip().lower()
        name = self._LANGUAGE_ALIASES.get(name, name)
        if name not in self._LANGUAGES:
            supported = ", ".join(sorted(self._LANGUAGES))
            raise ValueError(f"Unsupported language {raw!r}; supported: {supported}.")
        return name

    async def execute(self, **kwargs: Any) -> ToolResult:
        code = str(kwargs.get("code") or "").strip()
        if not code:
            raise ValueError("code_execution requires non-empty 'code'.")
        language = self._resolve_language(kwargs.get("language"))
        source_name, command_template = self._LANGUAGES[language]

        try:
            timeout = int(kwargs.get("timeout") or 30)
        except (TypeError, ValueError):
            timeout = 30
        timeout = max(1, min(timeout, 300))

        # ``_sandbox_*`` kwargs are injected server-side by the pipeline; the
        # LLM never supplies them. Mirror ExecTool's contract.
        user_id = str(kwargs.get("_sandbox_user_id") or "anonymous")
        workdir = str(kwargs.get("_sandbox_workdir") or "").strip()
        mounts = tuple(kwargs.get("_sandbox_mounts") or ())
        if not workdir:
            # No pipeline workspace (e.g. direct/tool tests): fall back to the
            # detached code workspace the path service already manages.
            workdir = str(get_path_service().get_run_code_workspace_dir())
            mounts = (Mount(host_path=workdir, sandbox_path=workdir, read_only=False),)

        # Each call gets its own subdir so concurrent runs don't clobber one
        # another's source / binary. The subdir lives inside the mounted
        # workspace, so the sandbox sees it at the same path.
        run_dir = Path(workdir) / f"{language}_{_unique_run_token()}"
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / source_name).write_text(code, encoding="utf-8")

        stdin_redirect = ""
        if str(kwargs.get("stdin") or "") != "":
            (run_dir / "stdin.txt").write_text(str(kwargs["stdin"]), encoding="utf-8")
            stdin_redirect = "< stdin.txt"
        command = command_template.format(src=source_name, stdin=stdin_redirect).strip()

        limits = ResourceLimits(timeout_s=timeout)
        request = ExecRequest(
            command=command,
            workdir=str(run_dir),
            mounts=mounts,
            limits=limits,
        )
        result = await sandbox_services.get_sandbox_service().run(request, user_id=user_id)

        # The source file, compiled binary, and stdin scratch are inputs we
        # wrote ourselves — exclude them so only program-generated files
        # surface as artifacts.
        meta_files = {source_name, "prog", "stdin.txt"}
        artifacts = [
            artifact
            for artifact in collect_public_artifacts(str(run_dir))
            if artifact.filename not in meta_files
        ]
        artifact_rows = [artifact.to_dict() for artifact in artifacts]
        content_parts = [result.render(limits.max_output_chars)]
        artifact_text = render_artifacts_for_tool(artifacts)
        if artifact_text:
            content_parts.append(artifact_text)

        return ToolResult(
            content="\n\n".join(content_parts),
            success=result.ok and result.exit_code == 0,
            sources=[
                {
                    "type": "artifact",
                    "filename": row["filename"],
                    "url": row["url"],
                    "path": row["path"],
                    "mime_type": row["mime_type"],
                    "size_bytes": row["size_bytes"],
                }
                for row in artifact_rows
            ],
            metadata={
                "language": language,
                "code": code,
                "command": command,
                "exit_code": result.exit_code,
                "timed_out": result.timed_out,
                "sandbox_error": result.error,
                "run_dir": str(run_dir),
                "artifacts": artifact_rows,
            },
        )
