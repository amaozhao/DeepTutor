"use client";

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useLayoutEffect,
  useMemo,
  useReducer,
  useRef,
} from "react";
import { readStoredLanguage } from "@/context/app-shell-storage";
import type { StreamEvent, ChatMessage, LLMSelection } from "@/lib/unified-ws";
import { UnifiedWSClient } from "@/lib/unified-ws";
import {
  getSession,
  deleteMessage,
  updateBranchSelection,
  updateSessionTitle,
} from "@/lib/session-api";
import { notify } from "@/lib/notifications";
import i18n from "i18next";

import {
  chatReducer,
  createSessionEntry,
  initialState,
  type ChatState,
  type HistoryReferencePayload,
  type MemoryReferencePayload,
  type MessageAttachment,
  type MessageItem,
  type MessageRequestSnapshot,
  type NotebookReferencePayload,
  type OutgoingAttachment,
  type QuestionNotebookReferencePayload,
  type SendMessageOptions,
  type SessionStatusSnapshot,
  type SessionRuntimeStatus,
} from "@/context/chat/state";
import {
  loadSessionActionFromDetail,
  newSessionAction,
  renameSessionTitleAction,
  subscribeTurnMessageFromDetail,
} from "@/context/chat/session";
import {
  runningSessionStatuses,
  selectedChatState,
  selectedSessionRecord,
} from "@/context/chat/selectors";
import {
  useActiveSessionStorageSync,
  useInitialDraftSession,
  useStoredLanguageSync,
  useStreamingTimeoutGuard,
} from "@/context/chat/effects";
import {
  buildRegenerateMessage,
  buildSubmitUserReplyMessage,
  cancelStreamingAction,
  regenerateStartActions,
  regenerateSessionPlan,
  userReplyTurnId,
  type AskUserReply,
} from "@/context/chat/commands";
import {
  branchSwitchPlan,
  editParentId,
  nextMessageParentIds,
  persistedMessageIdAt,
  userMessageIndexById,
} from "@/context/chat/branches";
import {
  buildEffectiveChatRequest,
  chatStartTurnActions,
} from "@/context/chat/request";
import {
  cancelRunnerTurn,
  cleanupRunnersAndTimers,
  doneStreamEndAction,
  effectiveRunnerKey,
  ensureRunner as ensureChatRunner,
  eventStatus,
  moveRunner,
  runnerClosedFailedAction,
  runnerConnectionFailedAction,
  runnerSendState,
  scheduleRunnerDisconnect,
  scheduleRunnerRetry,
  sessionBindAction,
  sessionMetaAction,
  shouldFailClosedRunner,
  terminalErrorActions,
  type ChatRunner,
} from "@/context/chat/transport";
export type {
  ChatState,
  MessageAttachment,
  MessageItem,
  MessageRequestSnapshot,
  SendMessageOptions,
} from "@/context/chat/state";
// Grace window between the orchestrator's ``done`` event and the actual
// WS disconnect. Keeps the connection alive long enough for post-turn
// pushes like the LLM-generated ``session_meta`` title update to land.
const POST_DONE_DISCONNECT_DELAY_MS = 15_000;

interface ChatContextValue {
  state: ChatState;
  setTools: (tools: string[]) => void;
  setCapability: (cap: string | null) => void;
  setKBs: (kbs: string[]) => void;
  setLLMSelection: (selection: LLMSelection | null) => void;
  setPersonaSelection: (persona: string) => void;
  setLanguage: (lang: string) => void;
  sendMessage: (
    content: string,
    attachments?: OutgoingAttachment[],
    config?: Record<string, unknown>,
    notebookReferences?: NotebookReferencePayload[],
    historyReferences?: HistoryReferencePayload,
    options?: SendMessageOptions,
    questionNotebookReferences?: QuestionNotebookReferencePayload,
    persona?: string,
    memoryReferences?: MemoryReferencePayload,
  ) => void;
  cancelStreamingTurn: () => void;
  /**
   * Deliver the user's reply for a turn that is paused on an
   * ``ask_user`` tool call. Sends the reply via the unified WS so the
   * backend can substitute it into the matching ``role=tool`` message
   * and resume the agentic loop on the **same** turn. No-op when the
   * active session has no live turn waiting on input.
   *
   * Accepts a plain string (legacy single-question reply) or a
   * structured object with ``answers`` (v2 multi-question reply).
   */
  submitUserReply: (reply: AskUserReply) => void;
  regenerateLastMessage: () => void;
  deleteTurn: (messageId: number) => Promise<void>;
  /** Re-send a user message under a new branch (sibling of the original).
   *  Uses the composer's current capability / refs — only the text is
   *  taken from ``newContent``. Re-runs the turn from the original's
   *  parent context. */
  editMessage: (messageId: number, newContent: string) => Promise<void>;
  /** Switch which sibling is currently visible at a branch point. */
  switchBranch: (parentMessageId: number | null, childId: number) => void;
  renameSessionTitle: (title: string) => Promise<void>;
  newSession: () => void;
  loadSession: (sessionId: string, signal?: AbortSignal) => Promise<void>;
  selectedSessionId: string | null;
  sessionStatuses: Record<string, SessionStatusSnapshot>;
  sidebarRefreshToken: number;
}

const ChatCtx = createContext<ChatContextValue | null>(null);

export function UnifiedChatProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const [state, dispatch] = useReducer(chatReducer, initialState);
  const stateRef = useRef(initialState);
  const runnersRef = useRef<Map<string, ChatRunner>>(new Map());
  const draftCounterRef = useRef(0);
  const retryTimersRef = useRef<Set<ReturnType<typeof setTimeout>>>(new Set());
  // Tracks in-flight regenerate requests so we can restore the popped
  // assistant message if the server rejects the request (e.g. ``regenerate_busy``
  // or ``nothing_to_regenerate``). Keyed by session entry key.
  const pendingRegenerateRef = useRef<Map<string, MessageItem>>(new Map());
  // Forward-declared so ``handleRunnerEvent`` (created above
  // ``loadSession`` in source order) can trigger a server refresh after
  // a turn finishes without taking a stale closure of ``loadSession``.
  const loadSessionRef = useRef<((sessionId: string) => Promise<void>) | null>(
    null,
  );

  useLayoutEffect(() => {
    stateRef.current = state;
  }, [state]);

  useEffect(
    () => () => {
      cleanupRunnersAndTimers(
        runnersRef.current,
        retryTimersRef.current,
        clearTimeout,
      );
    },
    [],
  );

  const makeDraftKey = useCallback(() => {
    draftCounterRef.current += 1;
    return `draft_${Date.now()}_${draftCounterRef.current}`;
  }, []);

  const handleRunnerEvent = useCallback(
    (runnerKey: string, event: StreamEvent) => {
      const effectiveKey = effectiveRunnerKey(runnersRef.current, runnerKey);
      if (event.type === "session") {
        const action = sessionBindAction(effectiveKey, event);
        if (action) {
          dispatch(action);
          moveRunner(runnersRef.current, effectiveKey, action.sessionId);
        }
        return;
      }
      if (event.type === "session_meta") {
        dispatch(sessionMetaAction(effectiveKey, event));
        return;
      }
      if (event.type === "done") {
        const status = eventStatus(event, "completed");
        dispatch(doneStreamEndAction(effectiveKey, event));
        pendingRegenerateRef.current.delete(effectiveKey);
        // Hold the WS open briefly so post-turn ``session_meta`` events
        // (e.g. the LLM-generated title for the first user/assistant
        // pair) can still reach us. The backend generates the title
        // before its finally block sends the subscriber sentinel, but
        // the title model can take a couple of seconds — disconnecting
        // synchronously on ``done`` would race that publish.
        scheduleRunnerDisconnect(
          runnersRef.current,
          effectiveKey,
          POST_DONE_DISCONNECT_DELAY_MS,
          window.setTimeout,
        );
        // Reconcile optimistic client-side message ids with the
        // server's real ids after the turn finishes. Without this the
        // Edit button (which needs a real id to attach the new branch
        // under) and branch navigation (which keys off real ids) would
        // stay disabled until the user navigates away and back.
        if (status === "completed") {
          const doneMeta = event.metadata as {
            user_message_id?: number;
            assistant_message_id?: number;
          } | null;
          const assistantMessageId = doneMeta?.assistant_message_id ?? null;
          if (assistantMessageId != null) {
            dispatch({
              type: "RECONCILE_TURN",
              key: effectiveKey,
              turnId: event.turn_id || null,
              userMessageId: doneMeta?.user_message_id ?? null,
              assistantMessageId,
            });
          } else {
            const finishedSession = stateRef.current.sessions[effectiveKey];
            const sessionId = finishedSession?.sessionId;
            if (sessionId) {
              loadSessionRef.current?.(sessionId).catch(() => {
                /* non-fatal — local state remains usable */
              });
            }
          }
        }
        return;
      }
      dispatch({ type: "STREAM_EVENT", key: effectiveKey, event });
      const errorActions = terminalErrorActions(
        effectiveKey,
        event,
        pendingRegenerateRef.current.get(effectiveKey),
      );
      if (errorActions.length) {
        pendingRegenerateRef.current.delete(effectiveKey);
        for (const action of errorActions) dispatch(action);
      }
    },
    [],
  );

  const ensureRunner = useCallback(
    (key: string) => {
      return ensureChatRunner(
        runnersRef.current,
        key,
        stateRef.current.sessions[key],
        (record) =>
          new UnifiedWSClient(
            (event) => handleRunnerEvent(record.key, event),
            () => {
              const session = stateRef.current.sessions[record.key];
              if (shouldFailClosedRunner(session)) {
                dispatch(runnerClosedFailedAction(record.key));
                // Surface the disconnect to the user. The WS client already
                // logs to console — we add a toast so non-debugging users
                // don't see streaming silently flatline.
                notify(
                  i18n.t(
                    "Connection lost while generating. Please retry your message.",
                  ),
                  { tone: "error", durationMs: 6000 },
                );
              }
            },
          ),
      );
    },
    [handleRunnerEvent],
  );

  const sendThroughRunner = useCallback(
    function dispatchToRunner(key: string, msg: ChatMessage, attempt = 0) {
      const runner = ensureRunner(key);
      const sendState = runnerSendState({
        connected: runner.client.connected,
        attempt,
        maxAttempts: 10,
      });
      if (sendState === "failed") {
        console.error("WebSocket failed to connect after retries");
        dispatch(runnerConnectionFailedAction(key));
        // Surfaces the dead-after-N-retries case (different code path
        // from the close-while-streaming handler above). Same user
        // mental model, so same toast copy.
        notify(
          i18n.t(
            "Couldn't reach the server. Please check your connection and retry.",
          ),
          { tone: "error", durationMs: 6000 },
        );
        return;
      }
      if (sendState === "retry") {
        scheduleRunnerRetry(
          retryTimersRef.current,
          () => dispatchToRunner(key, msg, attempt + 1),
          200,
          setTimeout,
        );
        return;
      }
      runner.client.send(msg);
    },
    [ensureRunner],
  );

  const loadSession = useCallback(
    async (sessionId: string, signal?: AbortSignal) => {
      const session = await getSession(sessionId, signal);
      dispatch(loadSessionActionFromDetail(session, readStoredLanguage()));
      const subscription = subscribeTurnMessageFromDetail(session);
      if (subscription) sendThroughRunner(subscription.key, subscription.message);
    },
    [sendThroughRunner],
  );

  useLayoutEffect(() => {
    loadSessionRef.current = loadSession;
  }, [loadSession]);

  useActiveSessionStorageSync(state);
  useStoredLanguageSync(dispatch);
  useInitialDraftSession({
    selectedKey: state.selectedKey,
    dispatch,
    makeDraftKey,
  });

  useStreamingTimeoutGuard({ dispatch, runnersRef, stateRef });

  const sendMessage = useCallback(
    (
      content: string,
      attachments?: OutgoingAttachment[],
      config?: Record<string, unknown>,
      notebookReferences?: NotebookReferencePayload[],
      historyReferences?: HistoryReferencePayload,
      options?: SendMessageOptions,
      questionNotebookReferences?: QuestionNotebookReferencePayload,
      persona?: string,
      memoryReferences?: MemoryReferencePayload,
    ) => {
      const currentState = stateRef.current;
      let key = currentState.selectedKey;
      if (!key) {
        key = makeDraftKey();
        dispatch(newSessionAction(key));
      }
      const session = currentState.sessions[key] ?? createSessionEntry(key);
      const { localParentId, wireParentId } = nextMessageParentIds({
        explicitParentId: options?.parentMessageId,
        messages: session.messages,
        selectedBranches: session.selectedBranches,
      });
      const request = buildEffectiveChatRequest({
        content,
        attachments,
        config,
        notebookReferences,
        historyReferences,
        options,
        questionNotebookReferences,
        persona,
        memoryReferences,
        session,
        language: readStoredLanguage(),
        wireParentId,
      });
      for (const action of chatStartTurnActions({
        key,
        content,
        request,
        parentMessageId: localParentId,
        displayUserMessage: options?.displayUserMessage,
      })) dispatch(action);
      sendThroughRunner(key, request.turnMessage);
    },
    [makeDraftKey, sendThroughRunner],
  );

  const cancelStreamingTurn = useCallback(() => {
    const selected = selectedSessionRecord(stateRef.current);
    if (!selected) return;
    const { key, session } = selected;
    cancelRunnerTurn(runnersRef.current, key, session.activeTurnId);
    if (session.isStreaming) {
      dispatch(cancelStreamingAction(key));
    }
  }, []);

  const submitUserReply = useCallback(
    (reply: AskUserReply) => {
      const selected = selectedSessionRecord(stateRef.current);
      if (!selected) return;
      const { key, session } = selected;
      const turnId = userReplyTurnId(session);
      if (!turnId) return;
      sendThroughRunner(key, buildSubmitUserReplyMessage(turnId, reply));
    },
    [sendThroughRunner],
  );

  const regenerateLastMessage = useCallback(() => {
    const selected = selectedSessionRecord(stateRef.current);
    if (!selected) return;
    const { key, session } = selected;
    const plan = regenerateSessionPlan(session);
    if (!plan.canRegenerate || !session?.sessionId) return;
    if (plan.restoreMessage) {
      pendingRegenerateRef.current.set(key, plan.restoreMessage);
    } else {
      pendingRegenerateRef.current.delete(key);
    }
    for (const action of regenerateStartActions(key)) dispatch(action);
    sendThroughRunner(
      key,
      buildRegenerateMessage(session.sessionId, readStoredLanguage()),
    );
  }, [sendThroughRunner]);

  const derivedState = useMemo<ChatState>(() => selectedChatState(state), [state]);

  const sessionStatuses = useMemo<Record<string, SessionStatusSnapshot>>(() => {
    return runningSessionStatuses(state.sessions);
  }, [state.sessions]);

  const setTools = useCallback((tools: string[]) => {
    dispatch({ type: "SET_TOOLS", tools });
  }, []);

  const setCapability = useCallback((cap: string | null) => {
    dispatch({ type: "SET_CAPABILITY", cap });
  }, []);

  const setKBs = useCallback((kbs: string[]) => {
    dispatch({ type: "SET_KB", kbs });
  }, []);

  const setLLMSelection = useCallback((selection: LLMSelection | null) => {
    dispatch({ type: "SET_LLM_SELECTION", selection });
  }, []);

  const setPersonaSelection = useCallback((persona: string) => {
    dispatch({ type: "SET_PERSONA_SELECTION", persona });
  }, []);

  const setLanguage = useCallback((lang: string) => {
    dispatch({ type: "SET_LANGUAGE", lang });
  }, []);

  const renameSessionTitle = useCallback(async (title: string) => {
    const trimmed = title.trim();
    if (!trimmed) return;
    const selected = selectedSessionRecord(stateRef.current);
    if (!selected) return;
    const { key, session } = selected;
    const sessionId = session?.sessionId;
    if (!sessionId) return;
    const updated = await updateSessionTitle(sessionId, trimmed);
    dispatch(renameSessionTitleAction({
      key,
      requestedTitle: trimmed,
      updatedTitle: updated.title,
    }));
  }, []);

  const newSession = useCallback(() => {
    dispatch(newSessionAction(makeDraftKey()));
  }, [makeDraftKey]);

  const editMessage = useCallback(
    async (messageId: number, newContent: string) => {
      const trimmed = newContent.trim();
      if (!trimmed) return;
      const selected = selectedSessionRecord(stateRef.current);
      if (!selected) return;
      const { key, session } = selected;
      // Edits create a new branch via a fresh turn — block while one is
      // already running so we don't queue against an in-flight stream
      // (matches the delete-turn guard).
      if (session.isStreaming) return;
      const idx = userMessageIndexById(session.messages, messageId);
      if (idx === -1) return;
      let original = session.messages[idx];
      // Optimistic in-flight rows have a negative client-side id — we
      // need a real server id to hang the new sibling under. Refresh
      // from the server, then re-resolve the row by its position in the
      // (now-persisted) thread before continuing.
      if (typeof original.id === "number" && original.id < 0) {
        if (!session.sessionId) return;
        try {
          await loadSession(session.sessionId);
        } catch {
          return;
        }
        const refreshed = stateRef.current.sessions[key];
        const realId = persistedMessageIdAt(refreshed?.messages, idx, "user");
        if (realId == null) return;
        original = { ...refreshed.messages[idx], id: realId };
      }
      if (typeof original.id !== "number" || original.id < 0) return;
      const parentId = editParentId(original);
      sendMessage(
        trimmed,
        undefined,
        undefined,
        undefined,
        undefined,
        { parentMessageId: parentId },
        undefined,
        undefined,
        undefined,
      );
    },
    [loadSession, sendMessage],
  );

  const switchBranch = useCallback(
    (parentMessageId: number | null, childId: number) => {
      const selected = selectedSessionRecord(stateRef.current);
      if (!selected) return;
      const { key, session } = selected;
      const plan = branchSwitchPlan({
        key,
        parentMessageId,
        childId,
        selectedBranches: session.selectedBranches,
      });
      dispatch(plan.action);
      const sessionId = session.sessionId;
      if (!sessionId) return;
      // Fire-and-forget — local state is the source of truth for the UI;
      // the server copy only matters for reload-time hydration.
      updateBranchSelection(sessionId, plan.selectedBranches).catch((err) => {
        console.warn("Failed to persist branch selection:", err);
      });
    },
    [],
  );

  const deleteTurn = useCallback(
    async (messageId: number) => {
      const selected = selectedSessionRecord(stateRef.current);
      if (!selected) return;
      const { key, session } = selected;
      if (!session.sessionId) return;
      if (session.isStreaming) return;
      let effectiveId = messageId;
      if (messageId < 0) {
        const origIdx = session.messages.findIndex((m) => m.id === messageId);
        if (origIdx === -1) return;
        try {
          await loadSession(session.sessionId);
        } catch {
          return;
        }
        const refreshed = stateRef.current.sessions[key];
        const realId = persistedMessageIdAt(refreshed?.messages, origIdx);
        if (realId == null) return;
        effectiveId = realId;
      }
      try {
        await deleteMessage(session.sessionId, effectiveId);
        dispatch({ type: "DELETE_TURN", key, messageId: effectiveId });
      } catch (err) {
        console.error("Failed to delete turn:", err);
      }
    },
    [loadSession],
  );

  // Memoize the context value so consumers don't re-render on every render of
  // this provider. Without this wrap, every stream-event-driven reducer
  // dispatch produced a fresh object identity, cascading a re-render through
  // every `useUnifiedChat()` consumer (chat page, composer, sidebar) on each
  // token. The callbacks below are already stable via useCallback; the only
  // things that should change identity are derivedState, sessionStatuses,
  // and sidebarRefreshToken.
  const value = useMemo<ChatContextValue>(
    () => ({
      state: derivedState,
      setTools,
      setCapability,
      setKBs,
      setLLMSelection,
      setPersonaSelection,
      setLanguage,
      sendMessage,
      cancelStreamingTurn,
      submitUserReply,
      regenerateLastMessage,
      deleteTurn,
      editMessage,
      switchBranch,
      renameSessionTitle,
      newSession,
      loadSession,
      selectedSessionId: derivedState.sessionId,
      sessionStatuses,
      sidebarRefreshToken: state.sidebarRefreshToken,
    }),
    [
      derivedState,
      setTools,
      setCapability,
      setKBs,
      setLLMSelection,
      setPersonaSelection,
      setLanguage,
      sendMessage,
      cancelStreamingTurn,
      submitUserReply,
      regenerateLastMessage,
      deleteTurn,
      editMessage,
      switchBranch,
      renameSessionTitle,
      newSession,
      loadSession,
      sessionStatuses,
      state.sidebarRefreshToken,
    ],
  );

  return <ChatCtx.Provider value={value}>{children}</ChatCtx.Provider>;
}

export function useUnifiedChat() {
  const ctx = useContext(ChatCtx);
  if (!ctx)
    throw new Error("useUnifiedChat must be inside UnifiedChatProvider");
  return ctx;
}
