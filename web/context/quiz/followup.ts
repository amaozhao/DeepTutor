import { shouldAppendEventContent } from "@/lib/stream";
import type { StreamEvent } from "@/lib/unified-ws";

export interface FollowupMessage {
  role: "user" | "assistant" | "system";
  content: string;
  /**
   * Stream events that produced this message (assistant turns only).
   * Keeping the full event log on the assistant message lets the
   * follow-up tab render the same inline trace rows the main chat uses.
   */
  events?: StreamEvent[];
}

export interface FollowupThreadState {
  isOpen: boolean;
  input: string;
  isStreaming: boolean;
  currentStage: string;
  sessionId: string | null;
  activeTurnId: string | null;
  messages: FollowupMessage[];
  error: string | null;
}

export interface HydratedFollowupMessage {
  role: "user" | "assistant" | "system";
  content: string;
  events?: StreamEvent[];
}

export function createEmptyThreadState(): FollowupThreadState {
  return {
    isOpen: false,
    input: "",
    isStreaming: false,
    currentStage: "",
    sessionId: null,
    activeTurnId: null,
    messages: [],
    error: null,
  };
}

export function shouldHydrateFollowupThread(
  current: FollowupThreadState | null | undefined,
): boolean {
  return !current || (current.messages.length === 0 && !current.isStreaming);
}

export function followupHydratedState(
  prev: FollowupThreadState,
  sessionId: string,
  messages: HydratedFollowupMessage[],
): FollowupThreadState {
  return {
    ...prev,
    sessionId,
    messages: messages.map((m) => ({
      role: m.role,
      content: m.content,
      events: m.events ?? [],
    })),
  };
}

export type FollowupSessionEventInfo = {
  sessionId: string;
  turnId: string | null;
} | null;

export function followupSessionEventInfo(
  event: StreamEvent,
): FollowupSessionEventInfo {
  if (event.type !== "session") return null;
  const metadata = (event.metadata ?? {}) as {
    session_id?: string;
    turn_id?: string;
  };
  const sessionId = metadata.session_id || event.session_id || "";
  if (!sessionId) return null;
  return {
    sessionId,
    turnId: metadata.turn_id || event.turn_id || null,
  };
}

export function applyFollowupSessionEvent(
  prev: FollowupThreadState,
  info: Exclude<FollowupSessionEventInfo, null>,
): FollowupThreadState {
  return {
    ...prev,
    sessionId: info.sessionId,
    activeTurnId: info.turnId,
  };
}

export function followupDoneState(
  prev: FollowupThreadState,
): FollowupThreadState {
  return {
    ...prev,
    isStreaming: false,
    currentStage: "",
    activeTurnId: null,
  };
}

export function followupFailedState(
  prev: FollowupThreadState,
  error: string,
): FollowupThreadState {
  return {
    ...prev,
    isStreaming: false,
    currentStage: "",
    activeTurnId: null,
    error: prev.error || error,
  };
}

export function followupStartUserTurnState(
  prev: FollowupThreadState,
  content: string,
): FollowupThreadState {
  return {
    ...prev,
    isOpen: true,
    input: "",
    isStreaming: true,
    error: null,
    messages: [...prev.messages, { role: "user", content }],
  };
}

export function followupResumeState(
  prev: FollowupThreadState,
): FollowupThreadState {
  return {
    ...prev,
    isStreaming: true,
    error: null,
  };
}

export function applyFollowupStreamEvent(
  prev: FollowupThreadState,
  event: StreamEvent,
): FollowupThreadState {
  const next = {
    ...prev,
    activeTurnId: event.turn_id || prev.activeTurnId,
  };
  if (event.type === "stage_start") {
    next.currentStage = event.stage;
  } else if (event.type === "stage_end") {
    next.currentStage = "";
  } else if (event.type === "error") {
    next.error = event.content || prev.error;
    const terminal = Boolean(
      ((event.metadata ?? {}) as { turn_terminal?: boolean }).turn_terminal,
    );
    if (terminal) {
      next.isStreaming = false;
      next.currentStage = "";
      next.activeTurnId = null;
    }
  }

  const messages = [...prev.messages];
  let last = messages[messages.length - 1];
  if (!last || last.role !== "assistant") {
    messages.push({ role: "assistant", content: "", events: [event] });
  } else {
    messages[messages.length - 1] = {
      ...last,
      events: [...(last.events ?? []), event],
    };
  }
  last = messages[messages.length - 1];
  if (last && last.role === "assistant" && shouldAppendEventContent(event)) {
    messages[messages.length - 1] = {
      ...last,
      content: `${last.content}${event.content}`,
    };
  }
  next.messages = messages;
  return next;
}
