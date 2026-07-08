import test from "node:test";
import assert from "node:assert/strict";

import {
  applyRunnerResumeState,
  cancelRunnerTurn,
  cleanupRunnersAndTimers,
  doneStreamEndAction,
  effectiveRunnerKey,
  ensureRunner,
  eventStatus,
  isRegenerateRejection,
  moveRunner,
  runnerClosedFailedAction,
  runnerConnectionFailedAction,
  runnerSendState,
  scheduleRunnerDisconnect,
  scheduleRunnerRetry,
  sessionBindAction,
  sessionEventIds,
  sessionMetaAction,
  sessionMetaTitle,
  shouldFailClosedRunner,
  terminalErrorActions,
  terminalErrorInfo,
  type ChatRunnerMap,
} from "../../../context/chat/transport";
import type { StreamEvent } from "../../../lib/unified-ws";

function event(partial: Partial<StreamEvent>): StreamEvent {
  return {
    type: "content",
    source: "server",
    stage: "",
    content: "",
    metadata: {},
    timestamp: 1,
    ...partial,
  };
}

test("moveRunner renames the stored runner key in place", () => {
  const runners: ChatRunnerMap = new Map([
    ["draft", { key: "draft", client: {} as never }],
  ]);

  moveRunner(runners, "draft", "session-1");

  assert.equal(runners.has("draft"), false);
  assert.equal(runners.get("session-1")?.key, "session-1");
  assert.equal(effectiveRunnerKey(runners, "draft"), "draft");
  assert.equal(effectiveRunnerKey(runners, "session-1"), "session-1");
});

test("ensureRunner creates, stores, resumes, and connects new runners", () => {
  const calls: unknown[] = [];
  const runners: ChatRunnerMap = new Map();
  const runner = ensureRunner(
    runners,
    "session-1",
    { activeTurnId: "turn-1", lastSeq: 7 },
    (record) =>
      ({
        connected: false,
        connect: () => calls.push(["connect", record.key]),
        setResumeState: (turnId: string | null, seq: number) =>
          calls.push(["resume", turnId, seq]),
      }) as never,
  );

  assert.equal(runner.key, "session-1");
  assert.equal(runners.get("session-1"), runner);
  assert.deepEqual(calls, [
    ["resume", "turn-1", 7],
    ["connect", "session-1"],
  ]);
});

test("ensureRunner reuses existing runners and reconnects when needed", () => {
  const calls: unknown[] = [];
  const existing = {
    key: "session-1",
    client: {
      connected: false,
      connect: () => calls.push(["connect"]),
      setResumeState: (turnId: string | null, seq: number) =>
        calls.push(["resume", turnId, seq]),
    } as never,
  };
  const runners: ChatRunnerMap = new Map([["session-1", existing]]);

  const runner = ensureRunner(
    runners,
    "session-1",
    { activeTurnId: null, lastSeq: 0 },
    () => {
      throw new Error("should not create");
    },
  );

  assert.equal(runner, existing);
  assert.deepEqual(calls, [
    ["resume", null, 0],
    ["connect"],
  ]);
});

test("applyRunnerResumeState forwards the active turn cursor", () => {
  const calls: unknown[] = [];
  applyRunnerResumeState(
    {
      key: "session-1",
      client: {
        setResumeState: (turnId: string | null, seq: number) => {
          calls.push([turnId, seq]);
        },
      } as never,
    },
    { activeTurnId: "turn-1", lastSeq: 7 },
  );
  applyRunnerResumeState(
    {
      key: "session-1",
      client: {
        setResumeState: (turnId: string | null, seq: number) => {
          calls.push([turnId, seq]);
        },
      } as never,
    },
    null,
  );

  assert.deepEqual(calls, [["turn-1", 7]]);
});

test("cancelRunnerTurn sends cancel, disconnects, and removes connected runners", () => {
  const calls: unknown[] = [];
  const runners: ChatRunnerMap = new Map([
    [
      "session-1",
      {
        key: "session-1",
        client: {
          connected: true,
          send: (message: unknown) => calls.push(["send", message]),
          disconnect: () => calls.push(["disconnect"]),
        } as never,
      },
    ],
  ]);

  assert.equal(cancelRunnerTurn(runners, "session-1", "turn-1"), true);
  assert.deepEqual(calls, [
    ["send", { type: "cancel_turn", turn_id: "turn-1" }],
    ["disconnect"],
  ]);
  assert.equal(runners.has("session-1"), false);
});

test("cancelRunnerTurn ignores missing or disconnected runners", () => {
  const runners: ChatRunnerMap = new Map([
    [
      "session-1",
      {
        key: "session-1",
        client: { connected: false } as never,
      },
    ],
  ]);

  assert.equal(cancelRunnerTurn(runners, "missing", "turn-1"), false);
  assert.equal(cancelRunnerTurn(runners, "session-1", "turn-1"), false);
  assert.equal(runners.has("session-1"), true);
});

test("scheduleRunnerDisconnect removes runner and delays disconnect", () => {
  const calls: unknown[] = [];
  const runners: ChatRunnerMap = new Map([
    [
      "session-1",
      {
        key: "session-1",
        client: {
          disconnect: () => calls.push(["disconnect"]),
        } as never,
      },
    ],
  ]);

  assert.equal(
    scheduleRunnerDisconnect(runners, "session-1", 15000, (callback, delay) => {
      calls.push(["schedule", delay]);
      callback();
    }),
    true,
  );
  assert.deepEqual(calls, [["schedule", 15000], ["disconnect"]]);
  assert.equal(runners.has("session-1"), false);
  assert.equal(
    scheduleRunnerDisconnect(runners, "missing", 15000, () => {}),
    false,
  );
});

test("scheduleRunnerRetry tracks and clears retry timers", () => {
  const timers = new Set<number>();
  const calls: string[] = [];
  const scheduled: Array<() => void> = [];

  const timerId = scheduleRunnerRetry(
    timers as never,
    () => calls.push("retry"),
    200,
    (callback, delay) => {
      assert.equal(delay, 200);
      scheduled.push(callback);
      return 42 as never;
    },
  );

  assert.equal(timerId, 42);
  assert.deepEqual([...timers], [42]);
  scheduled[0]();
  assert.deepEqual([...timers], []);
  assert.deepEqual(calls, ["retry"]);
});

test("cleanupRunnersAndTimers disconnects runners and clears retry timers", () => {
  const calls: unknown[] = [];
  const runners: ChatRunnerMap = new Map([
    [
      "a",
      {
        key: "a",
        client: { disconnect: () => calls.push(["disconnect", "a"]) } as never,
      },
    ],
    [
      "b",
      {
        key: "b",
        client: { disconnect: () => calls.push(["disconnect", "b"]) } as never,
      },
    ],
  ]);
  const timers = new Set([1, 2]) as never;

  cleanupRunnersAndTimers(runners, timers, (timerId) =>
    calls.push(["clear", timerId]),
  );

  assert.deepEqual(calls, [
    ["disconnect", "a"],
    ["disconnect", "b"],
    ["clear", 1],
    ["clear", 2],
  ]);
  assert.equal(runners.size, 0);
  assert.equal((timers as Set<number>).size, 0);
});

test("runnerSendState classifies connected, retry, and failed attempts", () => {
  assert.equal(
    runnerSendState({ connected: true, attempt: 10, maxAttempts: 10 }),
    "send",
  );
  assert.equal(
    runnerSendState({ connected: false, attempt: 9, maxAttempts: 10 }),
    "retry",
  );
  assert.equal(
    runnerSendState({ connected: false, attempt: 10, maxAttempts: 10 }),
    "failed",
  );
});

test("runnerConnectionFailedAction marks the stream failed", () => {
  assert.deepEqual(runnerConnectionFailedAction("session-1"), {
    type: "STREAM_END",
    key: "session-1",
    status: "failed",
  });
  assert.deepEqual(runnerClosedFailedAction("session-1"), {
    type: "STREAM_END",
    key: "session-1",
    status: "failed",
  });
});

test("doneStreamEndAction normalizes done status", () => {
  assert.deepEqual(
    doneStreamEndAction("session-1", event({ type: "done", turn_id: "t1" })),
    {
      type: "STREAM_END",
      key: "session-1",
      status: "completed",
      turnId: "t1",
    },
  );
  assert.deepEqual(
    doneStreamEndAction(
      "session-1",
      event({ type: "done", metadata: { status: "cancelled" } }),
    ),
    {
      type: "STREAM_END",
      key: "session-1",
      status: "cancelled",
      turnId: null,
    },
  );
});

test("session metadata helpers prefer metadata over event fields", () => {
  const ids = sessionEventIds(
    event({
      type: "session",
      session_id: "event-session",
      turn_id: "event-turn",
      metadata: { session_id: "meta-session", turn_id: "meta-turn" },
    }),
  );

  assert.deepEqual(ids, {
    sessionId: "meta-session",
    turnId: "meta-turn",
  });
  assert.deepEqual(
    sessionBindAction("draft", event({ type: "session", metadata: {} })),
    null,
  );
  assert.deepEqual(
    sessionBindAction(
      "draft",
      event({
        type: "session",
        session_id: "event-session",
        metadata: { session_id: "meta-session", turn_id: "meta-turn" },
      }),
    ),
    {
      type: "BIND_SERVER_SESSION",
      key: "draft",
      sessionId: "meta-session",
      turnId: "meta-turn",
    },
  );
  assert.equal(
    sessionMetaTitle(
      event({ type: "session_meta", metadata: { title: " T " } }),
    ),
    "T",
  );
});

test("terminal error helpers normalize status and regenerate reasons", () => {
  const info = terminalErrorInfo(
    event({
      type: "error",
      metadata: {
        turn_terminal: true,
        reason: "regenerate_busy",
        status: "rejected",
      },
    }),
  );

  assert.deepEqual(info, {
    terminal: true,
    reason: "regenerate_busy",
    status: "rejected",
  });
  assert.equal(isRegenerateRejection(info.reason), true);
  assert.equal(eventStatus(event({ metadata: {} }), "completed"), "completed");
});

test("sessionMetaAction updates title or bumps sidebar", () => {
  assert.deepEqual(
    sessionMetaAction(
      "s1",
      event({ type: "session_meta", metadata: { title: " New title " } }),
    ),
    { type: "SET_SESSION_TITLE", key: "s1", title: "New title" },
  );
  assert.deepEqual(
    sessionMetaAction("s1", event({ type: "session_meta", metadata: {} })),
    { type: "BUMP_SIDEBAR_REFRESH" },
  );
});

test("terminalErrorActions restores rejected regenerate placeholders", () => {
  const restore = { role: "assistant" as const, content: "old answer" };
  assert.deepEqual(
    terminalErrorActions(
      "s1",
      event({
        type: "error",
        turn_id: "turn-1",
        metadata: {
          turn_terminal: true,
          reason: "regenerate_busy",
          status: "rejected",
        },
      }),
      restore,
    ),
    [
      { type: "RESTORE_ASSISTANT", key: "s1", message: restore },
      {
        type: "STREAM_END",
        key: "s1",
        status: "rejected",
        turnId: "turn-1",
      },
    ],
  );
});

test("terminalErrorActions ignores non-terminal errors", () => {
  assert.deepEqual(
    terminalErrorActions(
      "s1",
      event({ type: "error", metadata: { turn_terminal: false } }),
    ),
    [],
  );
});

test("shouldFailClosedRunner only fails active streams without pending ask_user", () => {
  const askUser = event({
    type: "tool_result",
    turn_id: "turn-1",
    metadata: {
      tool_call_id: "call-1",
      tool_metadata: { ask_user: { questions: [{ id: "q", prompt: "Q?" }] } },
    },
  });

  assert.equal(shouldFailClosedRunner(null), false);
  assert.equal(
    shouldFailClosedRunner({
      isStreaming: false,
      activeTurnId: "turn-1",
      messages: [],
    }),
    false,
  );
  assert.equal(
    shouldFailClosedRunner({
      isStreaming: true,
      activeTurnId: "turn-1",
      messages: [],
    }),
    true,
  );
  assert.equal(
    shouldFailClosedRunner({
      isStreaming: true,
      activeTurnId: "turn-1",
      messages: [{ role: "assistant", content: "", events: [askUser] }],
    }),
    false,
  );
});
