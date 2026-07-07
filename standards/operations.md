# Operations Standard

## Scope

Use this when changing dependencies, extras, `pyproject.toml`, requirements,
environment variables, runtime settings, Docker/compose files, logging,
background work, packaging, or operational diagnostics.

## Dependencies

Use this order:

1. Python/Node standard library or platform feature.
2. Existing dependency.
3. Existing optional extra.
4. New dependency, only when it prevents more risk than it adds.

Rules:

- Keep optional infrastructure dependencies behind extras or guarded imports.
- Update `pyproject.toml`, matching `requirements/*.txt`, or `web/package.json`
  when dependencies change.
- Do not vendor generated dependency output.
- Do not edit `web/node_modules`, `.next`, caches, build output, or coverage
  output.

## Configuration

- Runtime settings live in `data/user/settings/*.json`.
- Project-root `.env` files are not the app's normal runtime configuration
  source; do not make them authoritative without an explicit task.
- Environment variables may override runtime settings only through existing
  config loaders.
- Validate config at startup or service boundaries.
- Keep sample values fake and document required production settings.

## Packaging And Deployment

- Source packages are `deeptutor*` and `deeptutor_cli*`.
- Packaged web assets live under `deeptutor_web` when built.
- Docker/compose changes must preserve the full `data/` tree unless the task is
  explicitly changing persistence.
- PostgreSQL shared_state deployments require backing up both `data/` and the
  configured database.

## Background Work

- Long-running agent loops, stream publishers, partner channels, schedulers,
  and tool calls need owned lifecycle, cancellation, logging, and cleanup.
- Do not create unmanaged fire-and-forget tasks.

## Review Checklist

- Are optional dependencies still optional?
- Are runtime settings and env overrides documented and validated?
- Does packaging still include prompts, skills, templates, and web assets?
- Are background tasks supervised and cancellable?
- Are operational docs updated when deployment behavior changes?
