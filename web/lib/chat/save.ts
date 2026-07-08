type NotebookSaveMessage = {
  role: "user" | "assistant" | "system";
  content: string;
  capability?: string;
};

type NotebookSavePayload = {
  recordType: "chat";
  title: string;
  userQuery: string;
  output: string;
  metadata?: Record<string, unknown>;
};

type ChatSaveMessage = {
  role: NotebookSaveMessage["role"];
  content: string;
  capability?: string;
};

export function chatNotebookSaveMessages(
  messages: ChatSaveMessage[],
): NotebookSaveMessage[] {
  return messages.map((message) => ({
    role: message.role,
    content: message.content,
    capability: message.capability,
  }));
}

export function chatNotebookSavePayload({
  messages,
  firstUserTitle,
  activeCapability,
  language,
  sessionId,
}: {
  messages: ChatSaveMessage[];
  firstUserTitle: string;
  activeCapability: string | null;
  language: string;
  sessionId: string | null;
}): NotebookSavePayload | null {
  if (!messages.length) return null;
  return {
    recordType: "chat",
    title: firstUserTitle || "Chat Session",
    userQuery: "",
    output: "",
    metadata: {
      source: "chat",
      capability: activeCapability || "chat",
      ui_language: language,
      session_id: sessionId,
      total_message_count: messages.length,
    },
  };
}
