"""Attachment preparation for session turns."""

from __future__ import annotations

import base64
from dataclasses import dataclass
import logging
from typing import Any
import uuid

from deeptutor.core.context import Attachment
from deeptutor.services.storage import get_attachment_store
from deeptutor.utils.document_extractor import extract_documents_from_records


@dataclass
class PreparedAttachments:
    context: list[Attachment]
    records: list[dict[str, Any]]
    persisted: list[dict[str, Any]]
    document_texts: list[str]


async def prepare_attachments(
    *,
    session_id: str,
    raw_items: list[dict[str, Any]],
    logger: logging.Logger,
) -> PreparedAttachments:
    records = [_attachment_record(item) for item in raw_items if isinstance(item, dict)]
    await _store_uploaded_bytes(session_id=session_id, records=records, logger=logger)

    document_texts, records = extract_documents_from_records(records)
    context = [
        Attachment(
            type=record.get("type", "file"),
            url=record.get("url", ""),
            base64=record.get("base64", ""),
            filename=record.get("filename", ""),
            mime_type=record.get("mime_type", ""),
            id=record.get("id", ""),
            extracted_text=record.get("extracted_text", ""),
        )
        for record in records
    ]
    persisted = [
        {**{key: value for key, value in record.items() if key != "base64"}, "base64": ""}
        for record in records
    ]
    return PreparedAttachments(
        context=context,
        records=records,
        persisted=persisted,
        document_texts=document_texts,
    )


def _attachment_record(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": item.get("type", "file"),
        "url": item.get("url", ""),
        "base64": item.get("base64", ""),
        "filename": item.get("filename", ""),
        "mime_type": item.get("mime_type", ""),
        "id": item.get("id", "") or uuid.uuid4().hex[:12],
    }


async def _store_uploaded_bytes(
    *,
    session_id: str,
    records: list[dict[str, Any]],
    logger: logging.Logger,
) -> None:
    attachment_store = get_attachment_store()
    for record in records:
        if record.get("url"):
            continue
        encoded = record.get("base64") or ""
        if not encoded:
            continue
        try:
            raw_bytes = base64.b64decode(encoded, validate=False)
        except Exception as exc:
            logger.warning(
                "skipping attachment upload for %r: invalid base64 (%s)",
                record.get("filename"),
                exc,
            )
            continue
        try:
            record["url"] = await attachment_store.put(
                session_id=session_id,
                attachment_id=record["id"],
                filename=record.get("filename", "") or "file",
                data=raw_bytes,
                mime_type=record.get("mime_type", "") or "",
            )
        except Exception as exc:
            logger.warning(
                "attachment store rejected %r: %s",
                record.get("filename"),
                exc,
            )
