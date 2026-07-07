# Security Standard

## Scope

Use this when changing auth, user isolation, grants, sessions, tools, provider
keys, uploads, artifacts, filesystem paths, external network access, logging,
or untrusted input.

## Core Rules

- `User` is the identity subject; session/workspace/resource access must be
  authorized through current authenticated context and grants.
- Do not trust client-provided identity, role, ownership, session scope, quota,
  grant, price, or permission fields.
- Keep admin-only behavior guarded on both backend and frontend. Frontend
  hiding is not authorization.
- Keep user data under the correct `data/user`, `data/users/<uid>`, or
  `data/system` path boundary.
- Normal users must not access admin model keys, other users' sessions,
  attachments, knowledge bases, grants, audit logs, or workspace files.

## Secrets

- Do not hardcode or commit real provider keys, tokens, cookies, passwords, or
  private IDs.
- Do not log provider API keys, auth headers, cookies, session tokens, raw
  model payloads, or uploaded contents.
- Treat `data/user/settings/model_catalog.json` and backups as secret-bearing.
- Sample env files must use fake values.

## Uploads, Paths, And Downloads

- Normalize and constrain filesystem paths.
- Prevent path traversal and symlink escape.
- Do not trust original filenames or client-provided content types alone.
- Enforce size/type limits before parsing or persistence.
- Attachment downloads must verify session ownership before serving files.

## Server-Side Network

- Server-side tools and fetchers must not blindly fetch arbitrary user URLs.
- Check protocol, host, redirects, private network access, timeout, and response
  size where the tool boundary supports it.

## Review Checklist

- Is the authorization check on the backend path that performs the action?
- Are grants and user workspace paths enforced?
- Are secrets redacted from logs, events, responses, and docs?
- Are uploads and file paths constrained?
- Are security-critical paths covered by tests?
