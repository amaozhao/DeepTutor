import type { CapabilityDef, ToolName } from "@/lib/capabilities";
import type { LLMSelection } from "@/lib/unified-ws";

type CapabilityConfigMap = Record<
  string,
  {
    enabledTools?: string[];
    knowledgeBase?: string;
  }
>;

const hiddenFrontendTools = new Set(["geogebra_analysis"]);

export type PersistedChatCapabilityConfig = {
  quizConfig?: unknown;
  visualizeConfig?: unknown;
  researchConfig?: unknown;
  capabilityConfigConfirmed?: boolean;
};

export type ChatQueryCapabilityPlan =
  | { type: "capability"; value: string }
  | { type: "tools"; tools: string[] }
  | null;

export type ChatCapabilityMode = {
  isQuizMode: boolean;
  isVisualizeMode: boolean;
  isResearchMode: boolean;
  capabilityNeedsConfig: boolean;
};

export function chatCapabilityMode(
  capability: string | null | undefined,
): ChatCapabilityMode {
  const isQuizMode = capability === "deep_question";
  const isVisualizeMode = capability === "visualize";
  const isResearchMode = capability === "deep_research";
  return {
    isQuizMode,
    isVisualizeMode,
    isResearchMode,
    capabilityNeedsConfig: isQuizMode || isVisualizeMode || isResearchMode,
  };
}

export function shouldAutoOpenCapabilityConfig(
  previousNeedsConfig: boolean,
  nextNeedsConfig: boolean,
): boolean {
  return !previousNeedsConfig && nextNeedsConfig;
}

export function chatDefaultLLMSelectionPlan({
  current,
  defaultSelection,
}: {
  current: LLMSelection | null | undefined;
  defaultSelection: LLMSelection | null | undefined;
}): LLMSelection | null {
  return current || !defaultSelection ? null : defaultSelection;
}

export function chatEnabledToolsSyncPlan({
  userEnabledTools,
  allowedTools,
  currentTools,
}: {
  userEnabledTools: string[] | null;
  allowedTools: string[];
  currentTools: string[];
}): string[] | null {
  if (userEnabledTools === null) return null;
  const allowed = new Set(allowedTools);
  const next = userEnabledTools.filter((tool) => allowed.has(tool));
  const same =
    currentTools.length === next.length &&
    currentTools.every((tool, idx) => tool === next[idx]);
  return same ? null : next;
}

export function chatCapabilityConfigStorageKey(
  sessionId: string | null | undefined,
  sessionIdParam: string | null | undefined,
): string | null {
  const sid = sessionId || sessionIdParam || "";
  return sid ? `dt:chat:capability-config:${sid}` : null;
}

export function parsePersistedChatCapabilityConfig(
  raw: string | null,
): PersistedChatCapabilityConfig | null {
  if (!raw) return null;
  try {
    return JSON.parse(raw) as PersistedChatCapabilityConfig;
  } catch {
    return null;
  }
}

export function chatCapabilitySelectionPlan({
  value,
  capabilities,
  capabilityConfigs,
  userEnabledTools,
}: {
  value: string;
  capabilities: CapabilityDef[];
  capabilityConfigs: CapabilityConfigMap;
  userEnabledTools: string[] | null;
}): {
  capability: CapabilityDef;
  capabilityValue: string | null;
  enabledTools: string[];
  knowledgeBases: string[];
} {
  const capability =
    capabilities.find((item) => item.value === value) ?? capabilities[0];
  const storageKey = capability.value || "chat";
  const config = capabilityConfigs[storageKey];
  const baseline =
    userEnabledTools === null ? capability.allowedTools : userEnabledTools;
  const enabledTools = config
    ? Array.from(
        new Set(config.enabledTools ?? capability.allowedTools),
      ).filter((tool) => !hiddenFrontendTools.has(tool))
    : baseline.filter((tool) =>
        capability.allowedTools.includes(tool as ToolName),
      );
  return {
    capability,
    capabilityValue: capability.value || null,
    enabledTools,
    knowledgeBases: config?.knowledgeBase ? [config.knowledgeBase] : [],
  };
}

export function chatQueryCapabilityPlan({
  query,
  validTools,
}: {
  query: string;
  validTools: string[];
}): ChatQueryCapabilityPlan {
  const params = new URLSearchParams(query);
  const capability = params.get("capability");
  if (capability !== null) return { type: "capability", value: capability };
  const requestedTools = params.getAll("tool");
  if (!requestedTools.length) return null;
  const allowed = new Set(validTools);
  const tools = Array.from(
    new Set(requestedTools.filter((tool) => allowed.has(tool))),
  );
  return tools.length ? { type: "tools", tools } : null;
}
