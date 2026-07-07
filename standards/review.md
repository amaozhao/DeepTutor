# Review Standard

## Scope

Use this for final self-review, requested code review, diff scope checks, and
verification reporting.

## Core Rule

Review the actual diff, verify relevant behavior, and report only what changed
and what was checked. Do not claim lint, type check, tests, build, or browser
verification passed unless the command was run and the output was read.

## Self-Review Checklist

### Scope

- No unrelated files changed.
- No generated, cache, runtime, build, coverage, or dependency output changed.
- No unrelated formatting churn.
- Deleted or renamed files are not still referenced.

### Correctness

- The changed boundary owns the invariant.
- API, CLI, WebSocket, frontend, and docs remain consistent where affected.
- Optional extras remain optional.
- Existing user data and settings remain backward-compatible.

### Security

- Auth and authorization are enforced on the backend.
- User workspace, session, grant, and attachment boundaries are preserved.
- Secrets and sensitive data are not logged or exposed.

### Tests

- A focused test covers bug fixes or changed behavior.
- Broader tests were run when shared behavior changed.
- Optional dependency skips do not hide non-optional behavior.

## Review Findings Format

For requested code reviews, findings come first and are ordered by severity:

- Critical: security, data loss, or build-breaking production risk.
- High: likely functional bug or broken public contract.
- Medium: maintainability, test, typing, or performance risk.
- Low: clarity or minor cleanup.

Each finding should include file/location, problem, impact, and recommended
fix. If there are no findings, say so and mention remaining verification gaps.

## Completion Report

Use this shape when useful:

```text
Changed:
- ...

Verified:
- ...

Skipped:
- ... because ...

Notes:
- ...
```

Keep it factual and short.
