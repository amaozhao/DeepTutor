export type ServiceName =
  | "llm"
  | "embedding"
  | "search"
  | "tts"
  | "stt"
  | "imagegen"
  | "videogen";

export type CatalogModel = {
  id: string;
  name: string;
  model: string;
  dimension?: string;
  send_dimensions?: boolean;
  supported_dimensions?: string;
  context_window?: string;
  context_window_source?: string;
  context_window_detected_at?: string;
  voice?: string;
  response_format?: string;
  language?: string;
  size?: string;
  quality?: string;
  style?: string;
  aspect_ratio?: string;
  duration?: string;
  resolution?: string;
};

export type LlmContextWindowDetection = {
  profileId: string | null;
  modelId: string | null;
  contextWindow: number;
  source: string;
  detail?: string;
  detectedAt?: string;
};

export type CatalogProfile = {
  id: string;
  name: string;
  binding?: string;
  provider?: string;
  base_url: string;
  api_key: string;
  api_version: string;
  extra_headers?: Record<string, string> | string;
  proxy?: string;
  max_results?: number;
  models: CatalogModel[];
};

export type CatalogService = {
  active_profile_id: string | null;
  active_model_id?: string | null;
  profiles: CatalogProfile[];
};

export type Catalog = {
  version: number;
  services: Record<ServiceName, CatalogService>;
};

export type UiSettings = {
  theme: "light" | "dark" | "glass" | "snow";
  language: "en" | "zh";
  code_block_theme: string;
  code_block_show_line_numbers: boolean;
  code_block_wrap_long_lines: boolean;
};

export type ProviderOption = {
  value: string;
  label: string;
  base_url?: string;
  default_dim?: string;
  default_model?: string;
  default_voice?: string;
};

export type SystemStatus = {
  backend: { status: string; timestamp: string };
  llm: { status: string; model?: string; error?: string };
  embeddings: { status: string; model?: string; error?: string };
  search: { status: string; provider?: string; error?: string };
  deployment?: {
    status: string;
    multi_replica_ready: boolean;
    shared_state?: Record<string, string>;
    blocking_reasons?: string[];
  };
};

export type EmbeddingCapabilities = {
  detected_dim?: number;
  default_dim?: number;
  supported_dimensions?: number[];
  supports_variable_dimensions?: boolean;
  model_known?: boolean;
  active_dim?: number;
  active_dim_source?: string;
};

export type DiagnosticsResult = {
  state: "success" | "failed";
  message: string;
  profileId: string | null;
  modelId: string | null;
};

export type ServiceReadiness =
  | "not_configured"
  | "untested"
  | "passed"
  | "failed";

export function cloneCatalog(catalog: Catalog): Catalog {
  return JSON.parse(JSON.stringify(catalog)) as Catalog;
}

export function voiceService(service: ServiceName): boolean {
  return service === "tts" || service === "stt";
}

export function generationService(service: ServiceName): boolean {
  return service === "imagegen" || service === "videogen";
}

export function prefillsDefaultModel(service: ServiceName): boolean {
  return voiceService(service) || generationService(service);
}

export function defaultCatalog(): Catalog {
  return {
    version: 1,
    services: {
      llm: { active_profile_id: null, active_model_id: null, profiles: [] },
      embedding: { active_profile_id: null, active_model_id: null, profiles: [] },
      search: { active_profile_id: null, profiles: [] },
      tts: { active_profile_id: null, active_model_id: null, profiles: [] },
      stt: { active_profile_id: null, active_model_id: null, profiles: [] },
      imagegen: { active_profile_id: null, active_model_id: null, profiles: [] },
      videogen: { active_profile_id: null, active_model_id: null, profiles: [] },
    },
  };
}

export function getActiveProfile(
  catalog: Catalog,
  serviceName: ServiceName,
): CatalogProfile | null {
  const service = catalog.services[serviceName];
  return (
    service.profiles.find(
      (profile) => profile.id === service.active_profile_id,
    ) ??
    service.profiles[0] ??
    null
  );
}

export function getActiveModel(
  catalog: Catalog,
  serviceName: ServiceName,
): CatalogModel | null {
  if (serviceName === "search") return null;
  const service = catalog.services[serviceName];
  const profile = getActiveProfile(catalog, serviceName);
  if (!profile) return null;
  return (
    profile.models.find((model) => model.id === service.active_model_id) ??
    profile.models[0] ??
    null
  );
}

export function serviceConfigured(
  catalog: Catalog,
  serviceName: ServiceName,
): boolean {
  return serviceName === "search"
    ? Boolean(getActiveProfile(catalog, serviceName)?.provider)
    : Boolean(getActiveModel(catalog, serviceName)?.model);
}

export function currentDiagnosticsResult(
  catalog: Catalog,
  serviceName: ServiceName,
  diagnosticsResults: Partial<Record<ServiceName, DiagnosticsResult>>,
): DiagnosticsResult | null {
  const service = catalog.services[serviceName];
  const diagnostics = diagnosticsResults[serviceName];
  if (!diagnostics) return null;
  const profileId = service.active_profile_id ?? null;
  const modelId =
    serviceName === "search" ? null : (service.active_model_id ?? null);
  return diagnostics.profileId === profileId && diagnostics.modelId === modelId
    ? diagnostics
    : null;
}

export function serviceReadiness(
  catalog: Catalog,
  serviceName: ServiceName,
  diagnosticsResults: Partial<Record<ServiceName, DiagnosticsResult>>,
): ServiceReadiness {
  if (!serviceConfigured(catalog, serviceName)) return "not_configured";
  const diagnostics = currentDiagnosticsResult(
    catalog,
    serviceName,
    diagnosticsResults,
  );
  if (diagnostics?.state === "failed") return "failed";
  if (diagnostics?.state === "success") return "passed";
  return "untested";
}

export function servicePendingApply(
  catalog: Catalog,
  draft: Catalog,
  service: ServiceName,
): boolean {
  return (
    JSON.stringify(catalog.services[service]) !==
    JSON.stringify(draft.services[service])
  );
}

export function nextModelName(
  models: CatalogModel[],
  language: UiSettings["language"],
): string {
  const prefix = language === "zh" ? "\u6a21\u578b" : "Model ";
  const used = new Set(models.map((model) => model.name.trim()));
  let index = models.length + 1;
  while (used.has(`${prefix}${index}`)) {
    index += 1;
  }
  return `${prefix}${index}`;
}
