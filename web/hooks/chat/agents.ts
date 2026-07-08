"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  agentKnowledgeBaseNames,
  chatKnowledgeBaseOptions,
  connectedAgentOptions,
  selectedConnectedAgent,
  withoutConnectedAgents,
  type ChatAgentKnowledgeBase,
} from "@/lib/chat/agents";
import { getSubagentSettings } from "@/lib/subagents-api";

type ChatAgentsInput = {
  knowledgeBases: ChatAgentKnowledgeBase[];
  selectedKnowledgeBases: string[];
  setKnowledgeBases: (knowledgeBases: string[]) => void;
};

export function useChatAgents({
  knowledgeBases,
  selectedKnowledgeBases,
  setKnowledgeBases,
}: ChatAgentsInput) {
  const pendingAgentRef = useRef<string | null | undefined>(undefined);
  if (pendingAgentRef.current === undefined) {
    pendingAgentRef.current =
      typeof window === "undefined"
        ? null
        : new URLSearchParams(window.location.search).get("agent");
  }
  const agentPreselectDoneRef = useRef(false);

  const agentNameSet = useMemo(
    () => agentKnowledgeBaseNames(knowledgeBases),
    [knowledgeBases],
  );
  const kbOptions = useMemo(
    () => chatKnowledgeBaseOptions(knowledgeBases),
    [knowledgeBases],
  );
  const agentOptions = useMemo(
    () => connectedAgentOptions(knowledgeBases),
    [knowledgeBases],
  );
  const selectedKbOnly = useMemo(
    () => withoutConnectedAgents(selectedKnowledgeBases, agentNameSet),
    [selectedKnowledgeBases, agentNameSet],
  );
  const selectedAgent = useMemo(
    () => selectedConnectedAgent(selectedKnowledgeBases, agentNameSet),
    [selectedKnowledgeBases, agentNameSet],
  );

  const handleSelectAgent = useCallback(
    (name: string | null) => {
      const withoutAgents = withoutConnectedAgents(
        selectedKnowledgeBases,
        agentNameSet,
      );
      setKnowledgeBases(name ? [...withoutAgents, name] : withoutAgents);
    },
    [setKnowledgeBases, selectedKnowledgeBases, agentNameSet],
  );

  useEffect(() => {
    if (agentPreselectDoneRef.current) return;
    const name = pendingAgentRef.current;
    if (!name || !agentNameSet.has(name)) return;
    agentPreselectDoneRef.current = true;
    handleSelectAgent(name);
  }, [agentNameSet, handleSelectAgent]);

  const [subagentBudget, setSubagentBudget] = useState<number | null>(null);
  useEffect(() => {
    void getSubagentSettings()
      .then((settings) => setSubagentBudget(settings.consult_budget))
      .catch(() => undefined);
  }, []);

  return {
    kbOptions,
    agentOptions,
    selectedKbOnly,
    selectedAgent,
    handleSelectAgent,
    subagentBudget,
    setSubagentBudget,
  };
}
