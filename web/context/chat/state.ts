import { readStoredLanguage } from "../app-shell-storage";
import type { BookReferencePayload } from "../../lib/book-references";
import {
  isNarrationMarker,
  recomputeAnswerContent,
  shouldAppendEventContent,
} from "../../lib/stream";
import { reconcileTurnIds } from "../../lib/turn-reconcile";
import type { LLMSelection, StreamEvent } from "../../lib/unified-ws";

export type SessionRuntimeStatus =
  | "idle"
  | "running"
  | "completed"
  | "failed"
  | "cancelled"
  | "rejected";

export interface OutgoingAttachment {
  type: string;
  url?: string;
  base64?: string;
  filename?: string;
  mime_type?: string;
}

export interface NotebookReferencePayload {
  notebook_id: string;
  record_ids: string[];
}

export type HistoryReferencePayload = string[];

export type QuestionNotebookReferencePayload = number[];

export type MemoryReferencePayload = Array<"summary" | "profile">;

export interface SendMessageOptions {
  displayUserMessage?: boolean;
  persistUserMessage?: boolean;
  requestSnapshotOverride?: MessageRequestSnapshot;
  bookReferences?: BookReferencePayload[];
  /** Edit-branching: when set, the new user message is inserted as a
   *  sibling under this parent rather than appended to the session tail.
   *  ``null`` means "explicitly attach to the session root". */
  parentMessageId?: number | null;
}

export interface ChatState {
  sessionId: string | null;
  sessionTitle: string;
  enabledTools: string[];
  activeCapability: string | null;
  knowledgeBases: string[];
  llmSelection: LLMSelection | null;
  /** Session-level persona preference; "" = Default (no persona). Applies
   *  to every following message until changed (persisted on the session). */
  personaSelection: string;
  messages: MessageItem[];
  isStreaming: boolean;
  currentStage: string;
  language: string;
  /** Edit-branching: keyed by stringified parent_message_id (or "null"
   *  for the root). Empty means "default to latest sibling everywhere". */
  selectedBranches: Record<string, number>;
}

export interface SessionStatusSnapshot {
  sessionId: string;
  status: SessionRuntimeStatus;
  activeTurnId: string | null;
  updatedAt: number;
}

export interface MessageAttachment {
  type: string;
  filename?: string;
  base64?: string;
  url?: string;
  mime_type?: string;
  /** Stable per-attachment id; matches the URL segment served by /api/attachments. */
  id?: string;
  /** Plain-text rendering of office docs, populated by the backend extractor.
   *  Used by the preview drawer to show "what the LLM saw" for binary docs. */
  extracted_text?: string;
  /** Set on files the assistant produced this turn (exec/code_execution
   *  artifacts) rather than files the user uploaded. Rendered as openable
   *  cards under the assistant message. */
  generated?: boolean;
  /** Byte size of the generated file, for the card's subtitle. */
  size_bytes?: number;
}

export interface MessageRequestSnapshot {
  content: string;
  capability?: string | null;
  enabledTools: string[];
  knowledgeBases: string[];
  language: string;
  attachments?: MessageAttachment[];
  config?: Record<string, unknown>;
  notebookReferences?: NotebookReferencePayload[];
  historyReferences?: HistoryReferencePayload;
  questionNotebookReferences?: QuestionNotebookReferencePayload;
  bookReferences?: BookReferencePayload[];
  persona?: string;
  memoryReferences?: MemoryReferencePayload;
  llmSelection?: LLMSelection | null;
}

export interface MessageItem {
  id?: number;
  role: "user" | "assistant" | "system";
  content: string;
  capability?: string;
  events?: StreamEvent[];
  attachments?: MessageAttachment[];
  requestSnapshot?: MessageRequestSnapshot;
  /** Edit-branching: id of the message this row continues. */
  parentMessageId?: number | null;
}

export interface SessionEntry extends ChatState {
  key: string;
  status: SessionRuntimeStatus;
  activeTurnId: string | null;
  lastSeq: number;
  updatedAt: number;
  /** Edit-branching: maps a parent_message_id (stringified, or "null" for
   *  the session root) to the chosen child id at that branch point. */
  selectedBranches: Record<string, number>;
}

export interface ProviderState {
  selectedKey: string | null;
  sessions: Record<string, SessionEntry>;
  sidebarRefreshToken: number;
}

export type Action =
  | { type: "SET_TOOLS"; tools: string[] }
  | { type: "SET_CAPABILITY"; cap: string | null }
  | { type: "SET_KB"; kbs: string[] }
  | { type: "SET_LLM_SELECTION"; selection: LLMSelection | null }
  | { type: "SET_PERSONA_SELECTION"; persona: string }
  | { type: "SET_LANGUAGE"; lang: string }
  | {
      type: "ADD_USER_MSG";
      key: string;
      content: string;
      capability?: string | null;
      attachments?: MessageAttachment[];
      requestSnapshot?: MessageRequestSnapshot;
      parentMessageId?: number | null;
    }
  | { type: "POP_LAST_ASSISTANT"; key: string }
  | { type: "RESTORE_ASSISTANT"; key: string; message: MessageItem }
  | { type: "STREAM_START"; key: string }
  | { type: "STREAM_EVENT"; key: string; event: StreamEvent }
  | {
      type: "STREAM_END";
      key: string;
      status?: SessionRuntimeStatus;
      turnId?: string | null;
    }
  | {
      type: "BIND_SERVER_SESSION";
      key: string;
      sessionId: string;
      turnId?: string | null;
    }
  | {
      type: "LOAD_SESSION";
      key: string;
      sessionId: string;
      title?: string;
      messages: MessageItem[];
      activeTurnId?: string | null;
      status?: SessionRuntimeStatus;
      tools?: string[];
      capability?: string | null;
      knowledgeBases?: string[];
      llmSelection?: LLMSelection | null;
      personaSelection?: string;
      language?: string;
      selectedBranches?: Record<string, number>;
    }
  | { type: "SET_SESSION_TITLE"; key: string; title: string }
  | {
      type: "RECONCILE_TURN";
      key: string;
      turnId?: string | null;
      userMessageId?: number | null;
      assistantMessageId?: number | null;
    }
  | { type: "DELETE_TURN"; key: string; messageId: number }
  | { type: "NEW_SESSION"; key: string }
  | {
      type: "SET_SELECTED_BRANCH";
      key: string;
      parentKey: string;
      childId: number;
    }
  | {
      type: "REPLACE_SELECTED_BRANCHES";
      key: string;
      selectedBranches: Record<string, number>;
    }
  | { type: "BUMP_SIDEBAR_REFRESH" };

export function createSessionEntry(
  key: string,
  sessionId: string | null = null,
): SessionEntry {
  return {
    key,
    sessionId,
    sessionTitle: "",
    enabledTools: [],
    activeCapability: null,
    knowledgeBases: [],
    llmSelection: null,
    personaSelection: "",
    messages: [],
    isStreaming: false,
    currentStage: "",
    language: typeof window === "undefined" ? "en" : readStoredLanguage(),
    status: "idle",
    activeTurnId: null,
    lastSeq: 0,
    updatedAt: Date.now(),
    selectedBranches: {},
  };
}

export function ensureSelectedSession(state: ProviderState): SessionEntry {
  if (state.selectedKey && state.sessions[state.selectedKey]) {
    return state.sessions[state.selectedKey];
  }
  return createSessionEntry("draft");
}

function updateSelectedSession(
  state: ProviderState,
  updater: (session: SessionEntry) => SessionEntry,
): ProviderState {
  const current = ensureSelectedSession(state);
  const key = state.selectedKey || current.key;
  const nextSession = updater(current);
  return {
    ...state,
    selectedKey: key,
    sessions: {
      ...state.sessions,
      [key]: nextSession,
    },
  };
}

function isSameTurnEvent(a: StreamEvent, b: StreamEvent): boolean {
  const aSeq = Number(a.seq || 0);
  const bSeq = Number(b.seq || 0);
  if (aSeq <= 0 || bSeq <= 0 || aSeq !== bSeq) return false;
  const aTurn = a.turn_id || "";
  const bTurn = b.turn_id || "";
  return Boolean(aTurn && bTurn && aTurn === bTurn);
}

export function chatReducer(state: ProviderState, action: Action): ProviderState {
  switch (action.type) {
    case "SET_TOOLS":
      return updateSelectedSession(state, (session) => ({
        ...session,
        enabledTools: action.tools,
      }));
    case "SET_CAPABILITY":
      return updateSelectedSession(state, (session) => ({
        ...session,
        activeCapability: action.cap,
      }));
    case "SET_KB":
      return updateSelectedSession(state, (session) => ({
        ...session,
        knowledgeBases: action.kbs,
      }));
    case "SET_LLM_SELECTION":
      return updateSelectedSession(state, (session) => ({
        ...session,
        llmSelection: action.selection,
      }));
    case "SET_PERSONA_SELECTION":
      return updateSelectedSession(state, (session) => ({
        ...session,
        personaSelection: action.persona,
      }));
    case "SET_LANGUAGE":
      return updateSelectedSession(state, (session) => ({
        ...session,
        language: action.lang,
      }));
    case "ADD_USER_MSG": {
      const session =
        state.sessions[action.key] ?? createSessionEntry(action.key);
      return {
        ...state,
        sessions: {
          ...state.sessions,
          [action.key]: {
            ...session,
            messages: [
              ...session.messages,
              {
                id: -Date.now(),
                role: "user",
                content: action.content,
                capability: action.capability || "",
                parentMessageId:
                  action.parentMessageId === undefined
                    ? null
                    : action.parentMessageId,
                ...(action.attachments?.length
                  ? { attachments: action.attachments }
                  : {}),
                ...(action.requestSnapshot
                  ? { requestSnapshot: action.requestSnapshot }
                  : {}),
              },
            ],
            updatedAt: Date.now(),
          },
        },
      };
    }
    case "POP_LAST_ASSISTANT": {
      const session = state.sessions[action.key];
      if (!session || session.messages.length === 0) return state;
      const last = session.messages[session.messages.length - 1];
      if (last.role !== "assistant") return state;
      return {
        ...state,
        sessions: {
          ...state.sessions,
          [action.key]: {
            ...session,
            messages: session.messages.slice(0, -1),
            updatedAt: Date.now(),
          },
        },
      };
    }
    case "RESTORE_ASSISTANT": {
      // Revert an optimistic POP_LAST_ASSISTANT when the server rejects a
      // regenerate request (e.g. ``regenerate_busy``), so the user doesn't
      // silently lose their last reply.
      const session = state.sessions[action.key];
      if (!session) return state;
      const messages = [...session.messages];
      // Drop any placeholder STREAM_START assistant bubble before restoring.
      while (
        messages.length > 0 &&
        messages[messages.length - 1].role === "assistant" &&
        (messages[messages.length - 1].content ?? "") === "" &&
        (messages[messages.length - 1].events?.length ?? 0) === 0
      ) {
        messages.pop();
      }
      messages.push(action.message);
      return {
        ...state,
        sessions: {
          ...state.sessions,
          [action.key]: {
            ...session,
            messages,
            updatedAt: Date.now(),
          },
        },
      };
    }
    case "STREAM_START": {
      const session =
        state.sessions[action.key] ?? createSessionEntry(action.key);
      const existing = session.messages ?? [];
      // Chain the placeholder assistant onto whatever message currently
      // sits at the tip — this is normally the user row just added by
      // ADD_USER_MSG (possibly an optimistic negative id during an edit).
      const tip = existing.length > 0 ? existing[existing.length - 1] : null;
      return {
        ...state,
        sessions: {
          ...state.sessions,
          [action.key]: {
            ...session,
            isStreaming: true,
            status: "running",
            messages: [
              ...existing,
              {
                id: -Date.now(),
                role: "assistant",
                content: "",
                events: [],
                capability: session.activeCapability || "",
                parentMessageId: tip?.id ?? null,
              },
            ],
            updatedAt: Date.now(),
          },
        },
      };
    }
    case "STREAM_EVENT": {
      // If the session entry has been removed (e.g., BIND_SERVER_SESSION
      // just renamed ``draft_X`` to a real id but a stray event still
      // targets the old key), drop the event rather than synthesise an
      // orphan session with no user message — that would scrub the
      // user's just-sent bubble from view.
      if (!state.sessions[action.key]) return state;
      const session = state.sessions[action.key];
      const msgs = [...session.messages];
      let last = msgs[msgs.length - 1];
      if (last?.role !== "assistant") {
        msgs.push({
          id: -Date.now(),
          role: "assistant",
          content: "",
          events: [],
          capability: session.activeCapability || "",
          parentMessageId: last?.id ?? null,
        });
        last = msgs[msgs.length - 1];
      }
      if (
        (last?.events || []).some((event) =>
          isSameTurnEvent(event, action.event),
        )
      ) {
        return state;
      }
      const events = [...(last?.events || []), action.event];
      let content = last?.content || "";
      if (isNarrationMarker(action.event)) {
        // A round just resolved as narration (preamble before a tool call):
        // drop its already-streamed text from the answer — it stays in the
        // trace. Recomputing is cheap here (only fires per narration round).
        content = recomputeAnswerContent(events);
      } else if (shouldAppendEventContent(action.event)) {
        content += action.event.content;
      }
      const capability = last?.capability || session.activeCapability || "";
      msgs[msgs.length - 1] = {
        ...(last || { role: "assistant", content: "" }),
        content,
        events,
        capability,
      };
      return {
        ...state,
        sessions: {
          ...state.sessions,
          [action.key]: {
            ...session,
            messages: msgs,
            currentStage:
              action.event.type === "stage_start"
                ? action.event.stage
                : action.event.type === "stage_end"
                  ? ""
                  : session.currentStage,
            activeTurnId: action.event.turn_id || session.activeTurnId,
            lastSeq: Math.max(session.lastSeq, action.event.seq || 0),
            updatedAt: Date.now(),
          },
        },
      };
    }
    case "STREAM_END":
      return {
        ...state,
        sessions: {
          ...state.sessions,
          [action.key]: {
            ...(state.sessions[action.key] ?? createSessionEntry(action.key)),
            isStreaming: false,
            currentStage: "",
            status: action.status ?? "completed",
            activeTurnId:
              action.status === "running"
                ? action.turnId ||
                  state.sessions[action.key]?.activeTurnId ||
                  null
                : null,
            updatedAt: Date.now(),
          },
        },
        sidebarRefreshToken: state.sidebarRefreshToken + 1,
      };
    case "BIND_SERVER_SESSION": {
      const current =
        state.sessions[action.key] ?? createSessionEntry(action.key);
      const targetKey = action.sessionId;
      const existing = state.sessions[targetKey];
      const merged: SessionEntry = {
        ...(existing ?? current),
        ...current,
        key: targetKey,
        sessionId: action.sessionId,
        sessionTitle: current.sessionTitle || existing?.sessionTitle || "",
        activeTurnId: action.turnId || current.activeTurnId,
        status: current.isStreaming ? "running" : current.status,
        updatedAt: Date.now(),
      };
      const nextSessions = { ...state.sessions };
      delete nextSessions[action.key];
      nextSessions[targetKey] = merged;
      return {
        ...state,
        selectedKey:
          state.selectedKey === action.key ? targetKey : state.selectedKey,
        sessions: nextSessions,
        sidebarRefreshToken: state.sidebarRefreshToken + 1,
      };
    }
    case "LOAD_SESSION": {
      const existing =
        state.sessions[action.key] ??
        createSessionEntry(action.key, action.sessionId);
      return {
        ...state,
        selectedKey: action.key,
        sessions: {
          ...state.sessions,
          [action.key]: {
            ...existing,
            key: action.key,
            sessionId: action.sessionId,
            sessionTitle:
              action.title !== undefined ? action.title : existing.sessionTitle,
            enabledTools: action.tools ?? existing.enabledTools,
            activeCapability:
              action.capability !== undefined
                ? action.capability
                : existing.activeCapability,
            knowledgeBases: action.knowledgeBases ?? existing.knowledgeBases,
            llmSelection:
              action.llmSelection !== undefined
                ? action.llmSelection
                : existing.llmSelection,
            personaSelection:
              action.personaSelection !== undefined
                ? action.personaSelection
                : existing.personaSelection,
            messages: action.messages,
            isStreaming: (action.status || "idle") === "running",
            currentStage: "",
            activeTurnId: action.activeTurnId || null,
            status: action.status || "idle",
            language: action.language ?? existing.language,
            selectedBranches:
              action.selectedBranches ?? existing.selectedBranches,
            updatedAt: Date.now(),
          },
        },
      };
    }
    case "SET_SESSION_TITLE": {
      const session = state.sessions[action.key];
      if (!session) return state;
      return {
        ...state,
        sessions: {
          ...state.sessions,
          [action.key]: {
            ...session,
            sessionTitle: action.title,
            updatedAt: Date.now(),
          },
        },
        sidebarRefreshToken: state.sidebarRefreshToken + 1,
      };
    }
    case "RECONCILE_TURN": {
      const session = state.sessions[action.key];
      if (!session) return state;
      const result = reconcileTurnIds(
        session.messages,
        session.selectedBranches,
        {
          turnId: action.turnId,
          userMessageId: action.userMessageId,
          assistantMessageId: action.assistantMessageId,
        },
      );
      if (!result.changed) return state;
      return {
        ...state,
        sessions: {
          ...state.sessions,
          [action.key]: {
            ...session,
            messages: result.messages,
            selectedBranches: result.selectedBranches,
            updatedAt: Date.now(),
          },
        },
      };
    }
    case "SET_SELECTED_BRANCH": {
      const session = state.sessions[action.key];
      if (!session) return state;
      return {
        ...state,
        sessions: {
          ...state.sessions,
          [action.key]: {
            ...session,
            selectedBranches: {
              ...session.selectedBranches,
              [action.parentKey]: action.childId,
            },
            updatedAt: Date.now(),
          },
        },
      };
    }
    case "REPLACE_SELECTED_BRANCHES": {
      const session = state.sessions[action.key];
      if (!session) return state;
      return {
        ...state,
        sessions: {
          ...state.sessions,
          [action.key]: {
            ...session,
            selectedBranches: { ...action.selectedBranches },
            updatedAt: Date.now(),
          },
        },
      };
    }
    case "DELETE_TURN": {
      const session = state.sessions[action.key];
      if (!session) return state;
      const idx = session.messages.findIndex((m) => m.id === action.messageId);
      if (idx === -1) return state;
      const msg = session.messages[idx];
      const toRemove = new Set<number>();
      toRemove.add(idx);
      if (msg.role === "user") {
        if (
          idx + 1 < session.messages.length &&
          session.messages[idx + 1].role === "assistant"
        ) {
          toRemove.add(idx + 1);
        }
      } else if (msg.role === "assistant") {
        if (idx - 1 >= 0 && session.messages[idx - 1].role === "user") {
          toRemove.add(idx - 1);
        }
      }
      const nextMessages = session.messages.filter((_, i) => !toRemove.has(i));
      return {
        ...state,
        sessions: {
          ...state.sessions,
          [action.key]: {
            ...session,
            messages: nextMessages,
            isStreaming: false,
            status: "idle",
            updatedAt: Date.now(),
          },
        },
        sidebarRefreshToken: state.sidebarRefreshToken + 1,
      };
    }
    case "BUMP_SIDEBAR_REFRESH":
      return {
        ...state,
        sidebarRefreshToken: state.sidebarRefreshToken + 1,
      };
    case "NEW_SESSION": {
      const MAX_CACHED_SESSIONS = 20;
      let nextSessions = {
        ...state.sessions,
        [action.key]: createSessionEntry(action.key),
      };
      const keys = Object.keys(nextSessions);
      if (keys.length > MAX_CACHED_SESSIONS) {
        const evictable = keys
          .filter(
            (k) => k !== action.key && nextSessions[k].status !== "running",
          )
          .sort(
            (a, b) => nextSessions[a].updatedAt - nextSessions[b].updatedAt,
          );
        const toRemove = evictable.slice(0, keys.length - MAX_CACHED_SESSIONS);
        for (const k of toRemove) delete nextSessions[k];
      }
      return { ...state, selectedKey: action.key, sessions: nextSessions };
    }
    default:
      return state;
  }
}

export const initialState: ProviderState = {
  selectedKey: null,
  sessions: {},
  sidebarRefreshToken: 0,
};
