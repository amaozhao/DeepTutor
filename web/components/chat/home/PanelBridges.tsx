"use client";

import { useEffect } from "react";
import type { MutableRefObject } from "react";

import { useQuizFollowupController } from "@/context/QuizFollowupContext";
import { useGeogebraTabOpener } from "@/context/GeogebraTabContext";
import type { StreamEvent } from "@/lib/unified-ws";
import type { SessionViewerPanelHandle } from "@/components/chat/home/SessionViewerPanel";

export function QuizFollowupBridge({
  viewerPanelRef,
}: {
  viewerPanelRef: MutableRefObject<SessionViewerPanelHandle | null>;
}) {
  const controller = useQuizFollowupController();
  useEffect(() => {
    controller.setOpenTabHandler((ctx) => {
      viewerPanelRef.current?.openQuizFollowupTab(ctx);
    });
    return () => controller.setOpenTabHandler(null);
  }, [controller, viewerPanelRef]);
  return null;
}

export function GeogebraTabBridge({
  viewerPanelRef,
}: {
  viewerPanelRef: MutableRefObject<SessionViewerPanelHandle | null>;
}) {
  const controller = useGeogebraTabOpener();
  useEffect(() => {
    if (!controller) return;
    controller.setOpenHandler((payload) => {
      viewerPanelRef.current?.openGeogebraTab(payload);
    });
    return () => controller.setOpenHandler(null);
  }, [controller, viewerPanelRef]);
  return null;
}

export function SubagentTabWatcher({
  messages,
  viewerPanelRef,
}: {
  messages: { events?: StreamEvent[] }[];
  viewerPanelRef: MutableRefObject<SessionViewerPanelHandle | null>;
}) {
  useEffect(() => {
    const groups = new Map<string, { label: string; events: StreamEvent[] }>();
    for (const msg of messages) {
      for (const ev of msg.events ?? []) {
        const meta = (ev.metadata ?? {}) as Record<string, unknown>;
        if (meta.trace_kind !== "subagent_event") continue;
        const key = String(meta.turn_id || meta.call_id || meta.trace_id || "");
        if (!key) continue;
        const existing = groups.get(key);
        const label = String(
          meta.subagent_name || existing?.label || "Subagent",
        );
        if (existing) {
          existing.label = label;
          existing.events.push(ev);
        } else {
          groups.set(key, { label, events: [ev] });
        }
      }
    }
    for (const [key, group] of groups) {
      viewerPanelRef.current?.openSubagentTab(key, group.label, group.events);
    }
  }, [messages, viewerPanelRef]);
  return null;
}
