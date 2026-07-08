"use client";

import dynamic from "next/dynamic";

import type { SelectedHistorySession } from "@/components/chat/HistorySessionPicker";
import type { SelectedQuestionEntry } from "@/components/chat/QuestionBankPicker";
import type { SelectedBookReference } from "@/lib/book-references";
import type { SelectedRecord } from "@/lib/notebook-selection-types";
import type { SpaceMemoryFile } from "@/lib/space-items";

const NotebookRecordPicker = dynamic(
  () => import("@/components/notebook/NotebookRecordPicker"),
  { ssr: false },
);
const HistorySessionPicker = dynamic(
  () => import("@/components/chat/HistorySessionPicker"),
  { ssr: false },
);
const MyAgentsPicker = dynamic(
  () => import("@/components/chat/MyAgentsPicker"),
  { ssr: false },
);
const QuestionBankPicker = dynamic(
  () => import("@/components/chat/QuestionBankPicker"),
  { ssr: false },
);
const MemoryPicker = dynamic(() => import("@/components/chat/MemoryPicker"), {
  ssr: false,
});
const BookReferencePicker = dynamic(
  () => import("@/components/chat/BookReferencePicker"),
  { ssr: false },
);

interface ChatReferencePickersProps {
  showNotebookPicker: boolean;
  showBookPicker: boolean;
  showHistoryPicker: boolean;
  showQuestionBankPicker: boolean;
  showMemoryPicker: boolean;
  selectedBookReferences: SelectedBookReference[];
  selectedMemoryFiles: SpaceMemoryFile[];
  onCloseNotebookPicker: () => void;
  onApplyNotebookRecords: (records: SelectedRecord[]) => void;
  onCloseBookPicker: () => void;
  onApplyBookReferences: (refs: SelectedBookReference[]) => void;
  onCloseHistoryPicker: () => void;
  onApplyHistorySessions: (sessions: SelectedHistorySession[]) => void;
  onCloseQuestionBankPicker: () => void;
  onApplyQuestionEntries: (entries: SelectedQuestionEntry[]) => void;
  onCloseMemoryPicker: () => void;
  onApplyMemoryFiles: (files: SpaceMemoryFile[]) => void;
  showAgentsPicker?: boolean;
  onCloseAgentsPicker?: () => void;
  onApplyAgentSessions?: (sessions: SelectedHistorySession[]) => void;
}

export default function ChatReferencePickers({
  showNotebookPicker,
  showBookPicker,
  showHistoryPicker,
  showAgentsPicker,
  showQuestionBankPicker,
  showMemoryPicker,
  selectedBookReferences,
  selectedMemoryFiles,
  onCloseNotebookPicker,
  onApplyNotebookRecords,
  onCloseBookPicker,
  onApplyBookReferences,
  onCloseHistoryPicker,
  onApplyHistorySessions,
  onCloseAgentsPicker,
  onApplyAgentSessions,
  onCloseQuestionBankPicker,
  onApplyQuestionEntries,
  onCloseMemoryPicker,
  onApplyMemoryFiles,
}: ChatReferencePickersProps) {
  return (
    <>
      <NotebookRecordPicker
        open={showNotebookPicker}
        onClose={onCloseNotebookPicker}
        onApply={onApplyNotebookRecords}
      />
      <BookReferencePicker
        open={showBookPicker}
        initialReferences={selectedBookReferences}
        onClose={onCloseBookPicker}
        onApply={onApplyBookReferences}
      />
      <HistorySessionPicker
        open={showHistoryPicker}
        onClose={onCloseHistoryPicker}
        onApply={onApplyHistorySessions}
      />
      {onCloseAgentsPicker && onApplyAgentSessions ? (
        <MyAgentsPicker
          open={Boolean(showAgentsPicker)}
          onClose={onCloseAgentsPicker}
          onApply={onApplyAgentSessions}
        />
      ) : null}
      <QuestionBankPicker
        open={showQuestionBankPicker}
        onClose={onCloseQuestionBankPicker}
        onApply={onApplyQuestionEntries}
      />
      <MemoryPicker
        open={showMemoryPicker}
        initialFiles={selectedMemoryFiles}
        onClose={onCloseMemoryPicker}
        onApply={onApplyMemoryFiles}
      />
    </>
  );
}
