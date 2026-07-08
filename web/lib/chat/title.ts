type MessageLike = {
  role: string;
  content: string;
};

export function firstUserMessageTitle(messages: readonly MessageLike[]): string {
  return (
    messages
      .find((message) => message.role === "user")
      ?.content.trim()
      .replace(/\s+/g, " ")
      .slice(0, 80) || ""
  );
}

export function resolveSessionTitle(
  persistedTitle: string,
  firstUserTitle: string,
  fallbackTitle: string,
): string {
  return persistedTitle.trim() || firstUserTitle || fallbackTitle;
}

type CommitInput = {
  canRename: boolean;
  displayTitle: string;
  draftTitle: string;
  persistedTitle: string;
};

export type SessionTitleCommitDecision =
  | { type: "close"; draftTitle: string }
  | { type: "save"; title: string };

export function decideSessionTitleCommit({
  canRename,
  displayTitle,
  draftTitle,
  persistedTitle,
}: CommitInput): SessionTitleCommitDecision {
  const nextTitle = draftTitle.trim();
  if (!nextTitle) return { type: "close", draftTitle: displayTitle };
  if (!canRename || nextTitle === persistedTitle.trim()) {
    return { type: "close", draftTitle: nextTitle };
  }
  return { type: "save", title: nextTitle };
}
