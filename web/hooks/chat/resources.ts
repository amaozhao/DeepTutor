"use client";

import { useCallback, useEffect, useState } from "react";

import { listKnowledgeBases } from "@/lib/knowledge-api";
import { listLLMOptions, type LLMOption } from "@/lib/llm-options";
import {
  loadCapabilityPlaygroundConfigs,
  type CapabilityPlaygroundConfigMap,
} from "@/lib/playground-config";
import {
  getEnabledOptionalTools,
  invalidateEnabledOptionalToolsCache,
} from "@/lib/tools-settings";
import type { LLMSelection } from "@/lib/unified-ws";
import { chatDefaultLLMSelectionPlan } from "@/lib/chat/capability";

export interface ChatKnowledgeBase {
  name: string;
  is_default?: boolean;
  metadata?: {
    /** Connected-source kind, e.g. "obsidian" | "subagent". */
    type?: string;
    /** Backend of a connected subagent: "claude_code" | "codex" | "partner". */
    agent_kind?: string;
    rag_provider?: string;
  };
  statistics?: { rag_provider?: string };
}

export function useChatBasicResources() {
  const [knowledgeBases, setKnowledgeBases] = useState<ChatKnowledgeBase[]>([]);
  const [knowledgeBasesLoaded, setKnowledgeBasesLoaded] = useState(false);
  const [llmOptions, setLLMOptions] = useState<LLMOption[]>([]);
  const [activeLLMDefault, setActiveLLMDefault] = useState<LLMSelection | null>(
    null,
  );
  const [llmOptionsLoading, setLLMOptionsLoading] = useState(true);
  const [llmOptionsError, setLLMOptionsError] = useState(false);

  const refreshKnowledgeBases = useCallback(
    async (options?: { force?: boolean }) => {
      try {
        const list = await listKnowledgeBases({ force: options?.force });
        setKnowledgeBases(list);
        setKnowledgeBasesLoaded(true);
      } catch {
        setKnowledgeBasesLoaded(false);
        setKnowledgeBases([]);
      }
    },
    [],
  );

  const refreshLLMOptions = useCallback(async (options?: { force?: boolean }) => {
    setLLMOptionsLoading(true);
    try {
      const payload = await listLLMOptions(options);
      setLLMOptions(payload.options);
      setActiveLLMDefault(payload.active);
      setLLMOptionsError(false);
    } catch {
      setLLMOptionsError(true);
      setLLMOptions([]);
      setActiveLLMDefault(null);
    } finally {
      setLLMOptionsLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshKnowledgeBases({ force: true });
  }, [refreshKnowledgeBases]);

  useEffect(() => {
    void refreshLLMOptions();
  }, [refreshLLMOptions]);

  return {
    knowledgeBases,
    knowledgeBasesLoaded,
    llmOptions,
    activeLLMDefault,
    llmOptionsLoading,
    llmOptionsError,
    refreshKnowledgeBases,
    refreshLLMOptions,
  };
}

export function useChatResources() {
  const {
    knowledgeBases,
    knowledgeBasesLoaded,
    llmOptions,
    activeLLMDefault,
    llmOptionsLoading,
    llmOptionsError,
    refreshKnowledgeBases,
    refreshLLMOptions,
  } = useChatBasicResources();
  const [capabilityConfigs, setCapabilityConfigs] =
    useState<CapabilityPlaygroundConfigMap>({});
  const [userEnabledTools, setUserEnabledTools] = useState<string[] | null>(
    null,
  );

  const refreshUserEnabledTools = useCallback(
    async (options?: { force?: boolean }) => {
      try {
        const list = await getEnabledOptionalTools({ force: options?.force });
        setUserEnabledTools(list);
      } catch {
        setUserEnabledTools([]);
      }
    },
    [],
  );

  useEffect(() => {
    void refreshUserEnabledTools({ force: true });
  }, [refreshUserEnabledTools]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const refresh = () => {
      void refreshKnowledgeBases({ force: true });
      void refreshLLMOptions();
      invalidateEnabledOptionalToolsCache();
      void refreshUserEnabledTools({ force: true });
    };
    const refreshWhenVisible = () => {
      if (document.visibilityState === "visible") refresh();
    };
    window.addEventListener("focus", refresh);
    window.addEventListener("pageshow", refresh);
    document.addEventListener("visibilitychange", refreshWhenVisible);
    return () => {
      window.removeEventListener("focus", refresh);
      window.removeEventListener("pageshow", refresh);
      document.removeEventListener("visibilitychange", refreshWhenVisible);
    };
  }, [refreshKnowledgeBases, refreshLLMOptions, refreshUserEnabledTools]);

  useEffect(() => {
    setCapabilityConfigs(loadCapabilityPlaygroundConfigs());
  }, []);

  return {
    knowledgeBases,
    knowledgeBasesLoaded,
    llmOptions,
    activeLLMDefault,
    llmOptionsLoading,
    llmOptionsError,
    capabilityConfigs,
    userEnabledTools,
    refreshLLMOptions,
  };
}

export function useChatDefaultLLMSelection({
  currentSelection,
  activeLLMDefault,
  setLLMSelection,
}: {
  currentSelection: LLMSelection | null;
  activeLLMDefault: LLMSelection | null;
  setLLMSelection: (selection: LLMSelection | null) => void;
}) {
  useEffect(() => {
    const next = chatDefaultLLMSelectionPlan({
      current: currentSelection,
      defaultSelection: activeLLMDefault,
    });
    if (next) setLLMSelection(next);
  }, [activeLLMDefault, currentSelection, setLLMSelection]);
}
