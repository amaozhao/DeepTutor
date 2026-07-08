"use client";

import { useCallback, useRef, useState } from "react";
import type { ClipboardEvent, DragEvent } from "react";

import type { FilePreviewSource } from "@/components/chat/preview/previewerFor";
import { useAttachmentLimits } from "@/lib/attachment-limits";
import {
  fileToAttachment,
  filterAttachments,
  type PendingAttachment,
} from "@/lib/attachments";

type Translate = (key: string, options?: Record<string, unknown>) => string;

export function useChatAttachments(t: Translate) {
  const attachmentLimits = useAttachmentLimits();
  const [attachments, setAttachments] = useState<PendingAttachment[]>([]);
  const [dragging, setDragging] = useState(false);
  const [attachmentError, setAttachmentError] = useState<string | null>(null);
  const [previewSource, setPreviewSource] = useState<FilePreviewSource | null>(
    null,
  );
  const dragCounter = useRef(0);
  const attachmentErrorTimer = useRef<ReturnType<typeof setTimeout> | null>(
    null,
  );

  const showAttachmentError = useCallback((message: string) => {
    setAttachmentError(message);
    if (attachmentErrorTimer.current) {
      clearTimeout(attachmentErrorTimer.current);
    }
    attachmentErrorTimer.current = setTimeout(() => {
      setAttachmentError(null);
      attachmentErrorTimer.current = null;
    }, 4000);
  }, []);

  const filterAndReportFiles = useCallback(
    (files: File[]): File[] => {
      const { accepted, rejected } = filterAttachments(
        files,
        attachments,
        attachmentLimits,
      );
      if (rejected.length) {
        const first = rejected[0];
        let msg: string;
        if (first.reason === "too_large") {
          msg = t("File too large: {{name}}", { name: first.name });
        } else if (first.reason === "quota") {
          msg = t("Too many files, skipped some");
        } else {
          msg = t("Unsupported file type: {{name}}", { name: first.name });
        }
        showAttachmentError(msg);
      }
      return accepted;
    },
    [attachmentLimits, attachments, showAttachmentError, t],
  );

  const handlePaste = useCallback(
    async (event: ClipboardEvent) => {
      const items = Array.from(event.clipboardData.items);
      const files = items
        .filter((item) => item.kind === "file")
        .map((item) => item.getAsFile())
        .filter((f): f is File => f !== null);
      const accepted = filterAndReportFiles(files);
      if (!accepted.length) return;
      event.preventDefault();
      const next = await Promise.all(accepted.map(fileToAttachment));
      setAttachments((prev) => [...prev, ...next]);
    },
    [filterAndReportFiles],
  );

  const removeAttachment = useCallback((index: number) => {
    setAttachments((prev) => prev.filter((_, i) => i !== index));
  }, []);

  const handlePreviewPendingAttachment = useCallback(
    (index: number) => {
      const attachment = attachments[index];
      if (!attachment) return;
      setPreviewSource({
        filename: attachment.filename,
        mimeType: attachment.mimeType,
        type: attachment.type,
        base64: attachment.base64,
        size: attachment.size,
      });
    },
    [attachments],
  );

  const handleClosePreview = useCallback(() => {
    setPreviewSource(null);
  }, []);

  const handleDragEnter = useCallback((event: DragEvent) => {
    event.preventDefault();
    event.stopPropagation();
    dragCounter.current += 1;
    if (event.dataTransfer.types.includes("Files")) setDragging(true);
  }, []);

  const handleDragLeave = useCallback((event: DragEvent) => {
    event.preventDefault();
    event.stopPropagation();
    dragCounter.current -= 1;
    if (dragCounter.current === 0) setDragging(false);
  }, []);

  const handleDragOver = useCallback((event: DragEvent) => {
    event.preventDefault();
    event.stopPropagation();
  }, []);

  const handleDrop = useCallback(
    async (event: DragEvent) => {
      event.preventDefault();
      event.stopPropagation();
      setDragging(false);
      dragCounter.current = 0;
      const accepted = filterAndReportFiles(
        Array.from(event.dataTransfer.files),
      );
      if (!accepted.length) return;
      const next = await Promise.all(accepted.map(fileToAttachment));
      setAttachments((prev) => [...prev, ...next]);
    },
    [filterAndReportFiles],
  );

  const handleAddFiles = useCallback(
    async (files: File[]) => {
      const accepted = filterAndReportFiles(files);
      if (!accepted.length) return;
      const next = await Promise.all(accepted.map(fileToAttachment));
      setAttachments((prev) => [...prev, ...next]);
    },
    [filterAndReportFiles],
  );

  const clearAttachments = useCallback(() => {
    setAttachments([]);
  }, []);

  return {
    attachments,
    dragging,
    attachmentError,
    previewSource,
    dragCounter,
    handlePaste,
    removeAttachment,
    handlePreviewPendingAttachment,
    handleClosePreview,
    handleDragEnter,
    handleDragLeave,
    handleDragOver,
    handleDrop,
    handleAddFiles,
    clearAttachments,
  };
}
