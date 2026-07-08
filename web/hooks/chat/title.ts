"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { KeyboardEvent } from "react";

import { decideSessionTitleCommit } from "@/lib/chat/title";

type SessionTitleEditorInput = {
  canRename: boolean;
  displayTitle: string;
  persistedTitle: string;
  renameSessionTitle: (title: string) => Promise<void>;
  renameFailedLabel: string;
};

export function useSessionTitleEditor({
  canRename,
  displayTitle,
  persistedTitle,
  renameSessionTitle,
  renameFailedLabel,
}: SessionTitleEditorInput) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const skipCommitRef = useRef(false);
  const [draft, setDraft] = useState(displayTitle);
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (editing) return;
    setDraft(displayTitle);
  }, [displayTitle, editing]);

  useEffect(() => {
    if (!editing) return;
    window.requestAnimationFrame(() => {
      inputRef.current?.focus();
      inputRef.current?.select();
    });
  }, [editing]);

  const start = useCallback(() => {
    if (!canRename) return;
    skipCommitRef.current = false;
    setError(null);
    setDraft(displayTitle);
    setEditing(true);
  }, [canRename, displayTitle]);

  const cancel = useCallback(() => {
    skipCommitRef.current = true;
    setDraft(displayTitle);
    setError(null);
    setEditing(false);
  }, [displayTitle]);

  const commit = useCallback(async () => {
    if (skipCommitRef.current) {
      skipCommitRef.current = false;
      return;
    }
    const decision = decideSessionTitleCommit({
      canRename,
      displayTitle,
      draftTitle: draft,
      persistedTitle,
    });
    if (decision.type === "close") {
      setDraft(decision.draftTitle);
      setEditing(false);
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await renameSessionTitle(decision.title);
      setEditing(false);
    } catch (err) {
      console.error("Failed to rename session:", err);
      setError(renameFailedLabel);
      inputRef.current?.focus();
    } finally {
      setSaving(false);
    }
  }, [
    canRename,
    displayTitle,
    draft,
    persistedTitle,
    renameFailedLabel,
    renameSessionTitle,
  ]);

  const handleKeyDown = useCallback(
    (event: KeyboardEvent<HTMLInputElement>) => {
      if (event.key === "Enter") {
        event.preventDefault();
        void commit();
      } else if (event.key === "Escape") {
        event.preventDefault();
        cancel();
      }
    },
    [cancel, commit],
  );

  return {
    inputRef,
    draft,
    setDraft,
    editing,
    saving,
    error,
    start,
    commit,
    handleKeyDown,
  };
}
