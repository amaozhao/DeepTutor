import type { StreamEvent, UnifiedWSClient } from "../../lib/unified-ws";
import { hasPendingAskUserInMessages } from "../../lib/ask-user-state";
import type { Action, MessageItem, SessionRuntimeStatus } from "./state";

type RunnerClient = Pick<
  UnifiedWSClient,
  | "connected"
  | "connect"
  | "disconnect"
  | "send"
  | "setResumeState"
>;

export interface ChatRunner {
  key: string;
  client: RunnerClient;
}

export type ChatRunnerMap = Map<string, ChatRunner>;

export type RetryTimerId = ReturnType<typeof setTimeout>;
export type RetryTimerSet = Set<RetryTimerId>;

export function moveRunner(
  runners: ChatRunnerMap,
  oldKey: string,
  newKey: string,
): void {
  if (oldKey === newKey) return;
  const runner = runners.get(oldKey);
  if (!runner) return;
  runners.delete(oldKey);
  runner.key = newKey;
  runners.set(newKey, runner);
}

export function effectiveRunnerKey(
  runners: ChatRunnerMap,
  runnerKey: string,
): string {
  return runners.get(runnerKey)?.key || runnerKey;
}

export function ensureRunner(
  runners: ChatRunnerMap,
  key: string,
  session:
    | {
        activeTurnId: string | null;
        lastSeq: number;
      }
    | null
    | undefined,
  createClient: (record: ChatRunner) => RunnerClient,
): ChatRunner {
  const existing = runners.get(key);
  if (existing) {
    applyRunnerResumeState(existing, session);
    if (!existing.client.connected) existing.client.connect();
    return existing;
  }
  const record = { key, client: null as unknown as RunnerClient };
  record.client = createClient(record);
  runners.set(key, record);
  applyRunnerResumeState(record, session);
  record.client.connect();
  return record;
}

export function applyRunnerResumeState(
  runner: ChatRunner,
  session:
    | {
        activeTurnId: string | null;
        lastSeq: number;
      }
    | null
    | undefined,
): void {
  if (!session) return;
  runner.client.setResumeState(session.activeTurnId, session.lastSeq);
}

export function cancelRunnerTurn(
  runners: ChatRunnerMap,
  key: string,
  turnId?: string | null,
): boolean {
  const runner = runners.get(key);
  if (!runner?.client.connected) return false;
  if (turnId) runner.client.send({ type: "cancel_turn", turn_id: turnId });
  runner.client.disconnect();
  runners.delete(key);
  return true;
}

export function scheduleRunnerDisconnect(
  runners: ChatRunnerMap,
  key: string,
  delayMs: number,
  schedule: (callback: () => void, delayMs: number) => void,
): boolean {
  const runner = runners.get(key);
  if (!runner) return false;
  runners.delete(key);
  schedule(() => {
    runner.client.disconnect();
  }, delayMs);
  return true;
}

export function scheduleRunnerRetry(
  timers: RetryTimerSet,
  retry: () => void,
  delayMs: number,
  schedule: (callback: () => void, delayMs: number) => RetryTimerId,
): RetryTimerId {
  const timerId = schedule(() => {
    timers.delete(timerId);
    retry();
  }, delayMs);
  timers.add(timerId);
  return timerId;
}

export function cleanupRunnersAndTimers(
  runners: ChatRunnerMap,
  timers: RetryTimerSet,
  clearTimer: (timerId: RetryTimerId) => void,
): void {
  runners.forEach(({ client }) => client.disconnect());
  runners.clear();
  timers.forEach((id) => clearTimer(id));
  timers.clear();
}

export type RunnerSendState = "send" | "retry" | "failed";

export function runnerSendState({
  connected,
  attempt,
  maxAttempts,
}: {
  connected: boolean;
  attempt: number;
  maxAttempts: number;
}): RunnerSendState {
  if (connected) return "send";
  return attempt >= maxAttempts ? "failed" : "retry";
}

export function runnerConnectionFailedAction(
  key: string,
): Extract<Action, { type: "STREAM_END" }> {
  return { type: "STREAM_END", key, status: "failed" };
}

export function runnerClosedFailedAction(
  key: string,
): Extract<Action, { type: "STREAM_END" }> {
  return { type: "STREAM_END", key, status: "failed" };
}

export function doneStreamEndAction(
  key: string,
  event: StreamEvent,
): Extract<Action, { type: "STREAM_END" }> {
  return {
    type: "STREAM_END",
    key,
    status: eventStatus(event, "completed"),
    turnId: event.turn_id || null,
  };
}

export function sessionBindAction(
  key: string,
  event: StreamEvent,
): Extract<Action, { type: "BIND_SERVER_SESSION" }> | null {
  const { sessionId, turnId } = sessionEventIds(event);
  if (!sessionId) return null;
  return {
    type: "BIND_SERVER_SESSION",
    key,
    sessionId,
    turnId,
  };
}

export function sessionEventIds(event: StreamEvent): {
  sessionId: string;
  turnId: string | null;
} {
  const metadata = event.metadata as {
    session_id?: string;
    turn_id?: string;
  };
  return {
    sessionId: metadata.session_id || event.session_id || "",
    turnId: metadata.turn_id || event.turn_id || null,
  };
}

export function sessionMetaTitle(event: StreamEvent): string {
  return String((event.metadata as { title?: string }).title || "").trim();
}

export function eventStatus(
  event: StreamEvent,
  fallback: SessionRuntimeStatus,
): SessionRuntimeStatus {
  return (
    (String((event.metadata as { status?: string }).status || fallback) as
      | SessionRuntimeStatus
      | "") || fallback
  );
}

export function terminalErrorInfo(event: StreamEvent): {
  terminal: boolean;
  reason: string;
  status: SessionRuntimeStatus;
} {
  const metadata = event.metadata as {
    turn_terminal?: boolean;
    reason?: string;
    status?: string;
  };
  return {
    terminal: event.type === "error" && Boolean(metadata.turn_terminal),
    reason: String(metadata.reason || ""),
    status: eventStatus(event, "failed"),
  };
}

export function isRegenerateRejection(reason: string): boolean {
  return reason === "regenerate_busy" || reason === "nothing_to_regenerate";
}

export function sessionMetaAction(
  key: string,
  event: StreamEvent,
): Extract<Action, { type: "SET_SESSION_TITLE" | "BUMP_SIDEBAR_REFRESH" }> {
  const title = sessionMetaTitle(event);
  return title
    ? { type: "SET_SESSION_TITLE", key, title }
    : { type: "BUMP_SIDEBAR_REFRESH" };
}

export function terminalErrorActions(
  key: string,
  event: StreamEvent,
  restoreMessage?: MessageItem,
): Action[] {
  const errorInfo = terminalErrorInfo(event);
  if (!errorInfo.terminal) return [];
  const actions: Action[] = [];
  if (restoreMessage && isRegenerateRejection(errorInfo.reason)) {
    actions.push({
      type: "RESTORE_ASSISTANT",
      key,
      message: restoreMessage,
    });
  }
  actions.push({
    type: "STREAM_END",
    key,
    status: errorInfo.status,
    turnId: event.turn_id || null,
  });
  return actions;
}

export function shouldFailClosedRunner(
  session:
    | {
        isStreaming: boolean;
        activeTurnId: string | null;
        messages: MessageItem[];
      }
    | null
    | undefined,
): boolean {
  if (!session?.isStreaming) return false;
  return !hasPendingAskUserInMessages(session.messages, session.activeTurnId);
}
