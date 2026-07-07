"""Tests for session turn event helpers."""

from __future__ import annotations

from deeptutor.core.stream import StreamEvent, StreamEventType
from deeptutor.services.session.events import (
    artifact_attachments,
    event_usage_summary,
    narration_marker_call_id,
    should_capture_assistant_content,
)


class TestShouldCaptureAssistantContent:
    def test_content_without_call_id_is_captured(self) -> None:
        event = StreamEvent(type=StreamEventType.CONTENT, content="hello")
        assert should_capture_assistant_content(event) is True

    def test_content_with_final_response_kind_is_captured(self) -> None:
        event = StreamEvent(
            type=StreamEventType.CONTENT,
            content="answer",
            metadata={"call_id": "c1", "call_kind": "llm_final_response"},
        )
        assert should_capture_assistant_content(event) is True

    def test_content_with_non_final_call_kind_not_captured(self) -> None:
        event = StreamEvent(
            type=StreamEventType.CONTENT,
            content="internal",
            metadata={"call_id": "c1", "call_kind": "llm_reasoning"},
        )
        assert should_capture_assistant_content(event) is False

    def test_agent_loop_round_content_is_captured(self) -> None:
        event = StreamEvent(
            type=StreamEventType.CONTENT,
            content="the answer",
            metadata={"call_id": "c1", "call_kind": "agent_loop_round"},
        )
        assert should_capture_assistant_content(event) is True

    def test_non_content_event_not_captured(self) -> None:
        event = StreamEvent(type=StreamEventType.THINKING, content="hmm")
        assert should_capture_assistant_content(event) is False

    def test_tool_call_not_captured(self) -> None:
        event = StreamEvent(type=StreamEventType.TOOL_CALL, content="web_search")
        assert should_capture_assistant_content(event) is False


class TestNarrationMarkerCallId:
    def test_narration_marker_returns_call_id(self) -> None:
        event = StreamEvent(
            type=StreamEventType.PROGRESS,
            metadata={
                "call_id": "round-1",
                "trace_kind": "call_status",
                "call_state": "complete",
                "call_role": "narration",
            },
        )
        assert narration_marker_call_id(event) == "round-1"

    def test_finish_marker_is_not_narration(self) -> None:
        event = StreamEvent(
            type=StreamEventType.PROGRESS,
            metadata={
                "call_id": "round-2",
                "trace_kind": "call_status",
                "call_state": "complete",
                "call_role": "finish",
            },
        )
        assert narration_marker_call_id(event) is None

    def test_running_status_is_not_narration(self) -> None:
        event = StreamEvent(
            type=StreamEventType.PROGRESS,
            metadata={
                "call_id": "round-1",
                "trace_kind": "call_status",
                "call_state": "running",
                "call_role": "narration",
            },
        )
        assert narration_marker_call_id(event) is None


class TestArtifactAttachments:
    def _sources_event(self, sources: list[dict]) -> StreamEvent:
        return StreamEvent(type=StreamEventType.SOURCES, metadata={"sources": sources})

    def test_artifact_source_becomes_generated_attachment(self) -> None:
        event = self._sources_event(
            [
                {
                    "type": "artifact",
                    "filename": "report.pdf",
                    "url": "/api/outputs/workspace/chat/chat/t1/exec/report.pdf",
                    "mime_type": "application/pdf",
                    "size_bytes": 2048,
                }
            ]
        )

        attachments = artifact_attachments(event)

        assert len(attachments) == 1
        attachment = attachments[0]
        assert attachment["type"] == "document"
        assert attachment["filename"] == "report.pdf"
        assert attachment["url"].endswith("report.pdf")
        assert attachment["mime_type"] == "application/pdf"
        assert attachment["generated"] is True

    def test_image_artifact_typed_as_image(self) -> None:
        event = self._sources_event(
            [
                {
                    "type": "artifact",
                    "filename": "chart.png",
                    "url": "/api/outputs/x/chart.png",
                    "mime_type": "image/png",
                }
            ]
        )
        assert artifact_attachments(event)[0]["type"] == "image"

    def test_non_artifact_sources_ignored(self) -> None:
        event = self._sources_event([{"type": "rag", "query": "q", "kb_name": "kb"}])
        assert artifact_attachments(event) == []

    def test_tool_result_artifacts_extracted(self) -> None:
        event = StreamEvent(
            type=StreamEventType.TOOL_RESULT,
            content="Exit code: 0",
            metadata={
                "tool_metadata": {
                    "exit_code": 0,
                    "artifacts": [
                        {
                            "filename": "notes.pdf",
                            "url": "/api/outputs/workspace/chat/chat/t2/exec/notes.pdf",
                            "mime_type": "application/pdf",
                            "size_bytes": 1024,
                        }
                    ],
                }
            },
        )

        attachments = artifact_attachments(event)

        assert len(attachments) == 1
        assert attachments[0]["filename"] == "notes.pdf"
        assert attachments[0]["generated"] is True

    def test_tool_result_without_artifacts_ignored(self) -> None:
        event = StreamEvent(
            type=StreamEventType.TOOL_RESULT,
            content="rag result",
            metadata={"tool_metadata": {"kb_name": "kb"}},
        )
        assert artifact_attachments(event) == []

    def test_non_sources_event_ignored(self) -> None:
        event = StreamEvent(type=StreamEventType.CONTENT, content="hello")
        assert artifact_attachments(event) == []

    def test_artifact_without_url_skipped(self) -> None:
        event = self._sources_event([{"type": "artifact", "filename": "x.pdf"}])
        assert artifact_attachments(event) == []


def test_event_usage_summary_reads_nested_cost_summary() -> None:
    event = StreamEvent(
        type=StreamEventType.RESULT,
        source="chat",
        metadata={"metadata": {"cost_summary": {"total_tokens": 42, "total_calls": 1}}},
    )

    assert event_usage_summary(event) == {"total_tokens": 42, "total_calls": 1}
