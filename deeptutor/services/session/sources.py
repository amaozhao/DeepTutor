"""Shared source-inventory data structures and rendering."""

from __future__ import annotations

from dataclasses import dataclass, field

# Per-source text-preview caps. Fresh sources get a meaningful preview so
# the model can answer simple "is this the right one?" questions without
# read_source. Historical sources surface only their identity — the model
# pays the read_source cost only when it actually needs them.
MANIFEST_PREVIEW_CHARS_FRESH = 2000


@dataclass(frozen=True)
class SourceEntry:
    """One row in the per-turn Attached Sources manifest."""

    sid: str
    kind: str
    name: str
    full_text: str
    fresh: bool
    first_seen_turn: int

    @property
    def char_count(self) -> int:
        return len(self.full_text)


@dataclass
class SourceInventory:
    """Ordered set of ``SourceEntry`` keyed by ``sid``."""

    entries: list[SourceEntry] = field(default_factory=list)
    _index: dict[str, int] = field(default_factory=dict, repr=False)

    def add(self, entry: SourceEntry) -> None:
        if not entry.sid:
            return
        if not entry.full_text.strip():
            return
        existing_pos = self._index.get(entry.sid)
        if existing_pos is None:
            self._index[entry.sid] = len(self.entries)
            self.entries.append(entry)
            return
        existing = self.entries[existing_pos]
        if entry.fresh and not existing.fresh:
            self.entries[existing_pos] = entry

    def is_empty(self) -> bool:
        return not self.entries

    def __contains__(self, sid: str) -> bool:
        return sid in self._index


def render_manifest(inv: SourceInventory) -> tuple[str, dict[str, str]]:
    """Render the inventory into (manifest_text, source_index)."""
    if inv.is_empty():
        return "", {}

    source_index: dict[str, str] = {sid: entry.full_text for sid, entry in _iter_sid_entries(inv)}
    rendered_rows = [_render_row(entry) for entry in inv.entries]

    header = (
        "[Attached Sources]\n"
        "An index of the sources the user has attached in this conversation. "
        "Rows with a `preview` field were attached **this turn**; rows marked "
        "`previously attached (turn N)` were uploaded in earlier turns and show "
        "only their identity. Their full text can be loaded on demand when a "
        "source is relevant. Refer to sources by name; never invent source ids."
    )
    return header + "\n\n" + "\n\n".join(rendered_rows), source_index


def _iter_sid_entries(inv: SourceInventory):
    seen: set[str] = set()
    for entry in inv.entries:
        if entry.sid in seen:
            continue
        seen.add(entry.sid)
        yield entry.sid, entry


def _clip_preview(text: str, limit: int = MANIFEST_PREVIEW_CHARS_FRESH) -> str:
    cleaned = (text or "").strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit].rstrip() + "…"


def _format_size(char_count: int) -> str:
    if char_count >= 1024:
        return f"~{round(char_count / 1024)} KB"
    return f"~{char_count} chars"


def _render_row(entry: SourceEntry) -> str:
    if entry.fresh:
        preview = _clip_preview(entry.full_text)
        return f"- id={entry.sid}  type={entry.kind}  name={entry.name!r}\n  preview: {preview!r}"
    return (
        f"- id={entry.sid}  type={entry.kind}  name={entry.name!r}"
        f"  size={_format_size(entry.char_count)}  "
        f"source: previously attached (turn {entry.first_seen_turn})"
    )


__all__ = [
    "MANIFEST_PREVIEW_CHARS_FRESH",
    "SourceEntry",
    "SourceInventory",
    "render_manifest",
]
