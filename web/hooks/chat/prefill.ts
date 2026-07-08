"use client";

import { useEffect, useRef } from "react";

import { chatVisualizePromptFromEvent } from "@/lib/chat/prefill";

export function useChatComposerPrefillBridge() {
  const prefillInputRef = useRef<((text: string) => void) | null>(null);

  useEffect(() => {
    const onVizPrompt = (event: Event) => {
      const text = chatVisualizePromptFromEvent(event);
      if (text) prefillInputRef.current?.(text);
    };
    window.addEventListener("dt:visualize-prompt", onVizPrompt);
    return () => window.removeEventListener("dt:visualize-prompt", onVizPrompt);
  }, []);

  return prefillInputRef;
}
