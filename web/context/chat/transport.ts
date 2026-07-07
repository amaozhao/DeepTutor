import type { StreamEvent, UnifiedWSClient } from "../../lib/unified-ws";
import type { SessionRuntimeStatus } from "./state";

export interface ChatRunner {
  key: string;
  client: UnifiedWSClient;
}

export type ChatRunnerMap = Map<string, ChatRunner>;

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
