import type { BookReferencePayload } from "../../lib/book-references";
import type { ChatMessage } from "../../lib/unified-ws";
import type {
  HistoryReferencePayload,
  MemoryReferencePayload,
  MessageRequestSnapshot,
  NotebookReferencePayload,
  OutgoingAttachment,
  QuestionNotebookReferencePayload,
  SendMessageOptions,
  SessionEntry,
  Action,
} from "./state";

type RequestInput = {
  content: string;
  attachments?: OutgoingAttachment[];
  config?: Record<string, unknown>;
  notebookReferences?: NotebookReferencePayload[];
  historyReferences?: HistoryReferencePayload;
  options?: SendMessageOptions;
  questionNotebookReferences?: QuestionNotebookReferencePayload;
  persona?: string;
  memoryReferences?: MemoryReferencePayload;
  session: SessionEntry;
  language: string;
  wireParentId?: number | null;
};

type EffectiveChatRequest = {
  capability: string | null;
  tools: string[];
  knowledgeBases: string[];
  language: string;
  persona: string;
  attachments?: OutgoingAttachment[];
  requestSnapshot: MessageRequestSnapshot;
  turnMessage: ChatMessage & { memory_references?: MemoryReferencePayload };
};

export function chatStartTurnActions({
  key,
  content,
  request,
  parentMessageId,
  displayUserMessage,
}: {
  key: string;
  content: string;
  request: Pick<
    EffectiveChatRequest,
    "capability" | "attachments" | "requestSnapshot"
  >;
  parentMessageId: number | null;
  displayUserMessage?: boolean;
}): Action[] {
  const actions: Action[] = [];
  if (displayUserMessage !== false) {
    actions.push({
      type: "ADD_USER_MSG",
      key,
      content,
      capability: request.capability,
      attachments: request.attachments,
      requestSnapshot: request.requestSnapshot,
      parentMessageId,
    });
  }
  actions.push({ type: "STREAM_START", key });
  return actions;
}

function normalizeOutgoingAttachments(
  attachments?: OutgoingAttachment[],
): OutgoingAttachment[] | undefined {
  return attachments?.map((attachment) => ({
    type: attachment.type,
    filename: attachment.filename,
    base64: attachment.base64,
    url: attachment.url,
    mime_type: attachment.mime_type,
  }));
}

export function buildEffectiveChatRequest({
  content,
  attachments,
  config,
  notebookReferences,
  historyReferences,
  options,
  questionNotebookReferences,
  persona,
  memoryReferences,
  session,
  language,
  wireParentId,
}: RequestInput): EffectiveChatRequest {
  const msgAttachments = normalizeOutgoingAttachments(attachments);
  const replaySnapshot = options?.requestSnapshotOverride;
  const capability = replaySnapshot?.capability ?? session.activeCapability;
  const tools = replaySnapshot?.enabledTools ?? session.enabledTools;
  const knowledgeBases =
    replaySnapshot?.knowledgeBases ?? session.knowledgeBases;
  const llmSelection =
    replaySnapshot && "llmSelection" in replaySnapshot
      ? (replaySnapshot.llmSelection ?? null)
      : session.llmSelection;
  const effectiveLanguage = replaySnapshot?.language ?? language;
  const effectivePersona =
    replaySnapshot?.persona ?? persona ?? session.personaSelection ?? "";
  const effectiveMemoryReferences =
    replaySnapshot?.memoryReferences ?? memoryReferences;
  const effectiveBookReferences =
    replaySnapshot?.bookReferences ?? options?.bookReferences;
  const effectiveAttachments =
    normalizeOutgoingAttachments(replaySnapshot?.attachments) ?? msgAttachments;
  const effectiveConfig = config ?? replaySnapshot?.config;
  const effectiveNotebookReferences =
    replaySnapshot?.notebookReferences ?? notebookReferences;
  const effectiveHistoryReferences =
    replaySnapshot?.historyReferences ?? historyReferences;
  const effectiveQuestionNotebookReferences =
    replaySnapshot?.questionNotebookReferences ?? questionNotebookReferences;
  const requestSnapshot: MessageRequestSnapshot = replaySnapshot ?? {
    content,
    capability,
    enabledTools: [...tools],
    knowledgeBases: [...knowledgeBases],
    language: effectiveLanguage,
    ...(effectiveAttachments?.length ? { attachments: effectiveAttachments } : {}),
    ...(effectiveConfig && Object.keys(effectiveConfig).length > 0
      ? { config: effectiveConfig }
      : {}),
    ...(effectiveNotebookReferences?.length
      ? { notebookReferences: effectiveNotebookReferences }
      : {}),
    ...(effectiveHistoryReferences?.length
      ? { historyReferences: [...effectiveHistoryReferences] }
      : {}),
    ...(effectiveQuestionNotebookReferences?.length
      ? { questionNotebookReferences: [...effectiveQuestionNotebookReferences] }
      : {}),
    ...(effectiveBookReferences?.length
      ? { bookReferences: effectiveBookReferences }
      : {}),
    ...(effectivePersona ? { persona: effectivePersona } : {}),
    ...(effectiveMemoryReferences?.length
      ? { memoryReferences: [...effectiveMemoryReferences] }
      : {}),
    ...(llmSelection ? { llmSelection } : {}),
  };
  const turnConfig =
    options?.persistUserMessage === false
      ? { ...(effectiveConfig || {}), _persist_user_message: false }
      : effectiveConfig;
  const turnMessage: EffectiveChatRequest["turnMessage"] = {
    type: "start_turn",
    content,
    tools,
    capability,
    knowledge_bases: knowledgeBases,
    session_id: session.sessionId,
    attachments: effectiveAttachments,
    language: effectiveLanguage,
    ...(effectiveNotebookReferences?.length
      ? { notebook_references: effectiveNotebookReferences }
      : {}),
    ...(effectiveHistoryReferences?.length
      ? { history_references: effectiveHistoryReferences }
      : {}),
    ...(effectiveQuestionNotebookReferences?.length
      ? { question_notebook_references: effectiveQuestionNotebookReferences }
      : {}),
    ...(effectiveBookReferences?.length
      ? { book_references: effectiveBookReferences as BookReferencePayload[] }
      : {}),
    persona: effectivePersona,
    ...(effectiveMemoryReferences?.length
      ? { memory_references: effectiveMemoryReferences }
      : {}),
    ...(llmSelection ? { llm_selection: llmSelection } : {}),
    ...(turnConfig && Object.keys(turnConfig).length > 0
      ? { config: turnConfig }
      : {}),
    ...(wireParentId !== undefined ? { parent_message_id: wireParentId } : {}),
  };

  return {
    capability,
    tools,
    knowledgeBases,
    language: effectiveLanguage,
    persona: effectivePersona,
    attachments: effectiveAttachments,
    requestSnapshot,
    turnMessage,
  };
}
