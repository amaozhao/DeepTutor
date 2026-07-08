import {
  ensureSelectedSession,
  type ChatState,
  type ProviderState,
  type SessionEntry,
  type SessionStatusSnapshot,
} from "./state";

export type SelectedSessionRecord = {
  key: string;
  session: SessionEntry;
};

export function selectedSessionRecord(
  state: ProviderState,
): SelectedSessionRecord | null {
  const key = state.selectedKey;
  if (!key) return null;
  const session = state.sessions[key];
  return session ? { key, session } : null;
}

export function selectedChatState(state: ProviderState): ChatState {
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
}

export function runningSessionStatuses(
  sessions: ProviderState["sessions"],
): Record<string, SessionStatusSnapshot> {
  const entries: Record<string, SessionStatusSnapshot> = {};
  for (const session of Object.values(sessions)) {
    if (!session.sessionId || session.status !== "running") continue;
    entries[session.sessionId] = {
      sessionId: session.sessionId,
      status: session.status,
      activeTurnId: session.activeTurnId,
      updatedAt: session.updatedAt,
    };
  }
  return entries;
}
