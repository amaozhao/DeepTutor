# DeepTutor Agent Instructions

These instructions apply to the whole repository unless a deeper `AGENTS.md`
overrides them for files under its directory.

## General

- Do not commit or push changes unless the user explicitly asks for it in the
  current task.
- For non-trivial code or documentation changes, read the relevant companion
  rule in `standards/` after this file; use `standards/index.md` to choose the
  smallest applicable file.
- Keep changes small, reviewable, and scoped to the user's request.
- Prefer existing project patterns over new abstractions.
- Inspect existing implementation, configuration, tests, and public contracts
  before changing architecture, dependencies, test layout, build tooling, or
  API behavior.
- Do not edit generated, vendored, cache, runtime, log, build, coverage, or
  dependency output unless the task explicitly targets it. Local runtime
  settings under `data/user/settings/*.json` are editable only for explicit
  configuration tasks.
- Avoid unrelated formatting churn. Format only files affected by the task
  unless the user asks for broader cleanup.
- Keep specifications, tests, implementation, and documentation consistent.
- When fixing a bug, identify the owning invariant and root cause first. Do not
  hide the failure behind broad fallback logic.

## Naming

- For new project-owned files and directories, prefer lowercase ASCII single
  words.
- Do not create fake compound words such as `loaddata`, `runagent`,
  `fetchreport`, or verb-plus-noun concatenations.
- Avoid new multiword names joined by hyphen, underscore, camelCase, or
  PascalCase unless an existing repo convention or external ecosystem requires
  it.
- Python ecosystem and framework-required filenames are allowed, for example
  `__init__.py`, `pyproject.toml`, pytest `test_*.py`, Next.js route files, and
  generated metadata.
- Existing files are exempt unless the task explicitly renames them. Do not
  rename files opportunistically.
- If a concept needs several words, place code in an existing appropriate
  single-word package or directory and use clear symbol names inside the file.

## Architecture Rules

- Keep entry points thin. Put runtime rules, storage details, external SDK
  details, transport bindings, and cache keys behind project-owned boundaries.
- Prefer deep modules that own real invariants and expose small typed
  interfaces.
- Avoid shallow wrappers that only rename, forward, re-export, or add
  indirection without owning a policy, invariant, type boundary, or useful
  abstraction.
- Public APIs should express domain operations and invariants, not
  implementation steps.
- Do not add layers, factories, registries, event buses, or plugin systems
  unless the task or existing project pattern justifies them.
- Deep modules are not god modules. Split code when responsibilities,
  dependencies, reasons to change, or test setup become unrelated.

## Python And Web

- Python application code lives under `deeptutor/`; CLI code lives under
  `deeptutor_cli/`; web UI code lives under `web/`; tests live under `tests/`
  and `web/tests/`.
- Python imports should be at module top, after the module docstring and
  `from __future__` imports. Function-local imports are acceptable for optional
  dependencies, documented cycles, or cold-path performance.
- Use existing config loaders and runtime settings. Project-root `.env` files
  are intentionally ignored by the app unless a task changes that contract.
- Type hints must describe real values. Do not silence type issues with
  incorrect annotations, unnecessary casts, or broad `Any`.
- Prefer dataclasses, typed dicts, protocols, literal types, or narrow
  dictionaries over unstructured payloads after boundary validation.
- Use async all the way through paths that are already asynchronous. Do not
  call blocking I/O, `time.sleep()`, or `asyncio.run()` from async runtime code.
- Do not leave fire-and-forget tasks unmanaged. Agent loops, streams, tool
  calls, partner channel tasks, and adapter tasks need ownership, error
  logging, cancellation behavior, and cleanup.
- Optional provider or channel dependencies must stay optional. Isolate them
  behind extras, guarded imports, or `pytest.importorskip()` in provider-specific
  tests.

## Error Handling

- Do not add `try` blocks merely to make a bug disappear.
- Keep each `try` block as narrow as possible and catch the most specific error
  type available.
- Do not use bare `except`, catch `BaseException`, use empty handlers, or
  silently ignore errors.
- Avoid broad `except Exception` unless it is at an adapter or host-application
  boundary and returns or raises a structured error.
- Do not return `None`, an empty collection, a default object, or a success
  response after an unexpected error unless that fallback is an explicit
  documented contract.
- Preserve causes when translating errors, for example `raise NewError(...) from
  exc` in Python.
- Tests must not hide assertion failures inside `try` blocks. Use
  `pytest.raises`.

## Configuration, Dependencies, Security

- Do not hardcode secrets, tokens, passwords, private keys, account IDs, or
  environment-specific credentials.
- Keep `.env.example` and sample environment files free of real secrets.
- Do not add a runtime dependency when the standard library, existing
  dependency, or small local helper is sufficient.
- When a dependency change is necessary, update the appropriate metadata and
  report why the dependency was needed.
- Enforce authentication and authorization before protected runtime resources
  are accessed.
- Do not trust client-provided identity, role, ownership, session scope, price,
  status, or permission fields.
- Validate and normalize external input before persistence or sensitive
  operations.
- Do not log secrets, credentials, session tokens, authorization headers,
  personal data, or large request bodies.
- Avoid SQL injection, command injection, path traversal, SSRF, XSS, open
  redirects, and unsafe deserialization.

## Tests And Verification

- Bug fixes should include the narrowest test that would have failed before the
  fix.
- Run the narrowest useful verification first, then broaden when shared
  behavior changes.
- Python checks commonly used in this repository:

```bash
ruff format --check .
ruff check .
pytest -q
```

- Frontend checks, when touching `web/`:

```bash
cd web && npm run lint
```

- Do not claim a tool, test, type check, or build passed unless it was actually
  run and the output was checked.

## Documentation And Specs

- Keep specifications consistent with the current implementation baseline.
- Mark future phases clearly as future work.
- Do not mix first-phase requirements with later-phase ambitions in the same
  acceptance criteria.
- Update relevant README, API notes, environment examples, or developer docs
  when behavior, setup, commands, or contracts change.

## Completion Expectations

- Before reporting completion, check the relevant git diff and verify no
  unrelated files were changed.
- Report what changed, what was verified, and any verification intentionally
  skipped.
- Mention known risks, follow-up work, or repository assumptions when they
  affect the result.

## DeepTutor Architecture

## Overview

DeepTutor is an **agent-native** intelligent learning companion organized
around a two-layer plugin model — single-shot **Tools** invoked by the
LLM, and multi-stage **Capabilities** that take over a turn — exposed
through three entry points: CLI, WebSocket API, and Python SDK.

## Architecture

```
Entry Points:  CLI (Typer)  |  WebSocket /api/v1/ws  |  Python SDK
                    ↓                   ↓                   ↓
              ┌─────────────────────────────────────────────────┐
              │              ChatOrchestrator                    │
              │   routes UnifiedContext → selected Capability    │
              │   (defaults to `chat`)                           │
              └──────────┬──────────────┬───────────────────────┘
                         │              │
              ┌──────────▼──┐  ┌────────▼──────────┐
              │ ToolRegistry │  │ CapabilityRegistry │
              │  (Level 1)   │  │   (Level 2)        │
              └──────────────┘  └────────────────────┘
```

All capabilities emit on a shared `StreamBus`; the orchestrator fans
events out to consumers. Runtime settings live in
`data/user/settings/*.json` — project-root `.env` files are intentionally
ignored.

### Level 1 — Tools

Single-function tools the LLM picks on demand. Four user-toggleable tools
surface in `/settings/tools`:

| Tool           | Description                                   |
| -------------- | --------------------------------------------- |
| `brainstorm`   | Breadth-first idea exploration with rationale |
| `web_search`   | Web search with citations                     |
| `paper_search` | arXiv preprint search                         |
| `reason`       | Dedicated deep-reasoning LLM call             |

The rest are **context-gated**: the chat capability auto-mounts them from
`ToolMountFlags` (presence of a KB, attachments, sandbox availability, …), and
any of them can also be force-enabled via `--tool`. Auto-mounted set: `rag`,
`read_source`, `read_memory`, `write_memory`, `read_skill`, `load_tools`,
`exec`, `code_execution` (sandboxed Python: NL intent → code → run),
`list_notebook`, `write_note`, `web_fetch`, `github`, `cron`,
`ask_user` (pauses the turn and resumes with the user's reply), plus the
mastery-path tools. `geogebra_analysis` is parked under
`COMING_SOON_TOOL_TYPES`.

### Level 2 — Capabilities

Multi-stage pipelines that own the turn:

| Capability       | Stages                                                |
| ---------------- | ----------------------------------------------------- |
| `chat`           | exploring → responding (single agentic loop, default) |
| `mastery_path`   | responding (Guided Learning — chat loop + mastery tools, gated per topic type) |
| `deep_solve`     | planning → reasoning → writing                        |
| `deep_question`  | ideation → generation                                 |
| `deep_research`  | rephrasing → decomposing → researching → reporting    |
| `visualize`      | analyzing → generating → reviewing (SVG / Chart.js / Mermaid / HTML; or routes to Manim sub-stages via `render_type`) |
| `math_animator`  | concept_analysis → concept_design → code_generation → code_retry → summary → render_output |

All capabilities converge on `emit_capability_result()` in
`deeptutor/capabilities/_shared.py` so every turn emits the same envelope
(response payload + `cost_summary` from `UsageTracker`). Status copy and
prompts are i18n'd via `capabilities/prompts/{en,zh}/<name>.yaml`.

## CLI Usage

```bash
# Install
pip install deeptutor      # Full app (CLI + Web/API + packaged Web assets)
pip install deeptutor-cli  # CLI-only

# Run any capability
deeptutor run chat "Explain Fourier transform"
deeptutor run deep_solve "Solve x^2=4" -t rag --kb my-kb
deeptutor run visualize "Animate sine wave" --config render_mode=manim_video

# Interactive REPL
deeptutor chat
# (inside the REPL: /regenerate or /retry re-runs the last user message)

# Partners (IM-connected companions)
deeptutor partner list

# Knowledge bases, memory, server
deeptutor kb list
deeptutor kb create my-kb --doc textbook.pdf
deeptutor memory show
deeptutor serve --port 8001       # API server only
deeptutor start                   # backend + frontend together
```

## Key Files

| Path                                       | Purpose                              |
| ------------------------------------------ | ------------------------------------ |
| `deeptutor/runtime/orchestrator.py`        | `ChatOrchestrator` — unified entry   |
| `deeptutor/runtime/launcher.py`            | Backend + frontend lifecycle / port discovery |
| `deeptutor/runtime/registry/`              | Tool + Capability registries         |
| `deeptutor/runtime/bootstrap/builtin_capabilities.py` | Built-in capability class paths |
| `deeptutor/services/config/runtime_settings.py` | JSON settings + process-env overrides |
| `deeptutor/core/stream.py`, `stream_bus.py` | StreamEvent protocol + async fan-out |
| `deeptutor/core/tool_protocol.py`          | `BaseTool` + `ToolDefinition`         |
| `deeptutor/core/capability_protocol.py`    | `BaseCapability` + `CapabilityManifest` |
| `deeptutor/core/context.py`                | `UnifiedContext` dataclass            |
| `deeptutor/tools/builtin/__init__.py`      | All built-in tool wrappers           |
| `deeptutor/capabilities/`                  | Built-in capability implementations  |
| `deeptutor/app.py`                         | `DeepTutorApp` — Python SDK facade    |
| `deeptutor_cli/main.py`                    | Typer CLI entry point                |
| `deeptutor/api/routers/unified_ws.py`      | Unified WebSocket endpoint           |

## Dependency Layers

Public install paths and source extras are defined in `pyproject.toml`.
Requirements files mirror the same dependency groups for Docker/CI installs.

```
pip install deeptutor      — Full app (CLI + Web/API + packaged Web assets)
pip install deeptutor-cli  — CLI-only (LLM + RAG + providers + document parsing)
pip install -e .           — Source install for development

Source extras (.[ extra ], defined in pyproject.toml):
.[cli]            — CLI-only dependency set
.[server]         — Web/API server dependencies
.[partners]       — Partner channel SDKs + MCP client  (legacy alias: .[tutorbot])
.[matrix]         — Matrix channel for Partners (matrix-nio; needs libolm)
.[matrix-e2e]     — Matrix with end-to-end encryption (matrix-nio[e2e])
.[math-animator]  — Manim addon (powers `visualize` Manim renders + `deeptutor run math_animator`)
.[dev]            — Test / lint tooling
.[all]            — Everything above
```
