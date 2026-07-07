# Performance Standard

## Scope

Use this when changing async execution, session locks, turn concurrency,
streaming, context building, tool execution, provider calls, file parsing,
caching, payload size, or storage access.

## Core Rule

Do not optimize blindly, but do not introduce obvious latency, memory,
concurrency, or isolation regressions. Prefer the simplest bounded behavior
that preserves correctness.

## Async Runtime

- Do not block the event loop with sync sleeps, long CPU work, or unbounded file
  parsing.
- Do not call `asyncio.run()` from async runtime code.
- Bound parallel tool calls and external provider calls.
- Keep cancellation checks in long-running loops.
- Clean up tasks, streams, temp files, and workspaces.

## Session And Shared State

- Protect session writes and user/shared-state writes at the owning storage
  boundary.
- Do not use global locks for unrelated users when a narrower existing lock or
  database transaction can protect the invariant.
- In PostgreSQL shared_state mode, prefer short transactions and advisory locks
  only around the shared record being updated.
- Avoid hidden cross-user scans in request paths.

## Streaming And Payloads

- Keep `StreamEvent.metadata` bounded and safe.
- Store large artifacts separately and reference them instead of embedding huge
  payloads in events.
- Avoid replaying unbounded session history.
- Context summarization and truncation must preserve current-turn correctness
  over clever compression.

## External Calls And Caches

- External calls need timeout, cancellation behavior, and bounded retries when
  safe.
- Cache only when the key includes inputs that affect behavior: user/session,
  model/provider, settings, grant state, file version, or prompt/tool source.
- Invalidate caches on persisted data changes.

## Review Checklist

- Are async operations non-blocking and cancellable?
- Is concurrency bounded and user/session-isolated?
- Are event and API payloads bounded?
- Are file/provider/storage calls batched or cached where it matters?
- Did the change avoid unnecessary global serialization?
