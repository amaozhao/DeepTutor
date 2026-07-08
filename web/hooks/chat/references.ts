"use client";

import { useCallback, useMemo, useState } from "react";

import type { SelectedHistorySession } from "@/components/chat/HistorySessionPicker";
import type { SelectedQuestionEntry } from "@/components/chat/QuestionBankPicker";
import type { SelectedRecord } from "@/lib/notebook-selection-types";
import {
  buildNotebookReferenceGroups,
  buildNotebookReferencesPayload,
  uniqueHistoryReferenceIds,
} from "@/lib/chat/references";
import {
  selectedBooksToPayload,
  type SelectedBookReference,
} from "@/lib/book-references";
import type { SpaceMemoryFile } from "@/lib/space-items";

export function useChatReferences() {
  const [showNotebookPicker, setShowNotebookPicker] = useState(false);
  const [showBookPicker, setShowBookPicker] = useState(false);
  const [showHistoryPicker, setShowHistoryPicker] = useState(false);
  const [showAgentsPicker, setShowAgentsPicker] = useState(false);
  const [showQuestionBankPicker, setShowQuestionBankPicker] = useState(false);
  const [showMemoryPicker, setShowMemoryPicker] = useState(false);

  const [selectedNotebookRecords, setSelectedNotebookRecords] = useState<
    SelectedRecord[]
  >([]);
  const [selectedBookReferences, setSelectedBookReferences] = useState<
    SelectedBookReference[]
  >([]);
  const [selectedHistorySessions, setSelectedHistorySessions] = useState<
    SelectedHistorySession[]
  >([]);
  const [selectedAgentSessions, setSelectedAgentSessions] = useState<
    SelectedHistorySession[]
  >([]);
  const [selectedQuestionEntries, setSelectedQuestionEntries] = useState<
    SelectedQuestionEntry[]
  >([]);
  const [selectedMemoryFiles, setSelectedMemoryFiles] = useState<
    SpaceMemoryFile[]
  >([]);

  const notebookReferenceGroups = useMemo(
    () => buildNotebookReferenceGroups(selectedNotebookRecords),
    [selectedNotebookRecords],
  );
  const notebookReferencesPayload = useMemo(
    () => buildNotebookReferencesPayload(selectedNotebookRecords),
    [selectedNotebookRecords],
  );
  const bookReferencesPayload = useMemo(
    () => selectedBooksToPayload(selectedBookReferences),
    [selectedBookReferences],
  );
  const historyReferencesPayload = useMemo(
    () =>
      uniqueHistoryReferenceIds(
        selectedHistorySessions,
        selectedAgentSessions,
      ),
    [selectedHistorySessions, selectedAgentSessions],
  );
  const questionNotebookReferencesPayload = useMemo(
    () => selectedQuestionEntries.map((entry) => entry.id),
    [selectedQuestionEntries],
  );
  const memoryReferencesPayload = useMemo(
    () => [...selectedMemoryFiles],
    [selectedMemoryFiles],
  );

  const handleSelectNotebookPicker = useCallback(() => {
    setShowNotebookPicker(true);
  }, []);
  const handleSelectBookPicker = useCallback(() => {
    setShowBookPicker(true);
  }, []);
  const handleSelectHistoryPicker = useCallback(() => {
    setShowHistoryPicker(true);
  }, []);
  const handleSelectAgentsPicker = useCallback(() => {
    setShowAgentsPicker(true);
  }, []);
  const handleSelectQuestionBankPicker = useCallback(() => {
    setShowQuestionBankPicker(true);
  }, []);
  const handleSelectMemoryPicker = useCallback(() => {
    setShowMemoryPicker(true);
  }, []);

  const handleRemoveHistory = useCallback((sessionId: string) => {
    setSelectedHistorySessions((prev) =>
      prev.filter((item) => item.sessionId !== sessionId),
    );
  }, []);
  const handleRemoveAgent = useCallback((sessionId: string) => {
    setSelectedAgentSessions((prev) =>
      prev.filter((item) => item.sessionId !== sessionId),
    );
  }, []);
  const handleRemoveNotebook = useCallback((notebookId: string) => {
    setSelectedNotebookRecords((prev) =>
      prev.filter((record) => record.notebookId !== notebookId),
    );
  }, []);
  const handleRemoveBookReference = useCallback((bookId: string) => {
    setSelectedBookReferences((prev) =>
      prev.filter((record) => record.bookId !== bookId),
    );
  }, []);
  const handleRemoveQuestion = useCallback((entryId: number) => {
    setSelectedQuestionEntries((prev) =>
      prev.filter((entry) => entry.id !== entryId),
    );
  }, []);

  const handleToggleMemoryFile = useCallback((file: SpaceMemoryFile) => {
    setSelectedMemoryFiles((prev) =>
      prev.includes(file)
        ? prev.filter((item) => item !== file)
        : [...prev, file],
    );
  }, []);

  const handleCloseNotebookPicker = useCallback(() => {
    setShowNotebookPicker(false);
  }, []);
  const handleCloseBookPicker = useCallback(() => {
    setShowBookPicker(false);
  }, []);
  const handleCloseHistoryPicker = useCallback(() => {
    setShowHistoryPicker(false);
  }, []);
  const handleCloseAgentsPicker = useCallback(() => {
    setShowAgentsPicker(false);
  }, []);
  const handleCloseQuestionBankPicker = useCallback(() => {
    setShowQuestionBankPicker(false);
  }, []);
  const handleCloseMemoryPicker = useCallback(() => {
    setShowMemoryPicker(false);
  }, []);

  const clearSelectedReferences = useCallback(() => {
    setSelectedBookReferences([]);
    setSelectedNotebookRecords([]);
    setSelectedHistorySessions([]);
    setSelectedAgentSessions([]);
    setSelectedQuestionEntries([]);
    setSelectedMemoryFiles([]);
  }, []);

  return {
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
    handleApplyBookReferences: setSelectedBookReferences,
    handleApplyNotebookRecords: setSelectedNotebookRecords,
    handleCloseHistoryPicker,
    handleApplyHistorySessions: setSelectedHistorySessions,
    handleCloseAgentsPicker,
    handleApplyAgentSessions: setSelectedAgentSessions,
    handleCloseQuestionBankPicker,
    handleApplyQuestionEntries: setSelectedQuestionEntries,
    handleCloseMemoryPicker,
    handleApplyMemoryFiles: setSelectedMemoryFiles,
    clearSelectedReferences,
  };
}
