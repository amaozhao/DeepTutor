import { useEffect, type Dispatch, type MutableRefObject } from "react";

import {
  LANGUAGE_EVENT,
  LANGUAGE_STORAGE_KEY,
  normalizeLanguage,
  readStoredChatResponseTimeout,
  writeStoredActiveSessionId,
} from "@/context/app-shell-storage";
import { hasPendingAskUserInMessages } from "@/lib/ask-user-state";
import type { Action, ProviderState } from "@/context/chat/state";
import type { ChatRunnerMap } from "@/context/chat/transport";
import { initialDraftSessionAction } from "@/context/chat/session";

export function useActiveSessionStorageSync(state: ProviderState): void {
  useEffect(() => {
    if (typeof window === "undefined") return;
    const current = state.selectedKey ? state.sessions[state.selectedKey] : null;
    writeStoredActiveSessionId(current?.sessionId ?? null);
  }, [state.selectedKey, state.sessions]);
}

export function useStoredLanguageSync(dispatch: Dispatch<Action>): void {
  useEffect(() => {
    if (typeof window === "undefined") return;

    const syncLanguage = (language: string | null | undefined) => {
      dispatch({ type: "SET_LANGUAGE", lang: normalizeLanguage(language) });
    };
    const onLanguage = (event: Event) => {
      const detail = (event as CustomEvent<{ language?: string }>).detail;
      syncLanguage(detail?.language);
    };
    const onStorage = (event: StorageEvent) => {
      if (event.key === LANGUAGE_STORAGE_KEY) syncLanguage(event.newValue);
    };

    window.addEventListener(LANGUAGE_EVENT, onLanguage);
    window.addEventListener("storage", onStorage);
    return () => {
      window.removeEventListener(LANGUAGE_EVENT, onLanguage);
      window.removeEventListener("storage", onStorage);
    };
  }, [dispatch]);
}

export function useInitialDraftSession({
  selectedKey,
  dispatch,
  makeDraftKey,
}: {
  selectedKey: string | null;
  dispatch: Dispatch<Action>;
  makeDraftKey: () => string;
}): void {
  useEffect(() => {
    if (typeof window === "undefined") return;
    const action = initialDraftSessionAction({ selectedKey, makeDraftKey });
    if (action) dispatch(action);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
}

export function useStreamingTimeoutGuard({
  dispatch,
  runnersRef,
  stateRef,
}: {
  dispatch: Dispatch<Action>;
  runnersRef: MutableRefObject<ChatRunnerMap>;
  stateRef: MutableRefObject<ProviderState>;
}): void {
  useEffect(() => {
    const CHECK_INTERVAL_MS = 10_000;

    const timer = setInterval(() => {
      const timeoutSeconds = readStoredChatResponseTimeout();
      const idleTimeoutMs = timeoutSeconds * 1000;
      const current = stateRef.current;
      for (const [key, session] of Object.entries(current.sessions)) {
        if (!session.isStreaming) continue;
        if (hasPendingAskUserInMessages(session.messages, session.activeTurnId)) {
          continue;
        }
        if (Date.now() - session.updatedAt <= idleTimeoutMs) continue;

        dispatch({
          type: "STREAM_EVENT",
          key,
          event: {
            type: "error",
            source: "client",
            stage: "",
            content: `Connection timed out — no response received for ${timeoutSeconds} seconds.`,
            metadata: { turn_terminal: true, status: "failed" },
            timestamp: Date.now() / 1000,
          },
        });
        dispatch({ type: "STREAM_END", key, status: "failed" });

        const runner = runnersRef.current.get(key);
        if (runner) {
          runner.client.disconnect();
          runnersRef.current.delete(key);
        }
      }
    }, CHECK_INTERVAL_MS);

    return () => clearInterval(timer);
  }, [dispatch, runnersRef, stateRef]);
}
