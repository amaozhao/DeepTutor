# Module Standard

## Scope

Use this when changing package boundaries, runtime orchestration, tools,
capabilities, registries, session stores, config services, multi-user logic, or
shared domain models.

## Current Package Map

- `deeptutor/core/`: small protocol/data types such as `UnifiedContext`,
  `StreamEvent`, `BaseTool`, and `BaseCapability`.
- `deeptutor/runtime/`: orchestration, registries, startup/launcher logic.
- `deeptutor/capabilities/`: multi-stage turn owners.
- `deeptutor/tools/`: tool implementations and built-in wrappers.
- `deeptutor/services/`: LLM, RAG, session, config, parsing, search, partners,
  and other infrastructure-facing services.
- `deeptutor/api/`: FastAPI routers and HTTP/WebSocket boundaries.
- `deeptutor/multi_user/`: user identity, grants, paths, shared state, audit,
  and data-governance behavior.
- `deeptutor_cli/`: Typer CLI.
- `web/`: Next.js frontend.

## Core Rule

Put behavior where every caller naturally passes through it. A small fix at
the owning boundary is better than repeated guards in routers, pages, and tools.

## Boundary Rules

- Keep API routers thin: validate transport input, call services, return safe
  responses.
- Keep frontend pages/components out of backend policy decisions.
- Keep provider SDK details inside service/provider modules, not capabilities
  or routers.
- Keep multi-user authorization and path isolation in `deeptutor/multi_user/`
  and shared auth/security helpers.
- Keep capability orchestration in capabilities/runtime; tools should do one
  bounded job and return `ToolResult`.
- Do not add a registry/factory/plugin layer unless an existing registry
  pattern already covers the need or the task explicitly requires extension.
- Keep Python imports at module top unless the dependency is optional, the
  import breaks a real cycle, or the path is deliberately cold. Never use
  wildcard imports in project code.
- In `web/`, use `@/` for cross-directory imports. Relative imports are fine
  inside the same local folder and in tests.

## Invariant Owners

- Authentication and token validity: `deeptutor/services/auth.py` plus auth
  router/security dependencies.
- User workspace and system paths: `deeptutor/multi_user/paths.py`.
- Model/tool/knowledge grants: `deeptutor/multi_user/*_access.py` and grants.
- Shared auth/rate/quota/invite state: `deeptutor/multi_user/shared_state.py`
  and its callers.
- Session history and summarization: `deeptutor/services/session/`.
- Tool schemas/results: `deeptutor/core/tool_protocol.py` and built-in tools.
- Stream event shape: `deeptutor/core/stream.py`.

## Review Checklist

- Does the change live at the boundary that owns the invariant?
- Did it avoid duplicating checks across callers?
- Did it reuse existing services/helpers before adding new structure?
- Are API, CLI, WebSocket, and frontend callers still aligned?
- Are tests placed near the behavior they protect?
- Does `python scripts/imports.py` still pass?
