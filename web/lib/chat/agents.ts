export interface ChatAgentKnowledgeBase {
  name: string;
  metadata?: {
    type?: string;
    agent_kind?: string;
  };
}

export function agentKnowledgeBaseNames(
  knowledgeBases: ChatAgentKnowledgeBase[],
): Set<string> {
  return new Set(
    knowledgeBases
      .filter((kb) => kb.metadata?.type === "subagent")
      .map((kb) => kb.name),
  );
}

export function chatKnowledgeBaseOptions(
  knowledgeBases: ChatAgentKnowledgeBase[],
): ChatAgentKnowledgeBase[] {
  return knowledgeBases.filter((kb) => kb.metadata?.type !== "subagent");
}

export function connectedAgentOptions(
  knowledgeBases: ChatAgentKnowledgeBase[],
): Array<{ name: string; kind?: string }> {
  return knowledgeBases
    .filter((kb) => kb.metadata?.type === "subagent")
    .map((kb) => ({ name: kb.name, kind: kb.metadata?.agent_kind }));
}

export function withoutConnectedAgents(
  selectedKnowledgeBases: string[],
  agentNames: Set<string>,
): string[] {
  return selectedKnowledgeBases.filter((name) => !agentNames.has(name));
}

export function selectedConnectedAgent(
  selectedKnowledgeBases: string[],
  agentNames: Set<string>,
): string | null {
  return selectedKnowledgeBases.find((name) => agentNames.has(name)) ?? null;
}

export function toggleKnowledgeBaseSelection(
  selectedKnowledgeBases: string[],
  name: string,
): string[] {
  return selectedKnowledgeBases.includes(name)
    ? selectedKnowledgeBases.filter((kb) => kb !== name)
    : [...selectedKnowledgeBases, name];
}
