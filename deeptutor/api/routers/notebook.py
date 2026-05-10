"""
Notebook API Router
Provides notebook creation, querying, updating, deletion, and record management functions
"""

import json
from typing import AsyncGenerator, Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from deeptutor.agents.notebook import NotebookSummarizeAgent
from deeptutor.multi_user.context import get_current_user
from deeptutor.multi_user.notebook_access import (
    list_visible_notebooks,
    resolve_notebook_for_read,
    resolve_notebook_for_write,
)
from deeptutor.services.llm import clean_thinking_tags
from deeptutor.services.notebook import notebook_manager

router = APIRouter()


# === Request/Response Models ===


class CreateNotebookRequest(BaseModel):
    """Create notebook request"""

    name: str
    description: str = ""
    color: str = "#3B82F6"
    icon: str = "book"


class UpdateNotebookRequest(BaseModel):
    """Update notebook request"""

    name: str | None = None
    description: str | None = None
    color: str | None = None
    icon: str | None = None


class AddRecordRequest(BaseModel):
    """Add record request"""

    notebook_ids: list[str]
    record_type: Literal["solve", "question", "research", "chat", "co_writer", "tutorbot"]
    title: str
    summary: str = ""
    user_query: str
    output: str
    metadata: dict = {}
    kb_name: str | None = None


class RemoveRecordRequest(BaseModel):
    """Remove record request"""

    record_id: str


class UpdateRecordRequest(BaseModel):
    """Update an existing notebook record."""

    title: str | None = None
    summary: str | None = None
    user_query: str | None = None
    output: str | None = None
    metadata: dict | None = None
    kb_name: str | None = None


# === API Endpoints ===


async def _build_record_summary(request: AddRecordRequest) -> str:
    if request.summary.strip():
        return clean_thinking_tags(request.summary).strip()
    agent = NotebookSummarizeAgent(language=str(request.metadata.get("ui_language", "en")))
    return clean_thinking_tags(
        await agent.summarize(
            title=request.title,
            record_type=request.record_type,
            user_query=request.user_query,
            output=request.output,
            metadata=request.metadata,
        )
    ).strip()


def _add_record_to_requested_notebooks(request: AddRecordRequest, summary: str) -> dict:
    if get_current_user().is_admin:
        return notebook_manager.add_record(
            notebook_ids=request.notebook_ids,
            record_type=request.record_type,
            title=request.title,
            summary=summary,
            user_query=request.user_query,
            output=request.output,
            metadata=request.metadata,
            kb_name=request.kb_name,
        )

    resolved_ids: list[str] = []
    manager = notebook_manager
    for notebook_id in request.notebook_ids:
        try:
            resolved = resolve_notebook_for_write(notebook_id, copy_public=True)
        except HTTPException:
            continue
        manager = resolved.manager
        resolved_ids.append(resolved.notebook_id)
    return manager.add_record(
        notebook_ids=resolved_ids,
        record_type=request.record_type,
        title=request.title,
        summary=summary,
        user_query=request.user_query,
        output=request.output,
        metadata=request.metadata,
        kb_name=request.kb_name,
    )


async def _stream_add_record_with_summary(
    request: AddRecordRequest,
) -> AsyncGenerator[str, None]:
    try:
        agent = NotebookSummarizeAgent(language=str(request.metadata.get("ui_language", "en")))
        summary_parts: list[str] = []
        if request.summary.strip():
            summary = clean_thinking_tags(request.summary).strip()
            summary_parts.append(summary)
            if summary:
                yield f"data: {json.dumps({'type': 'summary_chunk', 'content': summary}, ensure_ascii=False)}\n\n"
        else:
            async for chunk in agent.stream_summary(
                title=request.title,
                record_type=request.record_type,
                user_query=request.user_query,
                output=request.output,
                metadata=request.metadata,
            ):
                if not chunk:
                    continue
                summary_parts.append(chunk)

            summary = clean_thinking_tags("".join(summary_parts)).strip()
            if summary:
                yield f"data: {json.dumps({'type': 'summary_chunk', 'content': summary}, ensure_ascii=False)}\n\n"

        summary = clean_thinking_tags("".join(summary_parts)).strip()
        result = _add_record_to_requested_notebooks(request, summary)
        payload = {
            "type": "result",
            "success": True,
            "summary": summary,
            "record": result["record"],
            "added_to_notebooks": result["added_to_notebooks"],
        }
        yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
    except Exception as exc:
        payload = {"type": "error", "detail": str(exc)}
        yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.get("/list")
async def list_notebooks():
    """
    Get all notebook list

    Returns:
        Notebook list (includes summary information)
    """
    try:
        if get_current_user().is_admin:
            notebooks = [
                {
                    **notebook,
                    "source": "admin",
                    "read_only": False,
                    "assigned": False,
                    "provenance_label": "Admin workspace",
                }
                for notebook in notebook_manager.list_notebooks()
            ]
        else:
            notebooks = list_visible_notebooks()
        return {"notebooks": notebooks, "total": len(notebooks)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/statistics")
async def get_statistics():
    """
    Get notebook statistics

    Returns:
        Statistics information
    """
    try:
        stats = notebook_manager.get_statistics()
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/create")
async def create_notebook(request: CreateNotebookRequest):
    """
    Create new notebook

    Args:
        request: Create request

    Returns:
        Created notebook information
    """
    try:
        notebook = notebook_manager.create_notebook(
            name=request.name,
            description=request.description,
            color=request.color,
            icon=request.icon,
        )
        return {"success": True, "notebook": notebook}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{notebook_id}")
async def get_notebook(notebook_id: str):
    """
    Get notebook details

    Args:
        notebook_id: Notebook ID

    Returns:
        Notebook details (includes all records)
    """
    try:
        if get_current_user().is_admin:
            notebook = notebook_manager.get_notebook(notebook_id)
            if not notebook:
                raise HTTPException(status_code=404, detail="Notebook not found")
            return {
                **notebook,
                "source": "admin",
                "read_only": False,
                "provenance_label": "Admin workspace",
            }

        resolved = resolve_notebook_for_read(notebook_id)
        notebook = resolved.manager.get_notebook(resolved.notebook_id)
        if not notebook:
            raise HTTPException(status_code=404, detail="Notebook not found")
        return {
            **notebook,
            "source": resolved.source,
            "read_only": resolved.read_only,
            "provenance_label": "Shared by admin" if resolved.read_only else "Created by you",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{notebook_id}")
async def update_notebook(notebook_id: str, request: UpdateNotebookRequest):
    """
    Update notebook information

    Args:
        notebook_id: Notebook ID
        request: Update request

    Returns:
        Updated notebook information
    """
    try:
        manager = notebook_manager
        resolved_id = notebook_id
        if not get_current_user().is_admin:
            resolved = resolve_notebook_for_write(notebook_id, copy_public=False)
            manager = resolved.manager
            resolved_id = resolved.notebook_id
        notebook = manager.update_notebook(
            notebook_id=resolved_id,
            name=request.name,
            description=request.description,
            color=request.color,
            icon=request.icon,
        )
        if not notebook:
            raise HTTPException(status_code=404, detail="Notebook not found")
        return {"success": True, "notebook": notebook}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{notebook_id}")
async def delete_notebook(notebook_id: str):
    """
    Delete notebook

    Args:
        notebook_id: Notebook ID

    Returns:
        Deletion result
    """
    try:
        manager = notebook_manager
        resolved_id = notebook_id
        if not get_current_user().is_admin:
            resolved = resolve_notebook_for_write(notebook_id, copy_public=False)
            manager = resolved.manager
            resolved_id = resolved.notebook_id
        success = manager.delete_notebook(resolved_id)
        if not success:
            raise HTTPException(status_code=404, detail="Notebook not found")
        return {"success": True, "message": "Notebook deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/add_record")
async def add_record(request: AddRecordRequest):
    """
    Add record to notebook

    Args:
        request: Add record request

    Returns:
        Addition result
    """
    try:
        summary = await _build_record_summary(request)
        result = _add_record_to_requested_notebooks(request, summary)
        return {
            "success": True,
            "summary": summary,
            "record": result["record"],
            "added_to_notebooks": result["added_to_notebooks"],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/add_record_with_summary")
async def add_record_with_summary(request: AddRecordRequest):
    """Add record to notebook and stream generated summary."""
    return StreamingResponse(
        _stream_add_record_with_summary(request),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.delete("/{notebook_id}/records/{record_id}")
async def remove_record(notebook_id: str, record_id: str):
    """
    Remove record from notebook

    Args:
        notebook_id: Notebook ID
        record_id: Record ID

    Returns:
        Deletion result
    """
    try:
        manager = notebook_manager
        resolved_id = notebook_id
        if not get_current_user().is_admin:
            resolved = resolve_notebook_for_write(notebook_id, copy_public=True)
            manager = resolved.manager
            resolved_id = resolved.notebook_id
        success = manager.remove_record(resolved_id, record_id)
        if not success:
            raise HTTPException(status_code=404, detail="Record not found")
        return {"success": True, "message": "Record removed successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{notebook_id}/records/{record_id}")
async def update_record(notebook_id: str, record_id: str, request: UpdateRecordRequest):
    """Update an existing notebook record in place."""
    try:
        manager = notebook_manager
        resolved_id = notebook_id
        if not get_current_user().is_admin:
            resolved = resolve_notebook_for_write(notebook_id, copy_public=True)
            manager = resolved.manager
            resolved_id = resolved.notebook_id
        updated = manager.update_record(
            notebook_id=resolved_id,
            record_id=record_id,
            title=request.title,
            summary=request.summary,
            user_query=request.user_query,
            output=request.output,
            metadata=request.metadata,
            kb_name=request.kb_name,
        )
        if not updated:
            raise HTTPException(status_code=404, detail="Record not found")
        return {"success": True, "record": updated}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health_check():
    """Health check"""
    return {"status": "healthy", "service": "notebook"}
