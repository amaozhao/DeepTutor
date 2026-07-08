"use client";

import type { KeyboardEvent, RefObject } from "react";
import { BookmarkPlus, Download, PanelRight, PenLine } from "lucide-react";

import HeaderActionButton from "@/components/chat/home/HeaderActionButton";

type ChatHeaderProps = {
  titleInputRef: RefObject<HTMLInputElement | null>;
  sessionTitleEditing: boolean;
  sessionTitleDraft: string;
  displaySessionTitle: string;
  canRenameSession: boolean;
  sessionTitleSaving: boolean;
  sessionTitleError: string | null;
  canSaveChat: boolean;
  canDownloadChat: boolean;
  viewerPanelOpen: boolean;
  labels: {
    sessionTitle: string;
    clickToRenameSession: string;
    startConversationToRename: string;
    saving: string;
    saveToNotebook: string;
    downloadMarkdown: string;
    downloadMarkdownTitle: string;
    activity: string;
    activityTitle: string;
  };
  onSessionTitleDraftChange: (value: string) => void;
  onCommitSessionTitleEdit: () => void;
  onSessionTitleKeyDown: (event: KeyboardEvent<HTMLInputElement>) => void;
  onStartSessionTitleEdit: () => void;
  onSaveToNotebook: () => void;
  onDownloadMarkdown: () => void;
  onToggleViewerPanel: () => void;
};

export default function ChatHeader({
  titleInputRef,
  sessionTitleEditing,
  sessionTitleDraft,
  displaySessionTitle,
  canRenameSession,
  sessionTitleSaving,
  sessionTitleError,
  canSaveChat,
  canDownloadChat,
  viewerPanelOpen,
  labels,
  onSessionTitleDraftChange,
  onCommitSessionTitleEdit,
  onSessionTitleKeyDown,
  onStartSessionTitleEdit,
  onSaveToNotebook,
  onDownloadMarkdown,
  onToggleViewerPanel,
}: ChatHeaderProps) {
  return (
    <div className="mx-auto flex w-full max-w-[960px] flex-wrap items-center justify-between gap-x-3 gap-y-1.5 px-6 pt-3 pb-0">
      <div className="group/title min-w-0 flex flex-1 items-center gap-2">
        {sessionTitleEditing ? (
          <input
            ref={titleInputRef}
            value={sessionTitleDraft}
            onChange={(event) => onSessionTitleDraftChange(event.target.value)}
            onBlur={onCommitSessionTitleEdit}
            onKeyDown={onSessionTitleKeyDown}
            disabled={sessionTitleSaving}
            aria-label={labels.sessionTitle}
            className="min-w-0 flex-1 rounded-xl border border-[var(--border)] bg-[var(--background)] px-3 py-1.5 font-serif text-[17px] font-semibold tracking-[-0.01em] text-[var(--foreground)] shadow-sm outline-none transition focus:border-[var(--ring)] focus:ring-2 focus:ring-[var(--ring)]/20 disabled:opacity-60"
            maxLength={100}
          />
        ) : (
          <button
            type="button"
            onClick={onStartSessionTitleEdit}
            disabled={!canRenameSession}
            title={
              canRenameSession
                ? labels.clickToRenameSession
                : labels.startConversationToRename
            }
            className="inline-flex min-w-0 max-w-full items-center gap-2 rounded-xl px-2 py-1 text-left font-serif text-[17px] font-semibold tracking-[-0.01em] text-[var(--foreground)] transition hover:bg-[var(--muted)]/55 disabled:cursor-default disabled:hover:bg-transparent"
          >
            <span className="truncate">{displaySessionTitle}</span>
            {canRenameSession ? (
              <PenLine className="h-3.5 w-3.5 shrink-0 text-[var(--muted-foreground)] opacity-0 transition-opacity group-hover/title:opacity-100" />
            ) : null}
          </button>
        )}
        {sessionTitleSaving ? (
          <span className="shrink-0 text-xs text-[var(--muted-foreground)]">
            {labels.saving}
          </span>
        ) : null}
        {sessionTitleError ? (
          <span className="shrink-0 text-xs text-[var(--destructive)]">
            {sessionTitleError}
          </span>
        ) : null}
      </div>
      <div className="flex shrink-0 items-center gap-0.5">
        <HeaderActionButton
          onClick={onSaveToNotebook}
          disabled={!canSaveChat}
          icon={BookmarkPlus}
          label={labels.saveToNotebook}
        />
        <HeaderActionButton
          onClick={onDownloadMarkdown}
          disabled={!canDownloadChat}
          icon={Download}
          label={labels.downloadMarkdown}
          title={labels.downloadMarkdownTitle}
        />
        <HeaderActionButton
          onClick={onToggleViewerPanel}
          active={viewerPanelOpen}
          icon={PanelRight}
          label={labels.activity}
          title={labels.activityTitle}
        />
      </div>
    </div>
  );
}
