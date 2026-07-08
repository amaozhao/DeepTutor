"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { MouseEvent } from "react";

import type { SessionViewerPanelHandle } from "@/components/chat/home/SessionViewerPanel";
import type { MessageAttachment } from "@/context/UnifiedChatContext";

const VIEWER_PANEL_STORAGE_KEY = "dt:chat:viewer-panel";

export function useChatViewerPanel() {
  const [viewerPanelOpen, setViewerPanelOpen] = useState(false);
  const viewerPanelRef = useRef<SessionViewerPanelHandle | null>(null);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (window.localStorage.getItem(VIEWER_PANEL_STORAGE_KEY) === "1") {
      setViewerPanelOpen(true);
    }
  }, []);

  const setViewerOpen = useCallback((next: boolean) => {
    setViewerPanelOpen(next);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(VIEWER_PANEL_STORAGE_KEY, next ? "1" : "0");
    }
  }, []);

  const toggleViewerPanel = useCallback(() => {
    setViewerPanelOpen((prev) => {
      const next = !prev;
      if (typeof window !== "undefined") {
        window.localStorage.setItem(
          VIEWER_PANEL_STORAGE_KEY,
          next ? "1" : "0",
        );
      }
      return next;
    });
  }, []);

  const ensureActivityPanelOpen = useCallback(() => {
    setViewerOpen(true);
    viewerPanelRef.current?.focusActivityHome();
  }, [setViewerOpen]);

  const handlePreviewMessageAttachment = useCallback(
    (attachment: MessageAttachment) => {
      viewerPanelRef.current?.openFileTab(attachment);
    },
    [],
  );

  const handleMessagesClick = useCallback((event: MouseEvent) => {
    if (event.defaultPrevented) return;
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey)
      return;
    if (event.button !== 0) return;
    const target = event.target as HTMLElement | null;
    if (!target) return;
    const anchor = target.closest<HTMLAnchorElement>("a[href]");
    if (!anchor) return;
    const href = anchor.getAttribute("href");
    if (!href) return;
    if (!/^https?:\/\//i.test(href)) return;
    event.preventDefault();
    viewerPanelRef.current?.openWebTab(href);
  }, []);

  return {
    viewerPanelRef,
    viewerPanelOpen,
    setViewerOpen,
    toggleViewerPanel,
    ensureActivityPanelOpen,
    handlePreviewMessageAttachment,
    handleMessagesClick,
  };
}
