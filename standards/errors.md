# Error Standard

## Scope

Use this when changing exceptions, API error responses, stream error events,
fallbacks, retries, provider failures, tool failures, or error tests.

## Core Rules

- Expected failures should become safe, actionable errors at the boundary.
- Unexpected failures must not be converted into success.
- Keep protected blocks narrow and catch specific errors.
- Preserve causes with `raise ... from exc` when translating exceptions.
- Do not log or expose secrets, raw provider payloads, full local paths, or
  stack traces to users.
- Tool errors can be returned as `ToolResult(success=False)` only when the LLM
  can safely continue with that failure as information.

## Expected Failures

Examples:

- auth missing, disabled user, token version mismatch;
- access denied for session, model, tool, knowledge base, partner, or file;
- invalid user input or unsupported upload type;
- provider timeout, rate limit, or empty model response;
- optional dependency not installed for an optional feature;
- quota exhausted or rate limit exceeded.

Expected failures should be tested and should not produce noisy tracebacks in
normal operation.

## Unexpected Failures

Examples:

- impossible internal state;
- malformed persisted data that should have been validated;
- missing required config after startup validation;
- programmer errors and failed invariants.

Let these fail visibly at the appropriate host boundary. Do not return empty
lists, default objects, or "ok" responses after unexpected errors.

## Fallbacks And Retries

- Retries belong at the boundary that owns the external call.
- Every retry needs a limit, timeout behavior, and cancellation awareness.
- Fallbacks are allowed only when the contract says degraded behavior is safe.
- A fallback must make clear what users/callers observe.

## Review Checklist

- Is each caught error specific?
- Does the fallback preserve correctness and user isolation?
- Are causes preserved when errors are translated?
- Are sensitive details excluded from API responses, events, and logs?
- Do tests prove expected error behavior?
