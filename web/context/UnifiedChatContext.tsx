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
import {
  LANGUAGE_EVENT,
  LANGUAGE_STORAGE_KEY,
  normalizeLanguage,
  readStoredChatResponseTimeout,
  readStoredLanguage,
  writeStoredActiveSessionId,
} from "@/context/app-shell-storage";
import type { StreamEvent, ChatMessage, LLMSelection } from "@/lib/unified-ws";
import { UnifiedWSClient } from "@/lib/unified-ws";
import {
  getSession,
  deleteMessage,
  updateBranchSelection,
  updateSessionTitle,
  type SessionMessage,
} from "@/lib/session-api";
import { normalizeMarkdownForDisplay } from "@/lib/markdown-display";
import { normalizeMessageContent } from "@/lib/message-content";
import { buildVisiblePath, tipMessageId } from "@/lib/message-branches";
import { hasPendingAskUserInMessages } from "@/lib/ask-user-state";
import { notify } from "@/lib/notifications";
import i18n from "i18next";
import {
  asLLMSelection,
  hydrateMessageAttachments,
  hydrateRequestSnapshot,
  normalizeSelectedBranches,
} from "@/lib/chat/hydration";

import {
  chatReducer,
  createSessionEntry,
  ensureSelectedSession,
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
  effectiveRunnerKey,
  eventStatus,
  isRegenerateRejection,
  moveRunner,
  sessionEventIds,
  sessionMetaTitle,
  terminalErrorInfo,
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
  submitUserReply: (
    reply:
      | string
      | {
          text?: string;
          answers?: Array<{ questionId: string; text: string }>;
        },
  ) => void;
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
      runnersRef.current.forEach(({ client }) => client.disconnect());
      runnersRef.current.clear();
      retryTimersRef.current.forEach((id) => clearTimeout(id));
      retryTimersRef.current.clear();
    },
    [],
  );

  const makeDraftKey = useCallback(() => {
    draftCounterRef.current += 1;
    return `draft_${Date.now()}_${draftCounterRef.current}`;
  }, []);

  const hydrateMessages = useCallback(
    (messages: SessionMessage[]): MessageItem[] => {
      return messages
        .filter((message) => message.role !== "system")
        .map((message) => {
          const raw = normalizeMessageContent(message.content as unknown);
          const attachments = hydrateMessageAttachments(message.attachments);
          const requestSnapshot = hydrateRequestSnapshot(
            message,
            raw,
            attachments,
          );
          return {
            id: message.id,
            role: message.role,
            content:
              message.role === "assistant"
                ? normalizeMarkdownForDisplay(raw)
                : raw,
            capability: message.capability || "",
            events: Array.isArray(message.events) ? message.events : [],
            attachments,
            parentMessageId:
              message.parent_message_id === undefined
                ? null
                : message.parent_message_id,
            ...(requestSnapshot ? { requestSnapshot } : {}),
          };
        });
    },
    [],
  );

  const handleRunnerEvent = useCallback(
    (runnerKey: string, event: StreamEvent) => {
      const effectiveKey = effectiveRunnerKey(runnersRef.current, runnerKey);
      if (event.type === "session") {
        const { sessionId, turnId } = sessionEventIds(event);
        if (sessionId) {
          dispatch({
            type: "BIND_SERVER_SESSION",
            key: effectiveKey,
            sessionId,
            turnId,
          });
          moveRunner(runnersRef.current, effectiveKey, sessionId);
        }
        return;
      }
      if (event.type === "session_meta") {
        // Post-turn metadata push (currently only used for the
        // LLM-generated session title). The backend writes the new
        // title to its store *before* sending this event. Update the
        // active header immediately and bump the sidebar so history
        // rows refresh to the generated title without a flicker.
        const title = sessionMetaTitle(event);
        if (title) {
          dispatch({
            type: "SET_SESSION_TITLE",
            key: effectiveKey,
            title,
          });
        } else {
          dispatch({ type: "BUMP_SIDEBAR_REFRESH" });
        }
        return;
      }
      if (event.type === "done") {
        const status = eventStatus(event, "completed");
        dispatch({
          type: "STREAM_END",
          key: effectiveKey,
          status,
          turnId: event.turn_id || null,
        });
        pendingRegenerateRef.current.delete(effectiveKey);
        const runner = runnersRef.current.get(effectiveKey);
        // Hold the WS open briefly so post-turn ``session_meta`` events
        // (e.g. the LLM-generated title for the first user/assistant
        // pair) can still reach us. The backend generates the title
        // before its finally block sends the subscriber sentinel, but
        // the title model can take a couple of seconds — disconnecting
        // synchronously on ``done`` would race that publish.
        if (runner) {
          runnersRef.current.delete(effectiveKey);
          window.setTimeout(() => {
            runner.client.disconnect();
          }, POST_DONE_DISCONNECT_DELAY_MS);
        }
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
      const errorInfo = terminalErrorInfo(event);
      if (errorInfo.terminal) {
        // Pre-flight regenerate rejections never mutate server state, so we
        // roll back the optimistic POP_LAST_ASSISTANT/STREAM_START placeholder
        // to keep the transcript in sync with the server.
        if (isRegenerateRejection(errorInfo.reason)) {
          const stash = pendingRegenerateRef.current.get(effectiveKey);
          if (stash) {
            dispatch({
              type: "RESTORE_ASSISTANT",
              key: effectiveKey,
              message: stash,
            });
          }
        }
        pendingRegenerateRef.current.delete(effectiveKey);
        dispatch({
          type: "STREAM_END",
          key: effectiveKey,
          status: errorInfo.status,
          turnId: event.turn_id || null,
        });
      }
    },
    [],
  );

  const ensureRunner = useCallback(
    (key: string) => {
      const existing = runnersRef.current.get(key);
      if (existing) {
        const session = stateRef.current.sessions[key];
        if (session) {
          existing.client.setResumeState(session.activeTurnId, session.lastSeq);
        }
        if (!existing.client.connected) existing.client.connect();
        return existing;
      }
      const record = {
        key,
        client: new UnifiedWSClient(
          (event) => handleRunnerEvent(record.key, event),
          () => {
            const session = stateRef.current.sessions[record.key];
            if (session?.isStreaming) {
              if (
                hasPendingAskUserInMessages(
                  session.messages,
                  session.activeTurnId,
                )
              ) {
                return;
              }
              dispatch({
                type: "STREAM_END",
                key: record.key,
                status: "failed",
              });
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
      };
      runnersRef.current.set(key, record);
      const session = stateRef.current.sessions[key];
      if (session?.activeTurnId) {
        record.client.setResumeState(session.activeTurnId, session.lastSeq);
      }
      record.client.connect();
      return record;
    },
    [handleRunnerEvent],
  );

  const sendThroughRunner = useCallback(
    function dispatchToRunner(key: string, msg: ChatMessage, attempt = 0) {
      const runner = ensureRunner(key);
      if (!runner.client.connected) {
        if (attempt >= 10) {
          console.error("WebSocket failed to connect after retries");
          dispatch({ type: "STREAM_END", key, status: "failed" });
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
        const timerId = setTimeout(() => {
          retryTimersRef.current.delete(timerId);
          dispatchToRunner(key, msg, attempt + 1);
        }, 200);
        retryTimersRef.current.add(timerId);
        return;
      }
      runner.client.send(msg);
    },
    [ensureRunner],
  );

  const loadSession = useCallback(
    async (sessionId: string, signal?: AbortSignal) => {
      const session = await getSession(sessionId, signal);
      const activeTurn = Array.isArray(session.active_turns)
        ? session.active_turns[0]
        : undefined;
      dispatch({
        type: "LOAD_SESSION",
        key: session.session_id || session.id,
        sessionId: session.session_id || session.id,
        title: session.title || "",
        messages: hydrateMessages(session.messages ?? []),
        activeTurnId: activeTurn?.turn_id || activeTurn?.id || null,
        status:
          (session.status as SessionRuntimeStatus | undefined) ||
          (activeTurn ? "running" : "idle"),
        tools: Array.isArray(session.preferences?.tools)
          ? session.preferences.tools
          : [],
        capability: session.preferences?.capability || null,
        knowledgeBases: Array.isArray(session.preferences?.knowledge_bases)
          ? session.preferences.knowledge_bases
          : [],
        llmSelection: asLLMSelection(session.preferences?.llm_selection),
        personaSelection:
          typeof session.preferences?.persona === "string"
            ? session.preferences.persona
            : "",
        // The Settings language is global UI state. Historical sessions may
        // have stale persisted preferences, so new turns follow the current
        // app language rather than the language saved when the session began.
        language: readStoredLanguage(),
        selectedBranches: normalizeSelectedBranches(
          session.preferences?.selected_branches,
        ),
      });
      if (activeTurn?.turn_id || activeTurn?.id) {
        const key = session.session_id || session.id;
        sendThroughRunner(key, {
          type: "subscribe_turn",
          turn_id: activeTurn.turn_id || activeTurn.id,
          after_seq: 0,
        });
      }
    },
    [hydrateMessages, sendThroughRunner],
  );

  useLayoutEffect(() => {
    loadSessionRef.current = loadSession;
  }, [loadSession]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const current = state.selectedKey
      ? state.sessions[state.selectedKey]
      : null;
    writeStoredActiveSessionId(current?.sessionId ?? null);
  }, [state.selectedKey, state.sessions]);

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
  }, []);

  // URL is now the source of truth for session loading.
  // Chat pages load sessions based on URL params; no sessionStorage restore needed.
  // Initialize a draft session so the provider always has a selected key.
  useEffect(() => {
    if (typeof window === "undefined") return;
    if (!state.selectedKey) {
      dispatch({ type: "NEW_SESSION", key: makeDraftKey() });
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Idle timeout: if a streaming session receives no events for the configured
  // window (default 180s, set in Settings > Network), auto-fail it. Read per
  // tick so a settings change applies without remounting.
  useEffect(() => {
    const CHECK_INTERVAL_MS = 10_000;

    const timer = setInterval(() => {
      const timeoutSeconds = readStoredChatResponseTimeout();
      const idleTimeoutMs = timeoutSeconds * 1000;
      const current = stateRef.current;
      for (const [key, session] of Object.entries(current.sessions)) {
        if (!session.isStreaming) continue;
        if (
          hasPendingAskUserInMessages(session.messages, session.activeTurnId)
        ) {
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
  }, []);

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
      const msgAttachments = attachments?.map((a) => ({
        type: a.type,
        filename: a.filename,
        base64: a.base64,
        url: a.url,
        mime_type: a.mime_type,
      }));
      const currentState = stateRef.current;
      let key = currentState.selectedKey;
      if (!key) {
        key = makeDraftKey();
        dispatch({ type: "NEW_SESSION", key });
      }
      const session = currentState.sessions[key] ?? createSessionEntry(key);
      const replaySnapshot = options?.requestSnapshotOverride;
      const effectiveCapability =
        replaySnapshot?.capability ?? session.activeCapability;
      const effectiveTools =
        replaySnapshot?.enabledTools ?? session.enabledTools;
      const effectiveKnowledgeBases =
        replaySnapshot?.knowledgeBases ?? session.knowledgeBases;
      const effectiveLLMSelection =
        replaySnapshot && "llmSelection" in replaySnapshot
          ? (replaySnapshot.llmSelection ?? null)
          : session.llmSelection;
      const effectiveLanguage =
        replaySnapshot?.language ?? readStoredLanguage();
      // Persona resolution: replay snapshot wins; then an explicit per-call
      // persona (quiz follow-up surface); then the session-level preference.
      // Always a string — "" means Default / no persona.
      const effectivePersona =
        replaySnapshot?.persona ?? persona ?? session.personaSelection ?? "";
      const effectiveMemoryReferences =
        replaySnapshot?.memoryReferences ?? memoryReferences;
      const effectiveBookReferences =
        replaySnapshot?.bookReferences ?? options?.bookReferences;
      const effectiveAttachments =
        replaySnapshot?.attachments?.map((a) => ({
          type: a.type,
          filename: a.filename,
          base64: a.base64,
          url: a.url,
          mime_type: a.mime_type,
        })) ?? msgAttachments;
      const effectiveConfig = config ?? replaySnapshot?.config;
      const effectiveNotebookReferences =
        replaySnapshot?.notebookReferences ?? notebookReferences;
      const effectiveHistoryReferences =
        replaySnapshot?.historyReferences ?? historyReferences;
      const effectiveQuestionNotebookReferences =
        replaySnapshot?.questionNotebookReferences ??
        questionNotebookReferences;
      const requestSnapshot: MessageRequestSnapshot = replaySnapshot ?? {
        content,
        capability: effectiveCapability,
        enabledTools: [...effectiveTools],
        knowledgeBases: [...effectiveKnowledgeBases],
        language: effectiveLanguage,
        ...(effectiveAttachments?.length
          ? { attachments: effectiveAttachments }
          : {}),
        ...(effectiveConfig && Object.keys(effectiveConfig).length > 0
          ? { config: effectiveConfig }
          : {}),
        ...(effectiveNotebookReferences?.length
          ? { notebookReferences: effectiveNotebookReferences }
          : {}),
        ...(effectiveHistoryReferences?.length
          ? { historyReferences: [...effectiveHistoryReferences] }
          : {}),
        ...(effectiveQuestionNotebookReferences?.length
          ? {
              questionNotebookReferences: [
                ...effectiveQuestionNotebookReferences,
              ],
            }
          : {}),
        ...(effectiveBookReferences?.length
          ? { bookReferences: effectiveBookReferences }
          : {}),
        ...(effectivePersona ? { persona: effectivePersona } : {}),
        ...(effectiveMemoryReferences?.length
          ? { memoryReferences: [...effectiveMemoryReferences] }
          : {}),
        ...(effectiveLLMSelection
          ? { llmSelection: effectiveLLMSelection }
          : {}),
      };
      // Default the new message's parent to the tip of the currently-
      // visible path so the local chat tree stays connected during
      // streaming. The wire-level ``parent_message_id`` is computed
      // separately further down: only persisted (positive) ids or an
      // explicit ``null`` (root edit) are sent — optimistic negative ids
      // would be meaningless to the server.
      const visible = buildVisiblePath(
        session.messages,
        session.selectedBranches,
      ).messages;
      const tipId = tipMessageId(visible);
      const localParentId =
        options?.parentMessageId !== undefined
          ? options.parentMessageId
          : tipId;
      const wireParentId: number | null | undefined =
        options?.parentMessageId !== undefined
          ? options.parentMessageId
          : tipId !== null && tipId > 0
            ? tipId
            : undefined;
      if (options?.displayUserMessage !== false) {
        dispatch({
          type: "ADD_USER_MSG",
          key,
          content,
          capability: effectiveCapability,
          attachments: effectiveAttachments,
          requestSnapshot,
          parentMessageId: localParentId,
        });
      }
      dispatch({ type: "STREAM_START", key });
      const effectiveTurnConfig =
        options?.persistUserMessage === false
          ? { ...(effectiveConfig || {}), _persist_user_message: false }
          : effectiveConfig;
      sendThroughRunner(key, {
        type: "start_turn",
        content,
        tools: effectiveTools,
        capability: effectiveCapability,
        knowledge_bases: effectiveKnowledgeBases,
        session_id: session.sessionId,
        attachments: effectiveAttachments,
        language: effectiveLanguage,
        ...(effectiveNotebookReferences?.length
          ? { notebook_references: effectiveNotebookReferences }
          : {}),
        ...(effectiveHistoryReferences?.length
          ? { history_references: effectiveHistoryReferences }
          : {}),
        ...(effectiveQuestionNotebookReferences?.length
          ? {
              question_notebook_references: effectiveQuestionNotebookReferences,
            }
          : {}),
        ...(effectiveBookReferences?.length
          ? { book_references: effectiveBookReferences }
          : {}),
        // Always sent (possibly ""): an explicit key is the backend's signal
        // to persist the value into session.preferences — "" clears back to
        // Default. Omitting the key would make the backend fall back to the
        // stored preference, so a clear could never propagate.
        persona: effectivePersona,
        ...(effectiveMemoryReferences?.length
          ? { memory_references: effectiveMemoryReferences }
          : {}),
        ...(effectiveLLMSelection
          ? { llm_selection: effectiveLLMSelection }
          : {}),
        ...(effectiveTurnConfig && Object.keys(effectiveTurnConfig).length > 0
          ? { config: effectiveTurnConfig }
          : {}),
        // Send ``parent_message_id`` only when we have a real (positive)
        // server id to chain under, or when the caller explicitly pinned
        // a parent (incl. ``null`` for editing the session's first
        // message). When the visible tip is still an optimistic
        // negative id, omit the key and let the backend auto-append to
        // the latest persisted row.
        ...(wireParentId !== undefined
          ? { parent_message_id: wireParentId }
          : {}),
      });
    },
    [makeDraftKey, sendThroughRunner],
  );

  const cancelStreamingTurn = useCallback(() => {
    const currentState = stateRef.current;
    const key = currentState.selectedKey;
    if (!key) return;
    const session = currentState.sessions[key];
    if (!session) return;
    const turnId = session.activeTurnId;
    const runner = runnersRef.current.get(key);
    if (runner?.client.connected) {
      if (turnId) {
        runner.client.send({ type: "cancel_turn", turn_id: turnId });
      }
      runner.client.disconnect();
      runnersRef.current.delete(key);
    }
    if (session.isStreaming) {
      dispatch({ type: "STREAM_END", key, status: "cancelled" });
    }
  }, []);

  const submitUserReply = useCallback(
    (
      reply:
        | string
        | {
            text?: string;
            answers?: Array<{ questionId: string; text: string }>;
          },
    ) => {
      const currentState = stateRef.current;
      const key = currentState.selectedKey;
      if (!key) return;
      const session = currentState.sessions[key];
      const turnId = session?.activeTurnId;
      const pendingAskUser = session
        ? hasPendingAskUserInMessages(session.messages, turnId)
        : false;
      // Only meaningful while a turn is live. A paused ask_user turn can be
      // silent long enough for the socket to reconnect, so allow submission
      // whenever the unresolved card and active turn id are still present.
      if (!session || !turnId || (!session.isStreaming && !pendingAskUser)) {
        return;
      }
      const message: import("@/lib/unified-ws").SubmitUserReplyMessage = {
        type: "submit_user_reply",
        turn_id: turnId,
      };
      if (typeof reply === "string") {
        message.text = reply;
      } else {
        if (typeof reply.text === "string") message.text = reply.text;
        if (Array.isArray(reply.answers)) message.answers = reply.answers;
      }
      sendThroughRunner(key, message);
    },
    [sendThroughRunner],
  );

  const regenerateLastMessage = useCallback(() => {
    const currentState = stateRef.current;
    const key = currentState.selectedKey;
    if (!key) return;
    const session = currentState.sessions[key];
    if (!session || !session.sessionId) return;
    if (session.isStreaming) return;
    const lastUser = [...session.messages]
      .reverse()
      .find((m) => m.role === "user");
    if (!lastUser) return;
    // Snapshot the trailing assistant (if any) so we can put it back when the
    // server rejects the request. We intentionally keep events/attachments so
    // the restored bubble round-trips identically.
    const lastMessage = session.messages[session.messages.length - 1];
    if (lastMessage && lastMessage.role === "assistant") {
      pendingRegenerateRef.current.set(key, { ...lastMessage });
    } else {
      pendingRegenerateRef.current.delete(key);
    }
    dispatch({ type: "POP_LAST_ASSISTANT", key });
    dispatch({ type: "STREAM_START", key });
    sendThroughRunner(key, {
      type: "regenerate",
      session_id: session.sessionId,
      overrides: {
        language: readStoredLanguage(),
      },
    });
  }, [sendThroughRunner]);

  const derivedState = useMemo<ChatState>(() => {
    const current = ensureSelectedSession(state);
    return {
      sessionId: current.sessionId,
      sessionTitle: current.sessionTitle,
      enabledTools: current.enabledTools,
      activeCapability: current.activeCapability,
      knowledgeBases: current.knowledgeBases,
      llmSelection: current.llmSelection,
      personaSelection: current.personaSelection,
      messages: current.messages,
      isStreaming: current.isStreaming,
      currentStage: current.currentStage,
      language: current.language,
      selectedBranches: current.selectedBranches,
    };
  }, [state]);

  const sessionStatuses = useMemo<Record<string, SessionStatusSnapshot>>(() => {
    const entries: Record<string, SessionStatusSnapshot> = {};
    for (const session of Object.values(state.sessions)) {
      if (!session.sessionId || session.status !== "running") continue;
      entries[session.sessionId] = {
        sessionId: session.sessionId,
        status: session.status,
        activeTurnId: session.activeTurnId,
        updatedAt: session.updatedAt,
      };
    }
    return entries;
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
    const currentState = stateRef.current;
    const key = currentState.selectedKey;
    if (!key) return;
    const session = currentState.sessions[key];
    const sessionId = session?.sessionId;
    if (!sessionId) return;
    const updated = await updateSessionTitle(sessionId, trimmed);
    dispatch({
      type: "SET_SESSION_TITLE",
      key,
      title: updated.title || trimmed,
    });
  }, []);

  const newSession = useCallback(() => {
    dispatch({ type: "NEW_SESSION", key: makeDraftKey() });
  }, [makeDraftKey]);

  const editMessage = useCallback(
    async (messageId: number, newContent: string) => {
      const trimmed = newContent.trim();
      if (!trimmed) return;
      const currentState = stateRef.current;
      const key = currentState.selectedKey;
      if (!key) return;
      const session = currentState.sessions[key];
      if (!session) return;
      // Edits create a new branch via a fresh turn — block while one is
      // already running so we don't queue against an in-flight stream
      // (matches the delete-turn guard).
      if (session.isStreaming) return;
      const idx = session.messages.findIndex(
        (m) => m.id === messageId && m.role === "user",
      );
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
        const candidate = refreshed?.messages[idx];
        if (
          !candidate ||
          candidate.role !== "user" ||
          typeof candidate.id !== "number" ||
          candidate.id < 0
        ) {
          return;
        }
        original = candidate;
      }
      if (typeof original.id !== "number" || original.id < 0) return;
      const parentId = original.parentMessageId ?? null;
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
      const currentState = stateRef.current;
      const key = currentState.selectedKey;
      if (!key) return;
      const session = currentState.sessions[key];
      if (!session) return;
      const parentKey =
        parentMessageId == null ? "null" : String(parentMessageId);
      dispatch({
        type: "SET_SELECTED_BRANCH",
        key,
        parentKey,
        childId,
      });
      const sessionId = session.sessionId;
      if (!sessionId) return;
      const nextSelections = {
        ...session.selectedBranches,
        [parentKey]: childId,
      };
      // Fire-and-forget — local state is the source of truth for the UI;
      // the server copy only matters for reload-time hydration.
      updateBranchSelection(sessionId, nextSelections).catch((err) => {
        console.warn("Failed to persist branch selection:", err);
      });
    },
    [],
  );

  const deleteTurn = useCallback(
    async (messageId: number) => {
      const currentState = stateRef.current;
      const key = currentState.selectedKey;
      if (!key) return;
      const session = currentState.sessions[key];
      if (!session || !session.sessionId) return;
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
        const realId = refreshed?.messages[origIdx]?.id;
        if (realId == null || realId < 0) return;
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
