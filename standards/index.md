# Engineering Standards Index

These standards are DeepTutor-specific companion rules for `AGENTS.md`. They
are not a separate product spec and should stay shorter than the code they
govern.

## Use Model

1. Read `AGENTS.md` first.
2. Identify the area touched by the task.
3. Read only the matching standard files.
4. Prefer current code and tests over stale prose when they disagree.
5. Report only checks that were actually run.

## Selection Guide

| Task touches | Read |
| --- | --- |
| Package boundaries, runtime orchestration, tools, capabilities, services, registries | `modules.md` |
| Stream events, context payloads, tool/capability interfaces, API/CLI/WebSocket contracts | `contracts.md` |
| Python typing, dataclasses, schemas, untrusted payloads | `typing.md` |
| Exceptions, error responses, fallbacks, retries, logging failures | `errors.md` |
| Tests, fixtures, mocks, optional dependency skips, verification commands | `testing.md` |
| Auth, user isolation, secrets, uploads, paths, SSRF, sensitive logging | `security.md` |
| Dependencies, extras, env vars, runtime settings, packaging, background work | `operations.md` |
| Async execution, streaming, sessions, locks, caching, payload size | `performance.md` |
| Final self-review, requested code review, verification reporting | `review.md` |

## File Map

- `modules.md`: where behavior belongs and which boundaries own invariants.
- `contracts.md`: stable protocol and API shapes.
- `typing.md`: practical typing rules for current Python code.
- `errors.md`: expected vs unexpected failure handling.
- `testing.md`: focused regression and optional-extra test rules.
- `security.md`: multi-user safety, secrets, uploads, and logs.
- `operations.md`: dependency, config, packaging, and background work rules.
- `performance.md`: bounded async, streaming, and storage behavior.
- `review.md`: diff review and completion reporting.

## Maintenance Rules

- Keep standards actionable and repository-specific.
- Delete rules copied from unrelated project templates.
- Do not put one-off product requirements, SaaS milestones, runbooks, or
  historical decisions here; put those under `docs/`.
- Do not add a new standards file until an existing one is clearly too broad.
