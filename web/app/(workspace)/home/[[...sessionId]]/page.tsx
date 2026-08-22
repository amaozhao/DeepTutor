"use client";

import dynamic from "next/dynamic";
import {
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";
import { useParams, useRouter } from "next/navigation";

import { useTranslation } from "react-i18next";
import ChatComposer from "@/components/chat/home/ChatComposer";
import type { ContextBudget } from "@/components/chat/home/ContextBudgetChip";
import ChatHeader from "@/components/chat/home/ChatHeader";
import { ChatMessageList } from "@/components/chat/home/ChatMessages";
import ChatReferencePickers from "@/components/chat/home/ChatReferencePickers";
import ChatWelcomeView from "@/components/chat/home/ChatWelcomeView";
import {
  GeogebraTabBridge,
  QuizFollowupBridge,
  SubagentTabWatcher,
} from "@/components/chat/home/PanelBridges";
import SessionLoadingView from "@/components/chat/home/SessionLoadingView";
import StarterSuggestions from "@/components/chat/home/StarterSuggestions";
import MasteryPathStrip from "@/components/chat/home/MasteryPathStrip";
import { TurnNavigator } from "@/components/chat/home/TurnNavigator";
import { READER_ASK_EVENT, ReaderPane } from "@/components/reading/ReaderPane";
// Imported eagerly so the drawer shell is always mounted off-screen —
// clicking a chip becomes a single CSS class flip, no chunk fetch + double
// render. The heavy renderers inside still load lazily.
import FilePreviewDrawer from "@/components/chat/preview/FilePreviewDrawer";
import { buildSessionActivity } from "@/components/chat/home/SessionActivityPanel";
import SessionViewerPanel from "@/components/chat/home/SessionViewerPanel";
import { QuizFollowupProvider } from "@/context/QuizFollowupContext";
import { GeogebraTabProvider } from "@/context/GeogebraTabContext";
import {
  useUnifiedChat,
  type MessageRequestSnapshot,
} from "@/context/UnifiedChatContext";
import { useAppShell } from "@/context/AppShellContext";
import type { LLMSelection, StreamEvent } from "@/lib/unified-ws";
import {
  extractBase64FromDataUrl,
  readFileAsDataUrl,
} from "@/lib/file-attachments";
import { useChatAutoScroll } from "@/hooks/useChatAutoScroll";
import { useMeasuredHeight } from "@/hooks/useMeasuredHeight";
import { useChatAttachments } from "@/hooks/chat/attachments";
import {
  useChatCapabilityConfig,
  useChatCapabilityConfigAutoOpen,
  useChatEnabledToolsSync,
  useChatQueryCapabilityInitializer,
} from "@/hooks/chat/capability";
import { useChatReferences } from "@/hooks/chat/references";
import {
  useChatDefaultLLMSelection,
  useChatResources,
} from "@/hooks/chat/resources";
import { useChatSessionRoute } from "@/hooks/chat/session";
import { useSessionTitleEditor } from "@/hooks/chat/title";
import { useChatViewerPanel } from "@/hooks/chat/viewer";
import { useChatComposerMenus } from "@/hooks/chat/menus";
import { useChatComposerPrefillBridge } from "@/hooks/chat/prefill";
import { useChatWelcomeGreeting } from "@/hooks/chat/greeting";
import { useSetupSync } from "@/hooks/useSetupSync";
import { type OutlineItem } from "@/lib/research-types";
import { downloadChatMarkdown } from "@/lib/chat-export";
import { buildChatOutline } from "@/lib/chat-outline";
import {
  CAPABILITIES,
  getCapability,
} from "@/lib/capabilities";
import {
  firstUserMessageTitle,
  resolveSessionTitle,
} from "@/lib/chat/title";
import { chatMessagesScrollStyle } from "@/lib/chat/style";
import {
  chatConfirmedOutlineSendPlan,
  chatCapabilitySendConfigPlan,
  chatConfigWithSubagentBudget,
  chatOutgoingAttachments,
  chatQuizPdfAttachment,
  chatSendPlan,
} from "@/lib/chat/send";
import {
  chatNotebookSaveMessages,
  chatNotebookSavePayload,
} from "@/lib/chat/save";
import {
  chatCapabilityMode,
  chatCapabilitySelectionPlan,
} from "@/lib/chat/capability";
import { toggleKnowledgeBaseSelection } from "@/lib/chat/agents";
import { useChatAgents } from "@/hooks/chat/agents";
import { consumePendingPrompt } from "@/lib/pending-prompt";

const SaveToNotebookModal = dynamic(
  () => import("@/components/notebook/SaveToNotebookModal"),
  {
    ssr: false,
  },
);

function readContextBudget(events: StreamEvent[] | undefined): ContextBudget | null {
  if (!events) return null;
  for (let i = events.length - 1; i >= 0; i -= 1) {
    const event = events[i];
    if (event.type !== "result") continue;
    const metadata = event.metadata?.metadata as Record<string, unknown> | undefined;
    const budget = metadata?.context_budget as ContextBudget | undefined;
    if (
      budget &&
      typeof budget.window === "number" &&
      typeof budget.used_tokens === "number" &&
      Array.isArray(budget.segments)
    ) {
      return budget;
    }
  }
  return null;
}

export default function ChatPage() {
  const params = useParams<{ sessionId?: string[] }>();
  const router = useRouter();
  const { t } = useTranslation();
  const sessionIdParam = params.sessionId?.[0] ?? null;
  const { setActiveSessionId, language: appLanguage } = useAppShell();

  const {
    state,
    setTools,
    setCapability,
    setKBs,
    setLLMSelection,
    setMasteryPathId,
    setPersonaSelection,
    sendMessage,
    cancelStreamingTurn,
    submitUserReply,
    regenerateLastMessage,
    deleteTurn,
    editMessage,
    switchBranch,
    newSession,
    loadSession,
    showCachedSession,
    renameSessionTitle,
  } = useUnifiedChat();

  const {
    knowledgeBases,
    knowledgeBasesLoaded,
    llmOptions,
    activeLLMDefault,
    llmOptionsLoading,
    llmOptionsError,
    capabilityConfigs,
    userEnabledTools,
    refreshLLMOptions,
  } = useChatResources();
  const availableKbNames = useMemo(
    () => new Set(knowledgeBases.map((kb) => kb.name)),
    [knowledgeBases],
  );
  const {
    kbOptions,
    agentOptions,
    selectedKbOnly,
    selectedAgent,
    handleSelectAgent,
    subagentBudget,
    setSubagentBudget,
  } = useChatAgents({
    knowledgeBases,
    selectedKnowledgeBases: state.knowledgeBases,
    setKnowledgeBases: setKBs,
  });
  const chatAttachments = useChatAttachments(t);
  const {
    attachments,
    dragging,
    attachmentError,
    previewSource,
    dragCounter,
    handlePaste,
    removeAttachment,
    handlePreviewPendingAttachment,
    handleClosePreview,
    handleDragEnter,
    handleDragLeave,
    handleDragOver,
    handleDrop,
    handleAddFiles,
    clearAttachments,
  } = chatAttachments;
  const {
    viewerPanelRef,
    viewerPanelOpen,
    setViewerOpen,
    toggleViewerPanel,
    ensureActivityPanelOpen,
    handlePreviewMessageAttachment,
    handleMessagesClick,
  } = useChatViewerPanel();
  const [showSaveModal, setShowSaveModal] = useState(false);
  // Session persona selector (toolbar chip / `/persona` / @space entry all
  // open the same dropdown). The selection itself lives in the unified chat
  // context (state.personaSelection) so it follows the session.
  const [personaSelectorOpen, setPersonaSelectorOpen] = useState(false);
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
  const chatReferences = useChatReferences();
  const {
    showNotebookPicker,
    showBookPicker,
    showHistoryPicker,
    showAgentsPicker,
    showQuestionBankPicker,
    showMemoryPicker,
    selectedNotebookRecords,
    selectedBookReferences,
    selectedHistorySessions,
    selectedAgentSessions,
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
    handleSelectAgentsPicker,
    handleSelectQuestionBankPicker,
    handleSelectMemoryPicker,
    handleRemoveHistory,
    handleRemoveAgent,
    handleRemoveNotebook,
    handleRemoveBookReference,
    handleRemoveQuestion,
    handleToggleMemoryFile,
    handleCloseNotebookPicker,
    handleCloseBookPicker,
    handleApplyBookReferences,
    handleApplyNotebookRecords,
    handleCloseHistoryPicker,
    handleApplyHistorySessions,
    handleCloseAgentsPicker,
    handleApplyAgentSessions,
    handleCloseQuestionBankPicker,
    handleApplyQuestionEntries,
    handleCloseMemoryPicker,
    handleApplyMemoryFiles,
    clearSelectedReferences,
  } = chatReferences;
  const prefillInputRef = useChatComposerPrefillBridge();

  useEffect(() => {
    const pending = consumePendingPrompt();
    if (!pending) return;
    let attempts = 0;
    let timer: ReturnType<typeof setTimeout>;
    const attempt = () => {
      if (prefillInputRef.current) {
        prefillInputRef.current(pending);
        return;
      }
      if (attempts++ >= 20) return;
      timer = setTimeout(attempt, 100);
    };
    timer = setTimeout(attempt, 0);
    return () => clearTimeout(timer);
  }, [prefillInputRef]);

  useEffect(() => {
    const onReaderAsk = (event: Event) => {
      const detail = (
        event as CustomEvent<{ quote?: string; locator?: number; unit?: string }>
      ).detail;
      const quote = (detail?.quote || "").trim();
      if (!quote) return;
      const unit = detail?.unit || "page";
      const where = detail?.locator ? ` (${unit} ${detail.locator})` : "";
      prefillInputRef.current?.(
        `> ${quote}\n\n${t("Explain this passage")}${where}: `,
      );
    };
    window.addEventListener(READER_ASK_EVENT, onReaderAsk);
    return () => window.removeEventListener(READER_ASK_EVENT, onReaderAsk);
  }, [prefillInputRef, t]);

  const activeCap = useMemo(
    () => getCapability(state.activeCapability),
    [state.activeCapability],
  );
  const { isQuizMode, isVisualizeMode, isResearchMode, capabilityNeedsConfig } =
    chatCapabilityMode(activeCap.value);
  const capabilityConfig = useChatCapabilityConfig({
    sessionId: state.sessionId,
    sessionIdParam,
    isQuizMode,
    isVisualizeMode,
    capabilityNeedsConfig,
  });
  const {
    quizConfig,
    quizPdf,
    visualizeConfig,
    researchConfig,
    researchValidation,
    confirmed: capabilityConfigConfirmed,
    setConfirmed: setCapabilityConfigConfirmed,
    configSection: capabilityConfigSection,
  } = capabilityConfig;

  useChatCapabilityConfigAutoOpen(
    capabilityNeedsConfig,
    ensureActivityPanelOpen,
  );
  useChatDefaultLLMSelection({
    currentSelection: state.llmSelection,
    activeLLMDefault,
    setLLMSelection,
  });
  useChatEnabledToolsSync({
    userEnabledTools,
    allowedTools: activeCap.allowedTools,
    currentTools: state.enabledTools,
    setTools,
  });
  const hasMessages = state.messages.length > 0;
  const isReadingMode = activeCap.value === "immersive_reading";
  useSetupSync(state.messages);
  const welcomeGreeting = useChatWelcomeGreeting();
  const firstUserTitle = useMemo(
    () => firstUserMessageTitle(state.messages),
    [state.messages],
  );
  const persistedSessionTitle = state.sessionTitle.trim();
  const displaySessionTitle = resolveSessionTitle(
    persistedSessionTitle,
    firstUserTitle,
    t("New chat"),
  );
  const canRenameSession = Boolean(state.sessionId);
  const sessionTitleEditor = useSessionTitleEditor({
    canRename: canRenameSession,
    displayTitle: displaySessionTitle,
    persistedTitle: persistedSessionTitle,
    renameSessionTitle,
    renameFailedLabel: t("Rename failed"),
  });
  const { ref: composerRef, height: composerHeight } =
    useMeasuredHeight<HTMLDivElement>();
  const chatSaveMessages = useMemo(
    () => chatNotebookSaveMessages(state.messages),
    [state.messages],
  );
  const chatSavePayload = useMemo(
    () =>
      chatNotebookSavePayload({
        messages: state.messages,
        firstUserTitle,
        activeCapability: state.activeCapability,
        language: state.language,
        sessionId: state.sessionId,
      }),
    [
      firstUserTitle,
      state.activeCapability,
      state.language,
      state.messages,
      state.sessionId,
    ],
  );
  const lastMessage = state.messages[state.messages.length - 1];
  const {
    containerRef: messagesContainerRef,
    endRef: messagesEndRef,
    shouldAutoScrollRef,
    scrollToBottom,
    handleScroll: handleMessagesScroll,
  } = useChatAutoScroll({
    hasMessages,
    isStreaming: state.isStreaming,
    composerHeight,
    messageCount: state.messages.length,
    lastMessageContent: lastMessage?.content,
    lastEventCount: lastMessage?.events?.length,
  });
  const chatOutline = useMemo(
    () => buildChatOutline(state.messages, state.selectedBranches),
    [state.messages, state.selectedBranches],
  );
  const jumpToTurn = useCallback(
    (key: string) => {
      const container = messagesContainerRef.current;
      const target = container?.querySelector<HTMLElement>(`[data-turn-key="${key}"]`);
      if (!container || !target) return;
      shouldAutoScrollRef.current = false;
      const offset = target.getBoundingClientRect().top - container.getBoundingClientRect().top;
      container.scrollTo({ top: container.scrollTop + offset - 56, behavior: "smooth" });
      const bubble = target.querySelector<HTMLElement>("[data-turn-bubble]") ?? target;
      bubble.classList.remove("turn-flash");
      void bubble.offsetWidth;
      bubble.classList.add("turn-flash");
      window.setTimeout(() => bubble.classList.remove("turn-flash"), 1300);
    },
    [messagesContainerRef, shouldAutoScrollRef],
  );
  const resumeFollowingLatest = useCallback(() => {
    shouldAutoScrollRef.current = true;
    scrollToBottom("instant");
  }, [scrollToBottom, shouldAutoScrollRef]);
  const copyAssistantMessage = useCallback(async (content: string) => {
    if (!content.trim()) return;
    try {
      await navigator.clipboard.writeText(content);
    } catch (error) {
      console.error("Failed to copy assistant message:", error);
    }
  }, []);
  const loadSessionAndSettle = useCallback(
    async (
      sessionId: string,
      options?: { signal?: AbortSignal; revalidate?: boolean },
    ) => {
      await loadSession(sessionId, options);
      if (options?.revalidate) return;
      shouldAutoScrollRef.current = true;
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          if (!options?.signal?.aborted) scrollToBottom("instant");
        });
      });
    },
    [loadSession, scrollToBottom, shouldAutoScrollRef],
  );
  const {
    sessionLoading,
    sessionLoadFailed,
    cancelSessionLoad,
    retrySessionLoad,
  } = useChatSessionRoute({
    sessionId: state.sessionId,
    sessionIdParam,
    router,
    newSession,
    loadSession: loadSessionAndSettle,
    showCachedSession,
    setActiveSessionId,
  });

  /* ---- handlers ---- */

  const handleSelectCapability = useCallback(
    (value: string) => {
      const plan = chatCapabilitySelectionPlan({
        value,
        capabilities: CAPABILITIES,
        capabilityConfigs,
        userEnabledTools,
      });
      setCapability(plan.capabilityValue);
      // Per-capability tool selection now derives from the user's saved
      // settings (/settings/tools) intersected with the capability's
      // allow-list. Playground-saved configs still override when the user
      // explicitly pinned tools in the playground for this capability.
      setTools(plan.enabledTools);
      if (plan.knowledgeBases.length) setKBs(plan.knowledgeBases);
      // Switching capability invalidates any prior config confirmation —
      // the new capability has its own form that needs explicit confirm.
      setCapabilityConfigConfirmed(false);
      setCapMenuOpen(false);
    },
    [
      capabilityConfigs,
      setCapabilityConfigConfirmed,
      setCapMenuOpen,
      setCapability,
      setKBs,
      setTools,
      userEnabledTools,
    ],
  );
  useChatQueryCapabilityInitializer({
    allowedTools: activeCap.allowedTools,
    onSelectCapability: handleSelectCapability,
    setTools,
  });
  useEffect(() => {
    if (typeof window === "undefined") return;
    const masteryPathId = new URLSearchParams(window.location.search)
      .get("mastery_path_id")
      ?.trim();
    if (masteryPathId) setMasteryPathId(masteryPathId);
  }, [setMasteryPathId]);

  useEffect(() => {
    if (!knowledgeBasesLoaded) return;
    const pruned = state.knowledgeBases.filter((name) =>
      availableKbNames.has(name),
    );
    if (pruned.length !== state.knowledgeBases.length) setKBs(pruned);
  }, [availableKbNames, knowledgeBasesLoaded, setKBs, state.knowledgeBases]);

  // Fold all messages once per state.messages change to power the
  // SessionActivityPanel on the right (tools, KBs, space refs, attachments).
  const sessionActivity = useMemo(
    () =>
      buildSessionActivity(state.messages, {
        availableKbNames: knowledgeBasesLoaded ? availableKbNames : undefined,
      }),
    [availableKbNames, knowledgeBasesLoaded, state.messages],
  );
  const contextBudget = useMemo(() => {
    for (let i = state.messages.length - 1; i >= 0; i -= 1) {
      const message = state.messages[i];
      if (message.role !== "assistant") continue;
      const budget = readContextBudget(message.events);
      if (budget) return budget;
    }
    return null;
  }, [state.messages]);

  const handleSend = useCallback(
    async (content: string) => {
      const plan = chatSendPlan({
        content,
        isStreaming: state.isStreaming,
        attachments,
        bookReferences: selectedBookReferences,
        notebookRecords: selectedNotebookRecords,
        historySessions: selectedHistorySessions,
        agentSessions: selectedAgentSessions,
        questionEntries: selectedQuestionEntries,
        memoryFiles: selectedMemoryFiles,
        memoryReferences: memoryReferencesPayload,
        t,
      });
      if (!plan) return;

      let extraAttachments = chatOutgoingAttachments(attachments);
      const configPlan = chatCapabilitySendConfigPlan({
        isQuizMode,
        isVisualizeMode,
        isResearchMode,
        quizConfig,
        visualizeConfig,
        researchConfig,
        researchConfigValid: researchValidation.valid,
      });
      if (!configPlan) return;
      let config = configPlan.config;

      if (configPlan.attachQuizPdf && quizPdf) {
        const b64 = extractBase64FromDataUrl(await readFileAsDataUrl(quizPdf));
        extraAttachments = [
          ...extraAttachments,
          chatQuizPdfAttachment(quizPdf.name, b64),
        ];
      }
      // When a connected agent is selected, carry the per-turn consult budget
      // (how many times DeepTutor may ask it) so the subagent capability uses it.
      config = chatConfigWithSubagentBudget({
        config,
        selectedAgent,
        subagentBudget,
      });

      const memoryPayload = [...memoryReferencesPayload];
      // Persona is NOT passed per-call here: it is a session-level
      // preference (state.personaSelection) that sendMessage resolves and
      // sends with every turn.
      sendMessage(
        plan.content,
        extraAttachments,
        config,
        notebookReferencesPayload,
        historyReferencesPayload,
        { bookReferences: bookReferencesPayload },
        questionNotebookReferencesPayload,
        undefined,
        memoryPayload,
      );
      shouldAutoScrollRef.current = true;
      clearAttachments();
      clearSelectedReferences();
    },
    [
      attachments,
      bookReferencesPayload,
      historyReferencesPayload,
      isQuizMode,
      isResearchMode,
      isVisualizeMode,
      memoryReferencesPayload,
      notebookReferencesPayload,
      questionNotebookReferencesPayload,
      quizConfig,
      quizPdf,
      researchConfig,
      researchValidation,
      selectedAgent,
      selectedAgentSessions,
      selectedBookReferences,
      selectedHistorySessions,
      selectedMemoryFiles,
      selectedNotebookRecords,
      selectedQuestionEntries,
      sendMessage,
      shouldAutoScrollRef,
      state.isStreaming,
      subagentBudget,
      t,
      visualizeConfig,
      clearSelectedReferences,
      clearAttachments,
    ],
  );

  const handleConfirmOutline = useCallback(
    (
      outline: OutlineItem[],
      _topic: string,
      originalConfig?: Record<string, unknown> | null,
      originalSnapshot?: MessageRequestSnapshot | null,
    ) => {
      const plan = chatConfirmedOutlineSendPlan({
        outline,
        topic: _topic,
        researchConfig,
        originalConfig,
        originalSnapshot,
      });
      sendMessage(
        plan.content,
        plan.attachments,
        plan.config,
        plan.notebookReferences,
        plan.historyReferences,
        plan.options,
        plan.questionNotebookReferences,
        plan.persona,
        plan.memoryReferences,
      );
      shouldAutoScrollRef.current = true;
    },
    [researchConfig, sendMessage, shouldAutoScrollRef],
  );

  const handleToggleKB = useCallback(
    (name: string) => {
      setKBs(
        toggleKnowledgeBaseSelection(state.knowledgeBases, name, knowledgeBases),
      );
    },
    [knowledgeBases, setKBs, state.knowledgeBases],
  );

  const handleSelectPersonaPicker = useCallback(() => {
    // The @space "Persona" entry now opens the session persona selector.
    setPersonaSelectorOpen(true);
  }, []);
  const handleClearPersona = useCallback(() => {
    setPersonaSelection("");
  }, [setPersonaSelection]);

  const handleDownloadMarkdown = useCallback(() => {
    if (!state.messages.length) return;
    const title = firstUserTitle || "Chat Session";
    downloadChatMarkdown(state.messages, { title });
  }, [firstUserTitle, state.messages]);

  return (
    <QuizFollowupProvider>
      <GeogebraTabProvider>
        <QuizFollowupBridge viewerPanelRef={viewerPanelRef} />
        <GeogebraTabBridge viewerPanelRef={viewerPanelRef} />
        <SubagentTabWatcher
          messages={state.messages}
          viewerPanelRef={viewerPanelRef}
        />
        <div className="relative h-full overflow-hidden">
          <div
            data-reader-open={isReadingMode ? "true" : "false"}
            className="dt-reader-shell"
          >
            {isReadingMode ? (
              <ReaderPane onClose={() => setCapability("")} />
            ) : null}
          </div>
        <div
          // When the preview drawer is open AND the viewport is wide enough,
          // push the chat content to the left by the drawer's width so the two
          // panels live side-by-side (matches Claude desktop). On smaller
          // screens the drawer overlays — squeezing a phone-width chat into
          // the remaining ~30 px would be useless. The actual padding +
          // transition lives in `chat-preview-shell` (globals.css) so we can
          // hand-tune it without fighting Tailwind's arbitrary-value parser.
          data-preview-open={previewSource ? "true" : "false"}
          data-viewer-open={viewerPanelOpen ? "true" : "false"}
          data-reader-open={isReadingMode ? "true" : "false"}
          className="chat-preview-shell flex h-full flex-col overflow-hidden bg-[var(--background)]"
        >
          <ChatHeader
            titleInputRef={sessionTitleEditor.inputRef}
            sessionTitleEditing={sessionTitleEditor.editing}
            sessionTitleDraft={sessionTitleEditor.draft}
            displaySessionTitle={displaySessionTitle}
            canRenameSession={canRenameSession}
            sessionTitleSaving={sessionTitleEditor.saving}
            sessionTitleError={sessionTitleEditor.error}
            canSaveChat={Boolean(chatSavePayload)}
            canDownloadChat={state.messages.length > 0}
            viewerPanelOpen={viewerPanelOpen}
            labels={{
              sessionTitle: t("Session title"),
              clickToRenameSession: t("Click to rename session"),
              startConversationToRename: t("Start a conversation to rename"),
              saving: t("Saving..."),
              saveToNotebook: t("Save to Notebook"),
              downloadMarkdown: t("Download Markdown"),
              downloadMarkdownTitle: t("Download chat history as Markdown"),
              activity: t("Activity"),
              activityTitle: t("Session activity, attachments & previews"),
            }}
            onSessionTitleDraftChange={sessionTitleEditor.setDraft}
            onCommitSessionTitleEdit={() => void sessionTitleEditor.commit()}
            onSessionTitleKeyDown={sessionTitleEditor.handleKeyDown}
            onStartSessionTitleEdit={sessionTitleEditor.start}
            onSaveToNotebook={() => setShowSaveModal(true)}
            onDownloadMarkdown={handleDownloadMarkdown}
            onToggleViewerPanel={toggleViewerPanel}
          />
          <div className="flex w-full flex-1 min-h-0 flex-col overflow-hidden">
            {sessionLoading || sessionLoadFailed ? (
              <SessionLoadingView
                onCancel={cancelSessionLoad}
                failed={sessionLoadFailed}
                onRetry={retrySessionLoad}
              />
            ) : !hasMessages ? (
              <ChatWelcomeView greeting={t(welcomeGreeting)} />
            ) : (
              <div className="relative flex w-full flex-1 min-h-0 flex-col">
                <div
                  ref={messagesContainerRef}
                  data-chat-scroll-root="true"
                  onScroll={handleMessagesScroll}
                  onClick={handleMessagesClick}
                  className="w-full flex-1 min-h-0 overflow-y-auto [scrollbar-gutter:stable_both-edges] pt-6"
                  style={chatMessagesScrollStyle(hasMessages)}
                >
                  <div
                    data-chat-column="true"
                    className="mx-auto w-full max-w-[960px] space-y-9 px-6"
                  >
                    <ChatMessageList
                      messages={state.messages}
                      isStreaming={state.isStreaming}
                      sessionId={state.sessionId}
                      language={state.language}
                      onCopyAssistantMessage={copyAssistantMessage}
                      onRegenerateMessage={regenerateLastMessage}
                      onConfirmOutline={handleConfirmOutline}
                      onPreviewAttachment={handlePreviewMessageAttachment}
                      onDeleteTurn={deleteTurn}
                      selectedBranches={state.selectedBranches}
                      onEditMessage={editMessage}
                      onSwitchBranch={switchBranch}
                      onSubmitUserReply={submitUserReply}
                      availableKbNames={
                        knowledgeBasesLoaded ? availableKbNames : undefined
                      }
                    />
                    <div ref={messagesEndRef} className="h-px w-full shrink-0" />
                  </div>
                </div>
                <TurnNavigator
                  entries={chatOutline}
                  scrollRootRef={messagesContainerRef}
                  onJump={jumpToTurn}
                  onJumpToBottom={resumeFollowingLatest}
                />
              </div>
            )}

            {state.activeCapability === "mastery_path" &&
            state.masteryPathId ? (
              <MasteryPathStrip pathId={state.masteryPathId} />
            ) : null}
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
              hasMessages={hasMessages}
              attachments={attachments}
              attachmentError={attachmentError}
              activeCap={activeCap}
              knowledgeBases={kbOptions}
              connectedAgents={agentOptions}
              selectedAgent={selectedAgent}
              onSelectAgent={handleSelectAgent}
              subagentBudget={subagentBudget}
              onSubagentBudgetChange={setSubagentBudget}
              llmOptions={llmOptions}
              activeLLMDefault={activeLLMDefault}
              llmSelection={state.llmSelection}
              llmOptionsLoading={llmOptionsLoading}
              llmOptionsError={llmOptionsError}
              onRefreshLLMOptions={() =>
                void refreshLLMOptions({ force: true })
              }
              contextBudget={contextBudget}
              selectedBookReferences={selectedBookReferences}
              selectedNotebookRecords={selectedNotebookRecords}
              selectedHistorySessions={selectedHistorySessions}
              selectedAgentSessions={selectedAgentSessions}
              selectedQuestionEntries={selectedQuestionEntries}
              notebookReferenceGroups={notebookReferenceGroups}
              selectedPersona={null}
              selectedMemoryFiles={selectedMemoryFiles}
              selectedKnowledgeBases={selectedKbOnly}
              isStreaming={state.isStreaming}
              isVisualizeMode={isVisualizeMode}
              capabilityNeedsConfig={capabilityNeedsConfig}
              capabilityConfigConfirmed={capabilityConfigConfirmed}
              onRequestConfigConfirm={ensureActivityPanelOpen}
              capabilities={CAPABILITIES}
              onSetCapMenuOpen={setCapMenuOpen}
              onSetSpaceMenuOpen={setSpaceMenuOpen}
              onToggleKB={handleToggleKB}
              onSelectLLM={setLLMSelection}
              onSelectNotebookPicker={handleSelectNotebookPicker}
              onSelectBookPicker={handleSelectBookPicker}
              onSelectHistoryPicker={handleSelectHistoryPicker}
              onSelectAgentsPicker={handleSelectAgentsPicker}
              onSelectQuestionBankPicker={handleSelectQuestionBankPicker}
              onSelectPersonaPicker={handleSelectPersonaPicker}
              onSelectMemoryPicker={handleSelectMemoryPicker}
              onClearPersona={handleClearPersona}
              personaSelection={state.personaSelection}
              onPersonaSelectionChange={setPersonaSelection}
              personaSelectorOpen={personaSelectorOpen}
              onPersonaSelectorOpenChange={setPersonaSelectorOpen}
              onToggleMemoryFile={handleToggleMemoryFile}
              onSend={handleSend}
              onRemoveAttachment={removeAttachment}
              onPreviewAttachment={handlePreviewPendingAttachment}
              onRemoveHistory={handleRemoveHistory}
              onRemoveAgent={handleRemoveAgent}
              onRemoveBookReference={handleRemoveBookReference}
              onRemoveNotebook={handleRemoveNotebook}
              onRemoveQuestion={handleRemoveQuestion}
              onDragEnter={handleDragEnter}
              onDragLeave={handleDragLeave}
              onDragOver={handleDragOver}
              onDrop={handleDrop}
              onPaste={handlePaste}
              onAddFiles={handleAddFiles}
              onSelectCapability={handleSelectCapability}
              onCancelStreaming={cancelStreamingTurn}
              prefillInputRef={prefillInputRef}
            />
            {!hasMessages ? (
              <StarterSuggestions
                onPick={(prompt) => void handleSend(prompt)}
                disabled={state.isStreaming}
              />
            ) : null}
            <div
              aria-hidden="true"
              className="shrink-0"
              style={{
                flexGrow: hasMessages ? 0 : 1.4,
                transition: "flex-grow 650ms cubic-bezier(0.16, 1, 0.3, 1)",
              }}
            />
          </div>
          <ChatReferencePickers
            showNotebookPicker={showNotebookPicker}
            showBookPicker={showBookPicker}
            showHistoryPicker={showHistoryPicker}
            showAgentsPicker={showAgentsPicker}
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
            onCloseAgentsPicker={handleCloseAgentsPicker}
            onApplyAgentSessions={handleApplyAgentSessions}
            onCloseQuestionBankPicker={handleCloseQuestionBankPicker}
            onApplyQuestionEntries={handleApplyQuestionEntries}
            onCloseMemoryPicker={handleCloseMemoryPicker}
            onApplyMemoryFiles={handleApplyMemoryFiles}
          />
          <SaveToNotebookModal
            open={showSaveModal}
            payload={chatSavePayload}
            messages={chatSaveMessages}
            onClose={() => setShowSaveModal(false)}
          />
          <FilePreviewDrawer
            open={previewSource !== null}
            source={previewSource}
            onClose={handleClosePreview}
          />
          <SessionViewerPanel
            ref={viewerPanelRef}
            open={viewerPanelOpen && previewSource === null}
            sessionId={state.sessionId}
            activity={sessionActivity}
            configSection={capabilityConfigSection}
            onClose={() => setViewerOpen(false)}
            onAutoOpen={() => setViewerOpen(true)}
          />
        </div>
        </div>
      </GeogebraTabProvider>
    </QuizFollowupProvider>
  );
}
