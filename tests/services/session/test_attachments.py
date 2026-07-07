"""Tests for session attachment preparation."""

from __future__ import annotations

import base64
import logging

import pytest

from deeptutor.services.session import attachments


class FakeAttachmentStore:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def put(
        self,
        *,
        session_id: str,
        attachment_id: str,
        filename: str,
        data: bytes,
        mime_type: str = "",
    ) -> str:
        self.calls.append(
            {
                "session_id": session_id,
                "attachment_id": attachment_id,
                "filename": filename,
                "data": data,
                "mime_type": mime_type,
            }
        )
        return f"/api/attachments/{session_id}/{attachment_id}/{filename}"


@pytest.mark.asyncio
async def test_prepare_attachments_uploads_and_strips_persisted_base64(monkeypatch) -> None:
    store = FakeAttachmentStore()
    monkeypatch.setattr(attachments, "get_attachment_store", lambda: store)

    def fake_extract(records):
        records[0]["extracted_text"] = "hello"
        return ["[File: note.txt]\nhello"], records

    monkeypatch.setattr(attachments, "extract_documents_from_records", fake_extract)

    prepared = await attachments.prepare_attachments(
        session_id="s1",
        raw_items=[
            {
                "type": "file",
                "filename": "note.txt",
                "mime_type": "text/plain",
                "base64": base64.b64encode(b"hello").decode("ascii"),
                "id": "a1",
            }
        ],
        logger=logging.getLogger(__name__),
    )

    assert store.calls == [
        {
            "session_id": "s1",
            "attachment_id": "a1",
            "filename": "note.txt",
            "data": b"hello",
            "mime_type": "text/plain",
        }
    ]
    assert prepared.document_texts == ["[File: note.txt]\nhello"]
    assert prepared.records[0]["url"] == "/api/attachments/s1/a1/note.txt"
    assert prepared.context[0].url == "/api/attachments/s1/a1/note.txt"
    assert prepared.context[0].extracted_text == "hello"
    assert prepared.persisted[0]["base64"] == ""
