"""Check repository import rules that are stricter than the base linters."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON_DIRS = ("deeptutor", "deeptutor_cli", "scripts", "tests")
WEB_DIR = ROOT / "web"
WEB_APP_DIRS = ("app", "components", "context", "features", "hooks", "lib")
WEB_SUFFIXES = {".ts", ".tsx"}
_LOCAL_SCOPE_NODES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _iter_python_files() -> list[Path]:
    files: list[Path] = []
    for directory in PYTHON_DIRS:
        files.extend((ROOT / directory).rglob("*.py"))
    return sorted(p for p in files if "__pycache__" not in p.parts)


def _iter_web_app_files() -> list[Path]:
    files: list[Path] = []
    for directory in WEB_APP_DIRS:
        files.extend((WEB_DIR / directory).rglob("*"))
    return sorted(
        p
        for p in files
        if p.is_file()
        and p.suffix in WEB_SUFFIXES
        and "node_modules" not in p.parts
        and ".next" not in p.parts
    )


def _check_python_file(path: Path) -> list[str]:
    errors: list[str] = []
    text = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError as exc:
        return [f"{_rel(path)}:{exc.lineno}: syntax error prevents import check"]

    stack: list[tuple[ast.AST, list[ast.AST]]] = [(tree, [])]
    while stack:
        node, local_scopes = stack.pop()
        if isinstance(node, ast.ImportFrom) and node.names:
            if any(alias.name == "*" for alias in node.names):
                errors.append(f"{_rel(path)}:{node.lineno}: wildcard import is not allowed")
        if isinstance(node, (ast.Import, ast.ImportFrom)) and local_scopes:
            errors.append(f"{_rel(path)}:{node.lineno}: import statement inside function/class")

        next_scopes = (
            [*local_scopes, node] if isinstance(node, _LOCAL_SCOPE_NODES) else local_scopes
        )
        for child in ast.iter_child_nodes(node):
            stack.append((child, next_scopes))
    return errors


def _check_python() -> list[str]:
    errors: list[str] = []
    for path in _iter_python_files():
        errors.extend(_check_python_file(path))
    return errors


def _check_web() -> list[str]:
    errors: list[str] = []
    for path in _iter_web_app_files():
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if not stripped.startswith("import"):
                continue
            if ' from "../' in stripped or " from '../" in stripped:
                errors.append(f"{_rel(path)}:{lineno}: use @/ for cross-directory imports")
    return errors


def main() -> int:
    errors = [*_check_python(), *_check_web()]
    if errors:
        print("\n".join(errors))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
