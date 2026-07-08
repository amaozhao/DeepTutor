import type {
  RegenerateMessage,
  SubmitUserReplyMessage,
} from "../../lib/unified-ws";
import { hasPendingAskUserInMessages } from "../../lib/ask-user-state";
import type { Action, MessageItem, SessionEntry } from "./state";

export type AskUserReply =
  | string
  | {
      text?: string;
      answers?: Array<{ questionId: string; text: string }>;
    };

export function buildSubmitUserReplyMessage(
  turnId: string,
  reply: AskUserReply,
): SubmitUserReplyMessage {
  const message: SubmitUserReplyMessage = {
    type: "submit_user_reply",
    turn_id: turnId,
  };
  if (typeof reply === "string") {
    message.text = reply;
  } else {
    if (typeof reply.text === "string") message.text = reply.text;
    if (Array.isArray(reply.answers)) message.answers = reply.answers;
  }
  return message;
}

export function userReplyTurnId(
  session:
    | Pick<SessionEntry, "activeTurnId" | "isStreaming" | "messages">
    | null
    | undefined,
): string | null {
  const turnId = session?.activeTurnId;
  if (!session || !turnId) return null;
  if (session.isStreaming) return turnId;
  return hasPendingAskUserInMessages(session.messages, turnId) ? turnId : null;
}

export function buildRegenerateMessage(
  sessionId: string,
  language: string,
): RegenerateMessage {
  return {
    type: "regenerate",
    session_id: sessionId,
    overrides: { language },
  };
}

export function cancelStreamingAction(
  key: string,
): Extract<Action, { type: "STREAM_END" }> {
  return { type: "STREAM_END", key, status: "cancelled" };
}

export function regenerateStartActions(key: string): Action[] {
  return [
    { type: "POP_LAST_ASSISTANT", key },
    { type: "STREAM_START", key },
  ];
}

export type RegenerateSessionPlan = {
  canRegenerate: boolean;
  restoreMessage?: MessageItem;
};

export function regenerateSessionPlan(
  session:
    | Pick<SessionEntry, "sessionId" | "isStreaming" | "messages">
    | null
    | undefined,
): RegenerateSessionPlan {
  if (!session?.sessionId || session.isStreaming) {
    return { canRegenerate: false };
  }
  if (!session.messages.some((message) => message.role === "user")) {
    return { canRegenerate: false };
  }
  const lastMessage = session.messages[session.messages.length - 1];
  if (lastMessage?.role !== "assistant") {
    return { canRegenerate: true };
  }
  return { canRegenerate: true, restoreMessage: { ...lastMessage } };
}
