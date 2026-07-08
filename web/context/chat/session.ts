import type { SubscribeTurnMessage } from "@/lib/unified-ws";
import {
  asLLMSelection,
  hydrateSessionMessages,
  normalizeSelectedBranches,
} from "@/lib/chat/hydration";
import type { Action, SessionRuntimeStatus } from "@/context/chat/state";

type LoadSessionAction = Extract<Action, { type: "LOAD_SESSION" }>;

export type SessionDetailInput = {
  id: string;
  session_id?: string;
  title?: string;
  status?: string;
  preferences?: {
    capability?: string;
    tools?: string[];
    knowledge_bases?: string[];
    llm_selection?: unknown;
    persona?: string;
    selected_branches?: unknown;
  };
  messages?: Parameters<typeof hydrateSessionMessages>[0];
  active_turns?: Array<{
    id?: string;
    turn_id?: string;
  }>;
};

function sessionKey(session: SessionDetailInput): string {
  return session.session_id || session.id;
}

function activeTurn(session: SessionDetailInput) {
  return Array.isArray(session.active_turns) ? session.active_turns[0] : undefined;
}

export function loadSessionActionFromDetail(
  session: SessionDetailInput,
  language: string,
): LoadSessionAction {
  const turn = activeTurn(session);
  const preferences = session.preferences;
  return {
    type: "LOAD_SESSION",
    key: sessionKey(session),
    sessionId: sessionKey(session),
    title: session.title || "",
    messages: hydrateSessionMessages(session.messages ?? []),
    activeTurnId: turn?.turn_id || turn?.id || null,
    status:
      (session.status as SessionRuntimeStatus | undefined) ||
      (turn ? "running" : "idle"),
    tools: Array.isArray(preferences?.tools) ? preferences.tools : [],
    capability: preferences?.capability || null,
    knowledgeBases: Array.isArray(preferences?.knowledge_bases)
      ? preferences.knowledge_bases
      : [],
    llmSelection: asLLMSelection(preferences?.llm_selection),
    personaSelection:
      typeof preferences?.persona === "string" ? preferences.persona : "",
    language,
    selectedBranches: normalizeSelectedBranches(preferences?.selected_branches),
  };
}

export function subscribeTurnMessageFromDetail(
  session: SessionDetailInput,
): { key: string; message: SubscribeTurnMessage } | null {
  const turn = activeTurn(session);
  const turnId = turn?.turn_id || turn?.id;
  if (!turnId) return null;
  return {
    key: sessionKey(session),
    message: {
      type: "subscribe_turn",
      turn_id: turnId,
      after_seq: 0,
    },
  };
}

export function renameSessionTitleAction({
  key,
  requestedTitle,
  updatedTitle,
}: {
  key: string;
  requestedTitle: string;
  updatedTitle?: string | null;
}): Extract<Action, { type: "SET_SESSION_TITLE" }> {
  return {
    type: "SET_SESSION_TITLE",
    key,
    title: updatedTitle || requestedTitle,
  };
}

export function newSessionAction(
  key: string,
): Extract<Action, { type: "NEW_SESSION" }> {
  return { type: "NEW_SESSION", key };
}

export function initialDraftSessionAction({
  selectedKey,
  makeDraftKey,
}: {
  selectedKey: string | null;
  makeDraftKey: () => string;
}): Extract<Action, { type: "NEW_SESSION" }> | null {
  return selectedKey ? null : newSessionAction(makeDraftKey());
}
