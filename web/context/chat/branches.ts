import type { Action, MessageItem } from "@/context/chat/state";
import { buildVisiblePath, tipMessageId } from "@/lib/message-branches";

export type NextMessageParentIds = {
  localParentId: number | null;
  wireParentId?: number | null;
};

export function nextMessageParentIds({
  explicitParentId,
  messages,
  selectedBranches,
}: {
  explicitParentId?: number | null;
  messages: MessageItem[];
  selectedBranches: Record<string, number>;
}): NextMessageParentIds {
  if (explicitParentId !== undefined) {
    return {
      localParentId: explicitParentId,
      wireParentId: explicitParentId,
    };
  }
  const visible = buildVisiblePath(messages, selectedBranches).messages;
  const tipId = tipMessageId(visible);
  return {
    localParentId: tipId,
    ...(tipId !== null && tipId > 0 ? { wireParentId: tipId } : {}),
  };
}

export function branchParentKey(parentMessageId: number | null): string {
  return parentMessageId == null ? "null" : String(parentMessageId);
}

export function branchSwitchPlan({
  key,
  parentMessageId,
  childId,
  selectedBranches,
}: {
  key: string;
  parentMessageId: number | null;
  childId: number;
  selectedBranches: Record<string, number>;
}): {
  action: Extract<Action, { type: "SET_SELECTED_BRANCH" }>;
  selectedBranches: Record<string, number>;
} {
  const parentKey = branchParentKey(parentMessageId);
  return {
    action: {
      type: "SET_SELECTED_BRANCH",
      key,
      parentKey,
      childId,
    },
    selectedBranches: {
      ...selectedBranches,
      [parentKey]: childId,
    },
  };
}

export function userMessageIndexById(
  messages: MessageItem[],
  messageId: number,
): number {
  return messages.findIndex(
    (message) => message.id === messageId && message.role === "user",
  );
}

export function persistedMessageIdAt(
  messages: MessageItem[] | undefined,
  index: number,
  role?: MessageItem["role"],
): number | null {
  const candidate = messages?.[index];
  if (!candidate || (role && candidate.role !== role)) return null;
  return typeof candidate.id === "number" && candidate.id >= 0
    ? candidate.id
    : null;
}

export function editParentId(message: MessageItem): number | null {
  return message.parentMessageId ?? null;
}
