"use client";

/**
 * FollowupChatComposer — renders the SAME ``ChatComposer`` used on the
 * main chat page, but with its own local state pool and a send handler
 * that routes through ``QuizFollowupController`` instead of the unified
 * chat context. The follow-up tab uses this so the composer surface
 * (look, controls, @space popup, KB picker, attachments, LLM selector,
 * picker dialogs) matches the main chat composer exactly.
 *
 * Self-contained: loads its own KB / LLM lists, owns drag-and-drop +
 * attachment state, mounts the @space pickers internally.
 */

import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { MessageSquare } from "lucide-react";
import { useTranslation } from "react-i18next";
import ChatComposer from "@/components/chat/home/ChatComposer";
import ChatReferencePickers from "@/components/chat/home/ChatReferencePickers";
import {
  type QuizFollowupTabContext,
  useFollowupThread,
  useQuizFollowupController,
} from "@/context/QuizFollowupContext";
import {
  quizFollowupSendPlan,
} from "@/lib/quiz-types";
import { useChatAttachments } from "@/hooks/chat/attachments";
import { useChatComposerMenus } from "@/hooks/chat/menus";
import { useChatBasicResources } from "@/hooks/chat/resources";
import { useChatReferences } from "@/hooks/chat/references";
import { chatOutgoingAttachments } from "@/lib/chat/send";
import { toggleKnowledgeBaseSelection } from "@/lib/chat/agents";
import type { LLMSelection } from "@/lib/unified-ws";

const PersonaPicker = dynamic(() => import("@/components/chat/PersonaPicker"), {
  ssr: false,
});

// Single-capability list — the follow-up tab is locked to "chat".
// label/description are i18n keys; resolved via t() inside the component.
const FOLLOWUP_CAPABILITIES_RAW = [
  {
    value: "",
    label: "Chat",
    description: "Flexible conversation with any tool",
    icon: MessageSquare,
    allowedTools: [],
  },
];

interface FollowupChatComposerProps {
  context: QuizFollowupTabContext;
}

function FollowupChatComposerImpl({ context }: FollowupChatComposerProps) {
  const { t } = useTranslation();
  const controller = useQuizFollowupController();
  const thread = useFollowupThread(context.questionKey);

  // ── Composer DOM refs ─────────────────────────────────────────
  const composerRef = useRef<HTMLDivElement>(null);
  const {
    capMenuRef,
    capBtnRef,
    spaceMenuRef,
    spaceBtnRef,
    capMenuOpen,
    spaceMenuOpen,
    setCapMenuOpen,
    setSpaceMenuOpen,
  } = useChatComposerMenus();

  const chatAttachments = useChatAttachments(t);
  const {
    attachments,
    dragging,
    attachmentError,
    dragCounter,
    handlePaste,
    removeAttachment,
    handleDragEnter,
    handleDragLeave,
    handleDragOver,
    handleDrop,
    handleAddFiles,
    clearAttachments,
  } = chatAttachments;

  // ── Composer local state ──────────────────────────────────────
  const [selectedKnowledgeBases, setSelectedKnowledgeBases] = useState<
    string[]
  >([]);
  const [selectedPersona, setSelectedPersona] = useState<string | null>(null);
  const [showPersonaPicker, setShowPersonaPicker] = useState(false);

  const references = useChatReferences();
  const {
    showNotebookPicker,
    showBookPicker,
    showHistoryPicker,
    showQuestionBankPicker,
    showMemoryPicker,
    selectedNotebookRecords,
    selectedBookReferences,
    selectedHistorySessions,
    selectedQuestionEntries,
    selectedMemoryFiles,
    notebookReferenceGroups,
    notebookReferencesPayload,
    bookReferencesPayload,
    historyReferencesPayload,
    questionNotebookReferencesPayload,
    memoryReferencesPayload,
    handleSelectNotebookPicker,
    handleSelectBookPicker,
    handleSelectHistoryPicker,
    handleSelectQuestionBankPicker,
    handleSelectMemoryPicker,
    handleRemoveHistory,
    handleRemoveNotebook,
    handleRemoveBookReference,
    handleRemoveQuestion,
    handleToggleMemoryFile,
    handleCloseNotebookPicker,
    handleApplyNotebookRecords,
    handleCloseBookPicker,
    handleApplyBookReferences,
    handleCloseHistoryPicker,
    handleApplyHistorySessions,
    handleCloseQuestionBankPicker,
    handleApplyQuestionEntries,
    handleCloseMemoryPicker,
    handleApplyMemoryFiles,
    clearSelectedReferences,
  } = references;

  const {
    knowledgeBases,
    llmOptions,
    activeLLMDefault,
    llmOptionsLoading,
    llmOptionsError,
  } = useChatBasicResources();
  const [llmSelection, setLLMSelection] = useState<LLMSelection | null>(null);

  // Default to the server-side active LLM until the user picks one.
  useEffect(() => {
    if (llmSelection || !activeLLMDefault) return;
    setLLMSelection(activeLLMDefault);
  }, [activeLLMDefault, llmSelection]);

  // ── Picker handlers ───────────────────────────────────────────
  const handleToggleKB = useCallback((name: string) => {
    setSelectedKnowledgeBases((prev) =>
      toggleKnowledgeBaseSelection(prev, name),
    );
  }, []);

  const handleSelectPersonaPicker = useCallback(() => {
    setShowPersonaPicker(true);
  }, []);

  const handleClearPersona = useCallback(() => {
    setSelectedPersona(null);
  }, []);

  // Once the user has clicked Send we wipe transient selections — the
  // follow-up chat session has captured them and later turns ride on
  // server-side memory, mirroring the main chat behavior.
  const handleSend = useCallback(
    (content: string) => {
      const plan = quizFollowupSendPlan({
        content,
        isStreaming: thread.isStreaming,
        isFirstSend: !thread.sessionId && thread.messages.length === 0,
        question: context.question,
        userAnswer: context.userAnswer,
        isCorrect: context.isCorrect,
        parentQuizSessionId: context.parentQuizSessionId,
        answerImages: context.answerImages,
        aiJudgment: context.aiJudgment,
        attachments,
        selectedKnowledgeBases: { length: selectedKnowledgeBases.length },
        selectedBookReferences: { length: selectedBookReferences.length },
        selectedNotebookRecords: { length: selectedNotebookRecords.length },
        selectedHistorySessions: { length: selectedHistorySessions.length },
        selectedQuestionEntries: { length: selectedQuestionEntries.length },
        selectedMemoryFiles: { length: selectedMemoryFiles.length },
        selectedPersona,
        memoryReferences: memoryReferencesPayload,
      });
      if (!plan) return;

      controller.sendMessage({
        questionKey: context.questionKey,
        content: plan.content,
        attachments: [
          ...plan.answerImageAttachments,
          ...chatOutgoingAttachments(attachments),
        ],
        config: plan.config,
        language: context.language,
        knowledgeBases: selectedKnowledgeBases,
        notebookReferences: notebookReferencesPayload,
        historyReferences: historyReferencesPayload,
        bookReferences: bookReferencesPayload,
        questionNotebookReferences: questionNotebookReferencesPayload,
        persona: plan.persona,
        llmSelection,
      });

      // Wipe transient selections — the chat session now owns them.
      clearAttachments();
      clearSelectedReferences();
      setSelectedPersona(null);
    },
    [
      attachments,
      bookReferencesPayload,
      context,
      controller,
      clearAttachments,
      clearSelectedReferences,
      historyReferencesPayload,
      llmSelection,
      memoryReferencesPayload,
      notebookReferencesPayload,
      questionNotebookReferencesPayload,
      selectedBookReferences.length,
      selectedHistorySessions.length,
      selectedKnowledgeBases,
      selectedMemoryFiles,
      selectedNotebookRecords.length,
      selectedQuestionEntries.length,
      selectedPersona,
      thread.isStreaming,
      thread.messages.length,
      thread.sessionId,
    ],
  );

  const handleCancelStreaming = useCallback(() => {
    // The follow-up runner is owned by the controller; we don't expose
    // a hard cancel from the public surface. Treat this as a no-op for
    // now — the user can refresh or close the tab to recover.
  }, []);

  // ── Active capability is always "chat" for follow-up ──────────
  const FOLLOWUP_CAPABILITIES = useMemo(
    () =>
      FOLLOWUP_CAPABILITIES_RAW.map((cap) => ({
        ...cap,
        label: t(cap.label),
        description: t(cap.description),
      })),
    [t],
  );
  const activeCap = FOLLOWUP_CAPABILITIES[0];

  return (
    <>
      <ChatComposer
        composerRef={composerRef}
        capMenuRef={capMenuRef}
        capBtnRef={capBtnRef}
        spaceMenuRef={spaceMenuRef}
        spaceBtnRef={spaceBtnRef}
        dragCounter={dragCounter}
        dragging={dragging}
        capMenuOpen={capMenuOpen}
        spaceMenuOpen={spaceMenuOpen}
        hasMessages={
          thread.messages.filter((m) => m.role !== "system").length > 0
        }
        attachments={attachments}
        attachmentError={attachmentError}
        activeCap={activeCap}
        knowledgeBases={knowledgeBases}
        llmOptions={llmOptions}
        activeLLMDefault={activeLLMDefault}
        llmSelection={llmSelection}
        llmOptionsLoading={llmOptionsLoading}
        llmOptionsError={llmOptionsError}
        selectedBookReferences={selectedBookReferences}
        selectedNotebookRecords={selectedNotebookRecords}
        selectedHistorySessions={selectedHistorySessions}
        selectedAgentSessions={[]}
        selectedQuestionEntries={selectedQuestionEntries}
        notebookReferenceGroups={notebookReferenceGroups}
        selectedPersona={selectedPersona}
        selectedMemoryFiles={selectedMemoryFiles}
        selectedKnowledgeBases={selectedKnowledgeBases}
        isStreaming={thread.isStreaming}
        isVisualizeMode={false}
        capabilityNeedsConfig={false}
        capabilityConfigConfirmed={true}
        onRequestConfigConfirm={() => {}}
        capabilities={FOLLOWUP_CAPABILITIES}
        onSetCapMenuOpen={setCapMenuOpen}
        onSetSpaceMenuOpen={setSpaceMenuOpen}
        onToggleKB={handleToggleKB}
        onSelectLLM={setLLMSelection}
        onSelectNotebookPicker={handleSelectNotebookPicker}
        onSelectBookPicker={handleSelectBookPicker}
        onSelectHistoryPicker={handleSelectHistoryPicker}
        agentsAvailable={false}
        onSelectAgentsPicker={() => {}}
        onSelectQuestionBankPicker={handleSelectQuestionBankPicker}
        onSelectPersonaPicker={handleSelectPersonaPicker}
        onSelectMemoryPicker={handleSelectMemoryPicker}
        onClearPersona={handleClearPersona}
        onToggleMemoryFile={handleToggleMemoryFile}
        onSend={handleSend}
        onRemoveAttachment={removeAttachment}
        onRemoveHistory={handleRemoveHistory}
        onRemoveAgent={() => {}}
        onRemoveBookReference={handleRemoveBookReference}
        onRemoveNotebook={handleRemoveNotebook}
        onRemoveQuestion={handleRemoveQuestion}
        onDragEnter={handleDragEnter}
        onDragLeave={handleDragLeave}
        onDragOver={handleDragOver}
        onDrop={handleDrop}
        onPaste={handlePaste}
        onAddFiles={handleAddFiles}
        onSelectCapability={() => {}}
        onCancelStreaming={handleCancelStreaming}
        inputPlaceholder={t(
          "Ask anything about this question, your answer, or the AI judgment.",
        )}
      />

      <ChatReferencePickers
        showNotebookPicker={showNotebookPicker}
        showBookPicker={showBookPicker}
        showHistoryPicker={showHistoryPicker}
        showQuestionBankPicker={showQuestionBankPicker}
        showMemoryPicker={showMemoryPicker}
        selectedBookReferences={selectedBookReferences}
        selectedMemoryFiles={selectedMemoryFiles}
        onCloseNotebookPicker={handleCloseNotebookPicker}
        onApplyNotebookRecords={handleApplyNotebookRecords}
        onCloseBookPicker={handleCloseBookPicker}
        onApplyBookReferences={handleApplyBookReferences}
        onCloseHistoryPicker={handleCloseHistoryPicker}
        onApplyHistorySessions={handleApplyHistorySessions}
        onCloseQuestionBankPicker={handleCloseQuestionBankPicker}
        onApplyQuestionEntries={handleApplyQuestionEntries}
        onCloseMemoryPicker={handleCloseMemoryPicker}
        onApplyMemoryFiles={handleApplyMemoryFiles}
      />
      <PersonaPicker
        open={showPersonaPicker}
        initialPersona={selectedPersona}
        onClose={() => setShowPersonaPicker(false)}
        onApply={(persona: string | null) => {
          setSelectedPersona(persona);
          setShowPersonaPicker(false);
        }}
      />
    </>
  );
}

const FollowupChatComposer = memo(FollowupChatComposerImpl);
export default FollowupChatComposer;

export type { FollowupChatComposerProps };
