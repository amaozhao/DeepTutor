# Testing Standard

## Scope

Use this when adding or changing tests, fixtures, mocks, test data, optional
dependency handling, or verification commands.

## Layout

- Python tests live under `tests/` and `deeptutor/learning/tests`.
- Frontend tests live under `web/tests/` or existing web test locations.
- New Python tests must mirror the owning package path by default, for example
  `deeptutor/services/session/...` -> `tests/services/session/...`.
- Existing behavior-domain folders may stay in place, but do not add new tests
  there for a newly split module unless the test genuinely spans multiple
  packages. If a mirrored test is impractical, state the reason in the test
  module docstring or the review summary.
- When moving behavior out of a large module, add or move focused tests beside
  the new module's mirrored path in the same change.

## Core Rules

- Add the narrowest regression test that would have failed before a bug fix.
- Test the boundary that owns the invariant.
- Keep tests deterministic and isolated.
- Do not hide failures with broad `try` blocks, arbitrary sleeps, broad mocks,
  or snapshots that do not assert behavior.
- Mock unstable external boundaries: network, provider SDKs, clocks, databases,
  browser APIs. Avoid mocking internal calls just to prove call order.
- Use `pytest.importorskip()` for tests that require optional extras such as
  partner SDKs or LlamaIndex packages.
- Test data must not include real credentials, tokens, personal data, or
  provider keys.

## Async Tests

- Use the repository's pytest-asyncio configuration.
- Prefer explicit awaits, fake clocks, deterministic synchronization, or
  bounded polling helpers.
- Clean up tasks, streams, temporary workspaces, and stores.

## Verification

Run the narrowest useful command first, then broaden when shared behavior
changed.

```bash
pytest -q tests/path/to/test_file.py
pytest -q
ruff check .
ruff format --check .
```

For frontend changes:

```bash
cd web && npm run lint
cd web && npm run test:node
```

## Review Checklist

- Would the regression test fail before the fix?
- Are optional dependencies skipped only for provider-specific assertions?
- Are mocks at external boundaries?
- Are async operations awaited deterministically?
- Was the claimed verification actually run and read?
