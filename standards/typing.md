# Typing Standard

## Scope

Use this when changing Python type hints, dataclasses, protocols, schemas,
runtime settings, DTOs, tool/capability definitions, or untrusted payload
parsing.

## Core Rules

- Types must describe real runtime values.
- Keep `Any` at boundaries; narrow before using values for decisions, storage
  keys, paths, permissions, or side effects.
- Prefer dataclasses, `TypedDict`, `Protocol`, `Literal`, enums, or narrow
  dictionaries when a shape is stable.
- Do not create a `Protocol` for every class mechanically.
- Use `T | None` only when absence is a real state callers must handle.
- Avoid `cast()` and `# type: ignore`; if unavoidable, keep the scope tiny and
  explain the external limitation.

## DeepTutor Shapes

- Use dataclasses for small core payloads, matching existing
  `deeptutor/core/*_protocol.py` patterns.
- Use Pydantic where routers or existing settings models already use it.
- Keep provider-specific payloads behind provider/service modules.
- Treat request JSON, settings files, CSV imports, uploaded metadata, and tool
  arguments as untrusted until validated.

## Optional Dependencies

- Type optional provider/channel integrations without importing their SDK at
  module import time unless the dependency is required by that install extra.
- For optional imports, keep the guard close to the import and provide a clear
  error or skip path.

## Review Checklist

- Are public payloads explicitly typed?
- Is untrusted data narrowed before side effects?
- Are optional fields representing real states?
- Did the change avoid spreading `Any` through core runtime state?
- Did it avoid unsafe ignores and casts?
