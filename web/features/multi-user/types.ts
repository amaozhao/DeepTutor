export type UserQuota = {
  daily_token_limit: number;
  monthly_token_limit: number;
  daily_call_limit: number;
  monthly_call_limit: number;
  daily_cost_limit_usd: number;
  monthly_cost_limit_usd: number;
};

export type UsageMetrics = {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  total_calls: number;
  total_cost_usd: number;
};

export type UserUsageResponse = {
  quota: UserQuota;
  usage: {
    today: UsageMetrics;
    month: UsageMetrics;
    all: UsageMetrics;
  };
};

export type DeleteDataAction = "keep" | "archive" | "delete";

export type AuditEvent = {
  time?: string;
  action?: string;
  actor_username?: string;
  actor_role?: string;
  target_user_id?: string;
  summary?: Record<string, unknown>;
};

export type GrantPayload = {
  version: number;
  user_id: string;
  models: {
    llm: Array<Record<string, unknown>>;
  };
  knowledge_bases: Array<Record<string, unknown>>;
  skills: Array<Record<string, unknown>>;
  /** Admin-assigned partners the user may see & consult ([{ partner_id }]). */
  partners: Array<Record<string, unknown>>;
  /** null = default (all system tools), [] = none, array = whitelist. */
  enabled_tools: string[] | null;
  /** null = default (all MCP tools), [] = none, array = whitelist. */
  mcp_tools: string[] | null;
  /** null = follow deployment exec policy, false = always disabled. */
  exec_enabled: boolean | null;
  /** Zero means unlimited. */
  quota: UserQuota;
};

export type ToolOption = { name: string; description?: string };

export type McpToolOption = {
  name: string;
  server?: string;
  description?: string;
};

export type MultiUserResources = {
  models: {
    llm: Array<{
      profile_id: string;
      name: string;
      models?: Array<{ model_id: string; name: string; model?: string }>;
    }>;
  };
  knowledge_bases: Array<{
    resource_id: string;
    name: string;
    source: "admin";
  }>;
  skills: Array<{ name: string; description?: string; tags?: string[] }>;
  partners: Array<{ partner_id: string; name: string; description?: string }>;
  tools: ToolOption[];
  mcp_tools: McpToolOption[];
};
