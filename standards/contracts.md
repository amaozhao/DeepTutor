# Contract Standard

## Scope

Use this when changing public protocol objects, API responses, WebSocket events,
CLI output that scripts may rely on, tool/capability interfaces, persisted JSON
settings, or frontend/backend DTOs.

## Stable DeepTutor Contracts

- `UnifiedContext` and `Attachment` in `deeptutor/core/context.py`.
- `StreamEvent` and `StreamEventType` in `deeptutor/core/stream.py`.
- `ToolDefinition`, `ToolParameter`, and `ToolResult` in
  `deeptutor/core/tool_protocol.py`.
- `CapabilityManifest` and `BaseCapability` in
  `deeptutor/core/capability_protocol.py`.
- Runtime settings under `data/user/settings/*.json`.
- User/grant/shared-state records under `deeptutor/multi_user/`.
- API routers under `deeptutor/api/routers/`.
- Frontend API clients under `web/lib/`.

## Rules

- Contract changes must update models, docs, tests, and affected callers
  together.
- Do not trust identity, role, ownership, quota, grant, or session values from
  request bodies; derive them from auth/session context.
- Keep wire/event fields backward-compatible when practical. When breaking a
  contract, update every caller in the same change.
- Do not expose provider SDK payloads, stack traces, full local paths, secrets,
  or raw database errors through API responses or stream metadata.
- Preserve `StreamEvent` fields unless all consumers are updated: `type`,
  `source`, `stage`, `content`, `metadata`, `session_id`, `turn_id`, `seq`,
  `timestamp`.
- Tool schemas must be valid JSON Schema for strict providers. Array parameters
  need `items`.
- Runtime settings files are product contracts. Add fields with safe defaults
  and migration-tolerant loaders.

## Tests

Cover contract changes at the boundary:

- API route tests for response/request shapes.
- WebSocket/session tests for stream event changes.
- Tool schema tests for provider-facing function definitions.
- Frontend client or node tests when `web/lib/` contracts change.

## Review Checklist

- Are backend and frontend shapes still synchronized?
- Are persisted settings backward-compatible?
- Are event/tool/capability fields safe and typed?
- Are sensitive implementation details excluded?
- Did contract tests change with the contract?
