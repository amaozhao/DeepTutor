import type { DeepQuestionFormConfig } from "@/lib/quiz-types";
import { buildQuizWSConfig } from "@/lib/quiz-types";
import type { DeepResearchFormConfig } from "@/lib/research-types";
import { buildResearchWSConfig } from "@/lib/research-types";
import type { VisualizeFormConfig } from "@/lib/visualize-types";
import { buildVisualizeWSConfig } from "@/lib/visualize-types";

type Counted = { length: number };
type Translate = (key: string) => string;
type ChatMemoryReference = "summary" | "profile";
type ChatOutgoingAttachment = {
  type: string;
  url?: string;
  base64?: string;
  filename?: string;
  mime_type?: string;
};
type ChatNotebookReference = {
  notebook_id: string;
  record_ids: string[];
};
type ChatBookReference = {
  book_id: string;
  page_ids: string[];
};
type ChatRequestSnapshot = {
  content: string;
  capability?: string | null;
  enabledTools: string[];
  knowledgeBases: string[];
  language: string;
  attachments?: ChatOutgoingAttachment[];
  notebookReferences?: ChatNotebookReference[];
  historyReferences?: string[];
  bookReferences?: ChatBookReference[];
  questionNotebookReferences?: number[];
  persona?: string;
  memoryReferences?: ChatMemoryReference[];
  config?: Record<string, unknown>;
};

export interface ChatSendPlan {
  content: string;
}

export function chatCapabilitySendConfigPlan({
  isQuizMode,
  isVisualizeMode,
  isResearchMode,
  quizConfig,
  visualizeConfig,
  researchConfig,
  researchConfigValid,
}: {
  isQuizMode: boolean;
  isVisualizeMode: boolean;
  isResearchMode: boolean;
  quizConfig: DeepQuestionFormConfig;
  visualizeConfig: VisualizeFormConfig;
  researchConfig: DeepResearchFormConfig;
  researchConfigValid: boolean;
}): { config?: Record<string, unknown>; attachQuizPdf: boolean } | null {
  if (isQuizMode) {
    return {
      config: buildQuizWSConfig(quizConfig),
      attachQuizPdf: quizConfig.mode === "mimic",
    };
  }
  if (isVisualizeMode) {
    return {
      config: buildVisualizeWSConfig(visualizeConfig),
      attachQuizPdf: false,
    };
  }
  if (isResearchMode) {
    if (!researchConfigValid) return null;
    return {
      config: buildResearchWSConfig(researchConfig),
      attachQuizPdf: false,
    };
  }
  return { attachQuizPdf: false };
}

export function chatConfirmedOutlineSendPlan({
  outline,
  topic,
  researchConfig,
  originalConfig,
  originalSnapshot,
}: {
  outline: unknown[];
  topic: string;
  researchConfig: { mode: string; depth: string };
  originalConfig?: Record<string, unknown> | null;
  originalSnapshot?: ChatRequestSnapshot | null;
}): {
  content: string;
  attachments: ChatOutgoingAttachment[];
  config: Record<string, unknown>;
  notebookReferences?: ChatNotebookReference[];
  historyReferences?: string[];
  options: {
    displayUserMessage: false;
    persistUserMessage: false;
    requestSnapshotOverride?: ChatRequestSnapshot;
    bookReferences?: ChatBookReference[];
  };
  questionNotebookReferences?: number[];
  persona?: string;
  memoryReferences?: ChatMemoryReference[];
} {
  const config: Record<string, unknown> = {
    ...(originalConfig ?? {
      mode: researchConfig.mode,
      depth: researchConfig.depth,
    }),
    confirmed_outline: outline,
  };
  return {
    content: topic,
    attachments: originalSnapshot?.attachments ?? [],
    config,
    notebookReferences: originalSnapshot?.notebookReferences,
    historyReferences: originalSnapshot?.historyReferences,
    options: {
      displayUserMessage: false,
      persistUserMessage: false,
      ...(originalSnapshot
        ? {
            requestSnapshotOverride: {
              ...originalSnapshot,
              content: topic,
              capability: "deep_research",
              config,
            },
          }
        : {}),
      bookReferences: originalSnapshot?.bookReferences,
    },
    questionNotebookReferences: originalSnapshot?.questionNotebookReferences,
    persona: originalSnapshot?.persona,
    memoryReferences: originalSnapshot?.memoryReferences,
  };
}

export function chatOutgoingAttachments(
  attachments: Array<{
    type: string;
    filename: string;
    base64?: string;
    mimeType?: string;
  }>,
): Array<{
  type: string;
  filename: string;
  base64?: string;
  mime_type?: string;
}> {
  return attachments.map((attachment) => ({
    type: attachment.type,
    filename: attachment.filename,
    base64: attachment.base64,
    mime_type: attachment.mimeType,
  }));
}

export function chatQuizPdfAttachment(
  filename: string,
  base64: string,
): {
  type: "pdf";
  filename: string;
  base64: string;
  mime_type: "application/pdf";
} {
  return {
    type: "pdf",
    filename,
    base64,
    mime_type: "application/pdf",
  };
}

export function chatConfigWithSubagentBudget({
  config,
  selectedAgent,
  subagentBudget,
}: {
  config?: Record<string, unknown>;
  selectedAgent: string | null;
  subagentBudget: number | null;
}): Record<string, unknown> | undefined {
  if (!selectedAgent || !subagentBudget) return config;
  return { ...(config ?? {}), subagent_consult_budget: subagentBudget };
}

export function chatSendPlan({
  content,
  isStreaming,
  attachments,
  bookReferences,
  notebookRecords,
  historySessions,
  agentSessions,
  questionEntries,
  memoryFiles,
  memoryReferences,
  t,
}: {
  content: string;
  isStreaming: boolean;
  attachments: Array<{ type?: string }>;
  bookReferences: Counted;
  notebookRecords: Counted;
  historySessions: Counted;
  agentSessions: Counted;
  questionEntries: Counted;
  memoryFiles: Counted;
  memoryReferences: Counted;
  t: Translate;
}): ChatSendPlan | null {
  const hasDraftInput =
    Boolean(content) ||
    attachments.length > 0 ||
    bookReferences.length > 0 ||
    notebookRecords.length > 0 ||
    historySessions.length > 0 ||
    questionEntries.length > 0 ||
    memoryFiles.length > 0;
  if (isStreaming || !hasDraftInput) return null;

  const hasContext =
    notebookRecords.length > 0 ||
    bookReferences.length > 0 ||
    historySessions.length > 0 ||
    agentSessions.length > 0 ||
    questionEntries.length > 0 ||
    memoryReferences.length > 0;
  return {
    content:
      content ||
      (hasContext
        ? t("Please use the selected context to help with this request.")
        : "") ||
      (attachments.some((attachment) => attachment.type === "image")
        ? t("Please analyze the attached image(s).")
        : ""),
  };
}
