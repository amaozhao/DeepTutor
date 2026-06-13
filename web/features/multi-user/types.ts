export type ModelAccessItem = {
  profile_id?: string;
  model_id?: string;
  name: string;
  model?: string;
  provider?: string;
  source?: "admin" | "user";
  available?: boolean;
};

export type ModelAccess = {
  llm: ModelAccessItem[];
  embedding: ModelAccessItem[];
  search: ModelAccessItem[];
};

export type CurrentUserAccess = {
  user: {
    id: string;
    username: string;
    role: "admin" | "user";
    is_admin: boolean;
  };
  models: Partial<ModelAccess>;
  knowledge_bases: Array<{
    id: string;
    name: string;
    source: "admin" | "user";
    assigned?: boolean;
    read_only?: boolean;
    available?: boolean;
    provenance_label?: string;
  }>;
  skills: string[];
  spaces: Array<Record<string, unknown>>;
};

export type GrantPayload = {
  version: number;
  user_id: string;
  models: {
    llm: Array<Record<string, unknown>>;
  };
  knowledge_bases: Array<Record<string, unknown>>;
  skills: Array<Record<string, unknown>>;
  /** null = default (all system tools), [] = none, array = whitelist. */
  enabled_tools: string[] | null;
  /** null = default (all MCP tools), [] = none, array = whitelist. */
  mcp_tools: string[] | null;
  /** null = follow deployment exec policy, false = always disabled. */
  exec_enabled: boolean | null;
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
  tools: ToolOption[];
  mcp_tools: McpToolOption[];
};
