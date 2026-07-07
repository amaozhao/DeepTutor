import type { LLMSelection } from "../unified-ws";
import {
  normalizeBookReferences,
  type BookReferencePayload,
} from "../book-references";

type NotebookReferencePayload = {
  notebook_id: string;
  record_ids: string[];
};
type HistoryReferencePayload = string[];
type QuestionNotebookReferencePayload = number[];
type MemoryReferencePayload = Array<"summary" | "profile">;

type SessionMessageLike = {
  capability?: string;
  metadata?: Record<string, unknown>;
  attachments: Array<{
    type: string;
    filename?: string;
    base64?: string;
    url?: string;
    mime_type?: string;
    id?: string;
    extracted_text?: string;
    generated?: boolean;
    size_bytes?: number;
  }>;
};

export type HydratedMessageAttachment =
  SessionMessageLike["attachments"][number];

export interface HydratedRequestSnapshot {
  content: string;
  capability?: string | null;
  enabledTools: string[];
  knowledgeBases: string[];
  language: string;
  attachments?: HydratedMessageAttachment[];
  config?: Record<string, unknown>;
  notebookReferences?: NotebookReferencePayload[];
  historyReferences?: HistoryReferencePayload;
  questionNotebookReferences?: QuestionNotebookReferencePayload;
  bookReferences?: BookReferencePayload[];
  persona?: string;
  memoryReferences?: MemoryReferencePayload;
  llmSelection?: LLMSelection | null;
}

export function hydrateMessageAttachments(
  attachments: SessionMessageLike["attachments"],
): HydratedMessageAttachment[] {
  return Array.isArray(attachments)
    ? attachments.map((item) => ({
        type: item.type,
        filename: item.filename,
        base64: item.base64,
        url: item.url,
        mime_type: item.mime_type,
        id: item.id,
        extracted_text: item.extracted_text,
        generated: item.generated,
        size_bytes: item.size_bytes,
      }))
    : [];
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function asStringArray(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter(
        (item): item is string => typeof item === "string" && item.length > 0,
      )
    : [];
}

export function asLLMSelection(value: unknown): LLMSelection | null {
  const record = asRecord(value);
  const profileId =
    typeof record?.profile_id === "string" ? record.profile_id.trim() : "";
  const modelId =
    typeof record?.model_id === "string" ? record.model_id.trim() : "";
  return profileId && modelId
    ? { profile_id: profileId, model_id: modelId }
    : null;
}

export function normalizeSelectedBranches(
  value: unknown,
): Record<string, number> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  const result: Record<string, number> = {};
  for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
    const n = typeof v === "number" ? v : Number(v);
    if (Number.isInteger(n) && n > 0) result[k] = n;
  }
  return result;
}

function asMemoryReferences(value: unknown): MemoryReferencePayload {
  return asStringArray(value).filter(
    (item): item is "summary" | "profile" =>
      item === "summary" || item === "profile",
  );
}

function asNotebookReferences(value: unknown): NotebookReferencePayload[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    const ref = asRecord(item);
    const notebookId =
      typeof ref?.notebook_id === "string" ? ref.notebook_id : "";
    const recordIds = asStringArray(ref?.record_ids);
    return notebookId && recordIds.length
      ? [{ notebook_id: notebookId, record_ids: recordIds }]
      : [];
  });
}

function asQuestionReferences(
  value: unknown,
): QuestionNotebookReferencePayload {
  return Array.isArray(value)
    ? value
        .map((item) => (typeof item === "number" ? item : Number(item)))
        .filter((item) => Number.isInteger(item))
    : [];
}

export function hydrateRequestSnapshot(
  message: SessionMessageLike,
  content: string,
  attachments: HydratedMessageAttachment[],
): HydratedRequestSnapshot | undefined {
  const metadata = asRecord(message.metadata);
  const stored = asRecord(
    metadata?.request_snapshot ?? metadata?.requestSnapshot,
  );
  if (!stored) return undefined;

  const snapshot: HydratedRequestSnapshot = {
    content: typeof stored.content === "string" ? stored.content : content,
    capability:
      typeof stored.capability === "string"
        ? stored.capability
        : message.capability || "",
    enabledTools: asStringArray(stored.enabledTools),
    knowledgeBases: asStringArray(stored.knowledgeBases),
    language: typeof stored.language === "string" ? stored.language : "en",
    ...(attachments.length ? { attachments } : {}),
  };

  const config = asRecord(stored.config);
  const notebookReferences = asNotebookReferences(stored.notebookReferences);
  const historyReferences = asStringArray(stored.historyReferences);
  const questionNotebookReferences = asQuestionReferences(
    stored.questionNotebookReferences,
  );
  const persona =
    typeof stored.persona === "string" && stored.persona.length > 0
      ? stored.persona
      : "";
  const memoryReferences = asMemoryReferences(stored.memoryReferences);
  const bookReferences = normalizeBookReferences(stored.bookReferences);
  const llmSelection = asLLMSelection(stored.llmSelection);

  if (config && Object.keys(config).length) snapshot.config = config;
  if (notebookReferences.length)
    snapshot.notebookReferences = notebookReferences;
  if (historyReferences.length) snapshot.historyReferences = historyReferences;
  if (questionNotebookReferences.length) {
    snapshot.questionNotebookReferences = questionNotebookReferences;
  }
  if (bookReferences.length) snapshot.bookReferences = bookReferences;
  if (persona) snapshot.persona = persona;
  if (memoryReferences.length) snapshot.memoryReferences = memoryReferences;
  if (llmSelection) snapshot.llmSelection = llmSelection;
  return snapshot;
}
