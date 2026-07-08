"use client";

import { useState } from "react";
import {
  CheckCircle2,
  ChevronDown,
  Info,
  Loader2,
  Pencil,
  Plus,
  Terminal,
  Trash2,
} from "lucide-react";
import { useTranslation } from "react-i18next";

import ProviderIcon from "@/components/common/ProviderIcon";
import {
  type CatalogModel,
  type CatalogProfile,
  type LlmContextWindowDetection,
  type ServiceName,
  getActiveModel,
  getActiveProfile,
  useSettings,
} from "./SettingsContext";
import { DimensionField } from "./DimensionField";
import { ProfileFields } from "./Profile";
import {
  defaultModelLabel,
  formatCompactTokens,
  formatDimensionBadge,
  formatIsoLocal,
  formatVoiceBadge,
} from "./format";
import {
  activeProfileDetail,
  deprecatedSearchProviders,
  formatContextWindowSource,
  inputClass,
  selectClass,
  selectOptionClass,
  supportedSearchProviders,
} from "./shared";

const SERVICE_LABEL: Record<ServiceName, string> = {
  llm: "LLM",
  embedding: "Embedding",
  search: "Search",
  tts: "Text-to-Speech",
  stt: "Speech-to-Text",
  imagegen: "Image Generation",
  videogen: "Video Generation",
};

export function ServiceConfigEditor({ service }: { service: ServiceName }) {
  const { t } = useTranslation();
  const {
    draft,
    catalogEditable,
    settingsError,
    providers,
    language,
    embeddingCapabilities,
    embeddingDefaultDim,
    logs,
    testRunning,
    mutateCatalog,
    addProfile,
    removeActiveProfile,
    addModel,
    removeActiveModel,
    updateProfileField,
    updateModelField,
    updateModelBoolField,
    updateContextWindowField,
    llmContextDetection,
    applyDetectedContextWindow,
    runDetailedTest,
  } = useSettings();

  const activeProfile = getActiveProfile(draft, service);
  const activeModel = getActiveModel(draft, service);

  const [showApiKey, setShowApiKey] = useState(false);
  const [diagnosticsOpen, setDiagnosticsOpen] = useState(false);
  const [editingModelId, setEditingModelId] = useState<string | null>(null);
  const [editingModelName, setEditingModelName] = useState("");
  const [editingProfileId, setEditingProfileId] = useState<string | null>(null);
  const [editingProfileName, setEditingProfileName] = useState("");

  // Reset API-key visibility whenever we land on a different profile or
  // switch services — same effect the old code had, but using React's
  // documented "store previous prop in state" pattern so it happens during
  // render rather than in a useEffect (which the linter forbids).
  const profileKey = `${service}:${activeProfile?.id ?? "none"}`;
  const [lastProfileKey, setLastProfileKey] = useState(profileKey);
  if (lastProfileKey !== profileKey) {
    setLastProfileKey(profileKey);
    if (showApiKey) setShowApiKey(false);
  }

  const searchProviderRaw =
    service === "search"
      ? (activeProfile?.provider || "").trim().toLowerCase()
      : "";
  const showSearchProviderWarning =
    service === "search" && Boolean(searchProviderRaw);
  const isDeprecatedSearchProvider =
    deprecatedSearchProviders.has(searchProviderRaw);
  const isSupportedSearchProvider = supportedSearchProviders.includes(
    searchProviderRaw as (typeof supportedSearchProviders)[number],
  );
  const isPerplexityMissingKey =
    service === "search" &&
    searchProviderRaw === "perplexity" &&
    !String(activeProfile?.api_key || "").trim();
  const activeLlmDetection =
    service === "llm" &&
    llmContextDetection?.profileId === draft.services.llm.active_profile_id &&
    llmContextDetection?.modelId === draft.services.llm.active_model_id
      ? llmContextDetection
      : null;

  const startModelRename = (model: CatalogModel) => {
    setEditingModelId(model.id);
    setEditingModelName(model.name || model.model || "");
  };

  const commitModelRename = (modelId: string) => {
    const fallbackIndex =
      activeProfile?.models.findIndex((model) => model.id === modelId) ?? -1;
    const fallbackName = defaultModelLabel(language, fallbackIndex + 1);
    const nextName = editingModelName.trim() || fallbackName;
    mutateCatalog((next) => {
      const profile = getActiveProfile(next, service);
      const model = profile?.models.find((item) => item.id === modelId);
      if (model) model.name = nextName;
    });
    setEditingModelId(null);
    setEditingModelName("");
  };

  const cancelModelRename = () => {
    setEditingModelId(null);
    setEditingModelName("");
  };

  const startProfileRename = (profile: CatalogProfile) => {
    setEditingProfileId(profile.id);
    setEditingProfileName(profile.name || "");
  };

  const commitProfileRename = (profileId: string) => {
    const nextName = editingProfileName.trim();
    if (nextName) {
      mutateCatalog((next) => {
        const profile = next.services[service].profiles.find(
          (item) => item.id === profileId,
        );
        if (profile) profile.name = nextName;
      });
    }
    setEditingProfileId(null);
    setEditingProfileName("");
  };

  const cancelProfileRename = () => {
    setEditingProfileId(null);
    setEditingProfileName("");
  };

  if (!catalogEditable) {
    // catalogEditable=false covers two unrelated cases: settings fetch failed,
    // or multi-user grant denied. Split them so a Docker user without the
    // 8001 port mapped does not see an "assigned by administrator" hint.
    if (settingsError) {
      return (
        <div className="rounded-xl border border-dashed border-[var(--border)] px-5 py-10 text-center text-[13px] text-[var(--muted-foreground)]">
          {t(
            "Backend unreachable — model endpoints will appear once the connection is restored. See the banner above for details.",
          )}
        </div>
      );
    }
    return (
      <div className="rounded-xl border border-dashed border-[var(--border)] px-5 py-10 text-center text-[13px] text-[var(--muted-foreground)]">
        {t(
          "Model endpoints are assigned by your administrator. You can still personalize theme and language here.",
        )}
      </div>
    );
  }

  return (
    <div data-tour={`tour-${service}`} className="space-y-5">
      {activeProfile ? (
        <div className="grid grid-cols-[200px_minmax(0,1fr)] items-start gap-5">
          {/* ── Profile list (sticky so it stays put while the editor scrolls) ── */}
          <aside className="sticky top-4 self-start rounded-xl border border-[var(--border)]/60 bg-[var(--card)]/40 p-2">
            <div className="px-2 pb-2 pt-1 text-[11px] font-medium uppercase tracking-wide text-[var(--muted-foreground)]/70">
              {t("Profiles")}
            </div>
            <div className="space-y-0.5">
              {draft.services[service].profiles.map((profile) => {
                const isActive =
                  profile.id === draft.services[service].active_profile_id;
                const profileDetail = activeProfileDetail(profile, service, t);
                const isEditing = editingProfileId === profile.id;
                return (
                  <div
                    key={profile.id}
                    role="button"
                    tabIndex={isEditing ? -1 : 0}
                    onClick={() => {
                      if (isEditing) return;
                      mutateCatalog((next) => {
                        next.services[service].active_profile_id = profile.id;
                        if (service !== "search") {
                          next.services[service].active_model_id =
                            profile.models[0]?.id ?? null;
                        }
                      });
                    }}
                    onDoubleClick={() => startProfileRename(profile)}
                    onKeyDown={(e) => {
                      if (isEditing) return;
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        mutateCatalog((next) => {
                          next.services[service].active_profile_id = profile.id;
                          if (service !== "search") {
                            next.services[service].active_model_id =
                              profile.models[0]?.id ?? null;
                          }
                        });
                      }
                    }}
                    title={isEditing ? undefined : t("Double-click to rename")}
                    className={`group relative cursor-pointer rounded-lg px-3 py-2 text-left transition-colors ${
                      isActive
                        ? "bg-[var(--muted)]/70 text-[var(--foreground)]"
                        : "text-[var(--muted-foreground)] hover:bg-[var(--muted)]/30"
                    }`}
                  >
                    {isActive && (
                      <span className="absolute inset-y-2 left-0 w-0.5 rounded-r-full bg-[var(--foreground)]/80" />
                    )}
                    {isEditing ? (
                      <input
                        autoFocus
                        className="block w-full rounded border border-[var(--border)] bg-[var(--background)] px-1.5 py-0.5 text-[13px] font-medium text-[var(--foreground)] outline-none focus:border-[var(--ring)]"
                        value={editingProfileName}
                        onChange={(e) => setEditingProfileName(e.target.value)}
                        onBlur={() => commitProfileRename(profile.id)}
                        onClick={(e) => e.stopPropagation()}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") {
                            e.currentTarget.blur();
                          }
                          if (e.key === "Escape") {
                            e.preventDefault();
                            cancelProfileRename();
                          }
                        }}
                        aria-label={t("Rename profile")}
                      />
                    ) : (
                      <div className="flex items-center gap-1.5">
                        <ProviderIcon
                          provider={
                            service === "search"
                              ? profile.provider
                              : profile.binding
                          }
                          size={13}
                        />
                        <div
                          className={`min-w-0 flex-1 truncate text-[13px] leading-tight ${
                            isActive ? "font-semibold" : "font-medium"
                          }`}
                        >
                          {profile.name}
                        </div>
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            startProfileRename(profile);
                          }}
                          className="-mr-1 shrink-0 rounded-md p-1 text-[var(--muted-foreground)]/60 transition-colors hover:bg-[var(--muted)] hover:text-[var(--foreground)]"
                          aria-label={t("Rename profile")}
                          title={t("Rename profile")}
                        >
                          <Pencil className="h-3 w-3" />
                        </button>
                      </div>
                    )}
                    <div className="mt-0.5 truncate text-[11px] leading-tight text-[var(--muted-foreground)]/70">
                      {profileDetail}
                    </div>
                  </div>
                );
              })}
            </div>
            <div className="mt-2 border-t border-[var(--border)]/40 pt-2">
              <button
                onClick={() => removeActiveProfile(service)}
                disabled={!activeProfile}
                className="flex w-full items-center gap-1.5 rounded-lg px-3 py-1.5 text-left text-[11px] text-[var(--muted-foreground)]/60 transition-colors hover:bg-red-500/5 hover:text-red-500 disabled:opacity-30"
                title={
                  activeProfile
                    ? t("Permanently remove the currently selected profile.")
                    : undefined
                }
              >
                <Trash2 className="h-3 w-3 shrink-0" />
                <span className="truncate">
                  {activeProfile
                    ? t("Delete “{{name}}”", { name: activeProfile.name })
                    : t("Delete profile")}
                </span>
              </button>
            </div>
          </aside>

          {/* ── Editor ── */}
          <div className="min-w-0 space-y-5">
            <div className="rounded-xl border border-[var(--border)] p-5">
              <div className="mb-4 flex items-center justify-between gap-2">
                <div className="text-[13px] font-medium text-[var(--foreground)]">
                  {t("Provider connection")}
                </div>
                <button
                  type="button"
                  onClick={() => addProfile(service)}
                  className="inline-flex items-center gap-1 rounded-lg border border-[var(--border)]/50 px-2.5 py-1 text-[12px] text-[var(--muted-foreground)] transition-colors hover:border-[var(--border)] hover:text-[var(--foreground)]"
                >
                  <Plus className="h-3 w-3" />
                  {t("Profile")}
                </button>
              </div>
              <ProfileFields
                service={service}
                profile={activeProfile}
                showApiKey={showApiKey}
                setShowApiKey={setShowApiKey}
                showSearchProviderWarning={showSearchProviderWarning}
                isSupportedSearchProvider={isSupportedSearchProvider}
                isDeprecatedSearchProvider={isDeprecatedSearchProvider}
                isPerplexityMissingKey={isPerplexityMissingKey}
              />
            </div>

            {service !== "search" && (
              <div className="rounded-xl border border-[var(--border)] p-5">
                <div className="mb-4 flex items-center justify-between gap-2">
                  <div className="text-[13px] font-medium text-[var(--foreground)]">
                    {t("Models")}
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => addModel(service)}
                      className="inline-flex items-center gap-1 rounded-lg border border-[var(--border)]/50 px-2.5 py-1 text-[12px] text-[var(--muted-foreground)] transition-colors hover:border-[var(--border)] hover:text-[var(--foreground)]"
                    >
                      <Plus className="h-3 w-3" />
                      {t("Model")}
                    </button>
                    <button
                      onClick={() => removeActiveModel(service)}
                      disabled={!activeModel}
                      className="inline-flex items-center gap-1 text-[11px] text-[var(--muted-foreground)]/40 transition-colors hover:text-red-500 disabled:opacity-30"
                    >
                      <Trash2 className="h-3 w-3" />
                      {t("Delete")}
                    </button>
                  </div>
                </div>
                {activeProfile.models.length > 0 && (
                  <div className="mb-4 flex flex-wrap items-center gap-1.5">
                    {activeProfile.models.map((model, index) => {
                      const isActive =
                        model.id === draft.services[service].active_model_id;
                      const label =
                        (model.name || "").trim() ||
                        defaultModelLabel(language, index + 1);
                      const metric =
                        service === "llm"
                          ? formatCompactTokens(model.context_window)
                          : service === "embedding"
                            ? formatDimensionBadge(model.dimension)
                            : service === "tts"
                              ? formatVoiceBadge(model.voice)
                              : "";
                      return (
                        <div key={model.id} className="min-w-0">
                          {editingModelId === model.id ? (
                            <input
                              autoFocus
                              className="h-8 w-60 rounded-lg border border-[var(--border)] bg-[var(--background)] px-2.5 text-[12.5px] text-[var(--foreground)] outline-none focus:border-[var(--ring)]"
                              value={editingModelName}
                              onChange={(e) =>
                                setEditingModelName(e.target.value)
                              }
                              onBlur={() => commitModelRename(model.id)}
                              onKeyDown={(e) => {
                                if (e.key === "Enter") {
                                  e.currentTarget.blur();
                                }
                                if (e.key === "Escape") {
                                  e.preventDefault();
                                  cancelModelRename();
                                }
                              }}
                              aria-label={t("Rename model")}
                            />
                          ) : (
                            <button
                              type="button"
                              onClick={() =>
                                mutateCatalog((next) => {
                                  next.services[service].active_model_id =
                                    model.id;
                                })
                              }
                              onDoubleClick={() => startModelRename(model)}
                              title={t("Double-click to rename")}
                              className={`inline-flex h-8 items-center gap-1.5 rounded-lg px-2.5 text-[12.5px] transition-colors ${
                                isActive
                                  ? "bg-[var(--muted)] text-[var(--foreground)]"
                                  : "text-[var(--muted-foreground)] hover:bg-[var(--muted)]/40"
                              }`}
                            >
                              {isActive && (
                                <CheckCircle2 className="h-3 w-3 shrink-0 text-[var(--foreground)]/70" />
                              )}
                              <span
                                className={`max-w-[280px] truncate leading-none ${
                                  isActive ? "font-medium" : ""
                                }`}
                              >
                                {label}
                              </span>
                              {metric && (
                                <span className="shrink-0 text-[10.5px] tabular-nums leading-none text-[var(--muted-foreground)]/80">
                                  {metric}
                                </span>
                              )}
                            </button>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
                {activeModel && (
                  <div className="grid gap-4 sm:grid-cols-2">
                    <div>
                      <div className="mb-1.5 text-[12px] text-[var(--muted-foreground)]">
                        {t("Model ID")}
                      </div>
                      <input
                        className={inputClass}
                        value={activeModel.model}
                        onChange={(e) =>
                          updateModelField(service, "model", e.target.value)
                        }
                        placeholder="gpt-4o"
                      />
                    </div>
                    {service === "llm" && (
                      <>
                        <div>
                          <div className="mb-1.5 text-[12px] text-[var(--muted-foreground)]">
                            {t("Context Window")}
                          </div>
                          <input
                            className={inputClass}
                            inputMode="numeric"
                            value={activeModel.context_window || ""}
                            onChange={(e) =>
                              updateContextWindowField(e.target.value)
                            }
                            placeholder="65536"
                          />
                          <ContextWindowMeta model={activeModel} />
                        </div>
                        <ContextWindowDetectionBanner
                          model={activeModel}
                          detection={activeLlmDetection}
                          onApply={applyDetectedContextWindow}
                        />
                      </>
                    )}
                    {service === "embedding" && (
                      <div>
                        <div className="mb-1.5 flex items-center justify-between gap-2">
                          <span className="text-[12px] text-[var(--muted-foreground)]">
                            {t("Dimension")}
                          </span>
                          <label className="inline-flex cursor-pointer items-center gap-1.5 text-[11px] text-[var(--muted-foreground)] select-none">
                            <input
                              type="checkbox"
                              className="h-3 w-3 cursor-pointer accent-[var(--foreground)]"
                              checked={activeModel.send_dimensions !== false}
                              onChange={(e) =>
                                updateModelBoolField(
                                  service,
                                  "send_dimensions",
                                  e.target.checked,
                                )
                              }
                            />
                            <span>{t("Send dimensions")}</span>
                            <span
                              tabIndex={0}
                              className="group/info relative inline-flex cursor-help focus:outline-none"
                            >
                              <Info className="h-3 w-3 opacity-50 transition-opacity group-hover/info:opacity-100 group-focus/info:opacity-100" />
                              <span
                                role="tooltip"
                                className="pointer-events-none absolute top-full left-1/2 z-20 mt-1.5 w-64 -translate-x-1/2 rounded-lg border border-[var(--border)] bg-[var(--card)] p-2.5 text-[11px] leading-relaxed text-[var(--foreground)] opacity-0 shadow-lg transition-opacity duration-75 group-hover/info:opacity-100 group-focus/info:opacity-100"
                              >
                                {t(
                                  "Some embedding models (e.g. Qwen text-embedding-v4) reject the `dimensions` request param. Turn this off if your provider returns HTTP 400.",
                                )}
                              </span>
                            </span>
                          </label>
                        </div>
                        <DimensionField
                          activeModel={activeModel}
                          activeBinding={activeProfile?.binding}
                          capabilities={embeddingCapabilities}
                          embeddingDefaultDim={embeddingDefaultDim}
                          inputClass={inputClass}
                          onChangeDimension={(value) =>
                            updateModelField(service, "dimension", value)
                          }
                        />
                      </div>
                    )}
                    {service === "tts" && (
                      <>
                        <div>
                          <div className="mb-1.5 text-[12px] text-[var(--muted-foreground)]">
                            {t("Voice")}
                          </div>
                          <input
                            className={inputClass}
                            value={activeModel.voice || ""}
                            onChange={(e) =>
                              updateModelField(service, "voice", e.target.value)
                            }
                            placeholder="alloy"
                          />
                          <p className="mt-1.5 text-[11px] text-[var(--muted-foreground)]">
                            {t(
                              "Provider-specific voice name, e.g. alloy (OpenAI) or model:voice (SiliconFlow).",
                            )}
                          </p>
                        </div>
                        <div>
                          <div className="mb-1.5 text-[12px] text-[var(--muted-foreground)]">
                            {t("Output format")}
                          </div>
                          <div className="relative">
                            <select
                              className={selectClass}
                              value={activeModel.response_format || "mp3"}
                              onChange={(e) =>
                                updateModelField(
                                  service,
                                  "response_format",
                                  e.target.value,
                                )
                              }
                            >
                              {["mp3", "wav", "opus", "aac", "flac", "pcm"].map(
                                (fmt) => (
                                  <option
                                    className={selectOptionClass}
                                    key={fmt}
                                    value={fmt}
                                  >
                                    {fmt}
                                  </option>
                                ),
                              )}
                            </select>
                            <ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[var(--muted-foreground)]" />
                          </div>
                        </div>
                      </>
                    )}
                    {service === "imagegen" && (
                      <>
                        <div>
                          <div className="mb-1.5 text-[12px] text-[var(--muted-foreground)]">
                            {t("Image size")}
                          </div>
                          <input
                            className={inputClass}
                            value={activeModel.size || ""}
                            onChange={(e) =>
                              updateModelField(service, "size", e.target.value)
                            }
                            placeholder="1024x1024"
                          />
                          <p className="mt-1.5 text-[11px] text-[var(--muted-foreground)]">
                            {t(
                              "Default pixel size sent with each request. Leave empty for the provider default.",
                            )}
                          </p>
                        </div>
                        <div>
                          <div className="mb-1.5 text-[12px] text-[var(--muted-foreground)]">
                            {t("Quality / Style")}
                          </div>
                          <div className="grid grid-cols-2 gap-2">
                            <input
                              className={inputClass}
                              value={activeModel.quality || ""}
                              onChange={(e) =>
                                updateModelField(
                                  service,
                                  "quality",
                                  e.target.value,
                                )
                              }
                              placeholder={t("quality (e.g. hd)")}
                            />
                            <input
                              className={inputClass}
                              value={activeModel.style || ""}
                              onChange={(e) =>
                                updateModelField(
                                  service,
                                  "style",
                                  e.target.value,
                                )
                              }
                              placeholder={t("style (e.g. vivid)")}
                            />
                          </div>
                        </div>
                      </>
                    )}
                    {service === "videogen" && (
                      <>
                        <div>
                          <div className="mb-1.5 text-[12px] text-[var(--muted-foreground)]">
                            {t("Aspect ratio")}
                          </div>
                          <input
                            className={inputClass}
                            value={activeModel.aspect_ratio || ""}
                            onChange={(e) =>
                              updateModelField(
                                service,
                                "aspect_ratio",
                                e.target.value,
                              )
                            }
                            placeholder="16:9"
                          />
                          <p className="mt-1.5 text-[11px] text-[var(--muted-foreground)]">
                            {t(
                              "Defaults sent with each request. Leave empty for the provider default.",
                            )}
                          </p>
                        </div>
                        <div>
                          <div className="mb-1.5 text-[12px] text-[var(--muted-foreground)]">
                            {t("Duration / Resolution")}
                          </div>
                          <div className="grid grid-cols-2 gap-2">
                            <input
                              className={inputClass}
                              inputMode="numeric"
                              value={activeModel.duration || ""}
                              onChange={(e) =>
                                updateModelField(
                                  service,
                                  "duration",
                                  e.target.value,
                                )
                              }
                              placeholder={t("seconds")}
                            />
                            <input
                              className={inputClass}
                              value={activeModel.resolution || ""}
                              onChange={(e) =>
                                updateModelField(
                                  service,
                                  "resolution",
                                  e.target.value,
                                )
                              }
                              placeholder="720p"
                            />
                          </div>
                        </div>
                      </>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* ── Diagnostics — per-service, inline ── */}
            <div className="rounded-xl border border-[var(--border)]">
              <div className="flex items-center justify-between px-5 py-3.5">
                <button
                  type="button"
                  onClick={() => setDiagnosticsOpen((v) => !v)}
                  className="flex min-w-0 flex-1 items-center gap-2 text-left"
                  aria-expanded={diagnosticsOpen}
                >
                  <Terminal className="h-3.5 w-3.5 text-[var(--muted-foreground)]" />
                  <span className="text-[13px] font-medium text-[var(--foreground)]">
                    {t("Diagnostics")}
                  </span>
                  {testRunning === service && (
                    <Loader2 className="h-3 w-3 animate-spin text-[var(--primary)]" />
                  )}
                </button>
                <div className="ml-3 flex items-center gap-3">
                  <button
                    type="button"
                    onClick={() => {
                      if (!diagnosticsOpen) setDiagnosticsOpen(true);
                      runDetailedTest(service);
                    }}
                    disabled={testRunning !== null}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--border)]/50 px-2.5 py-1 text-[12px] text-[var(--muted-foreground)] transition-colors hover:border-[var(--border)] hover:text-[var(--foreground)] disabled:opacity-40"
                  >
                    {t("Run test")}
                  </button>
                  <button
                    type="button"
                    onClick={() => setDiagnosticsOpen((v) => !v)}
                    className="text-[var(--muted-foreground)] transition-colors hover:text-[var(--foreground)]"
                    aria-label={
                      diagnosticsOpen
                        ? t("Collapse diagnostics")
                        : t("Expand diagnostics")
                    }
                    aria-expanded={diagnosticsOpen}
                  >
                    <ChevronDown
                      className={`h-4 w-4 transition-transform ${diagnosticsOpen ? "rotate-180" : ""}`}
                    />
                  </button>
                </div>
              </div>
              {diagnosticsOpen && (
                <div className="border-t border-[var(--border)] px-5 py-4">
                  <p className="mb-3 text-[12px] leading-relaxed text-[var(--muted-foreground)]">
                    {t(
                      "Streams config snapshot, request target, response summary, and service-specific validation for the active {{service}} profile.",
                      { service: t(SERVICE_LABEL[service]) },
                    )}
                  </p>
                  <pre className="max-h-[360px] overflow-auto rounded-lg bg-[#0f0f0f] p-4 font-mono text-[12px] leading-6 text-[#777] whitespace-pre-wrap break-words dark:bg-[#0a0a0a]">
                    {testRunning === service || logs
                      ? logs
                      : t("Waiting for test run...")}
                  </pre>
                </div>
              )}
            </div>
          </div>
        </div>
      ) : (
        <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed border-[var(--border)] px-5 py-12 text-center text-[13px] text-[var(--muted-foreground)]">
          <div>{t("No profiles configured. Add a profile to start.")}</div>
          <button
            type="button"
            onClick={() => addProfile(service)}
            className="inline-flex items-center gap-1 rounded-lg border border-[var(--border)]/50 px-2.5 py-1 text-[12px] text-[var(--muted-foreground)] transition-colors hover:border-[var(--border)] hover:text-[var(--foreground)]"
          >
            <Plus className="h-3 w-3" />
            {t("Profile")}
          </button>
        </div>
      )}
    </div>
  );
}

function ContextWindowMeta({ model }: { model: CatalogModel }) {
  const { t } = useTranslation();
  if (!model.context_window) return null;
  const source = formatContextWindowSource(model.context_window_source, t);
  const updatedAt = formatIsoLocal(model.context_window_detected_at);
  return (
    <div className="mt-1.5 flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-[11px] text-[var(--muted-foreground)]">
      <span>{t("Source")}:</span>
      <span className="text-[var(--foreground)]/80">{source}</span>
      {updatedAt && (
        <>
          <span className="text-[var(--muted-foreground)]/40">·</span>
          <span title={model.context_window_detected_at}>{updatedAt}</span>
        </>
      )}
    </div>
  );
}

function ContextWindowDetectionBanner({
  model,
  detection,
  onApply,
}: {
  model: CatalogModel;
  detection: LlmContextWindowDetection | null;
  onApply: () => void;
}) {
  const { t } = useTranslation();
  if (!detection) return null;
  const currentRaw = Number.parseInt(
    String(model.context_window || "").replace(/[^\d]/g, ""),
    10,
  );
  const matches =
    Number.isFinite(currentRaw) && currentRaw === detection.contextWindow;
  const detectedFormatted = detection.contextWindow.toLocaleString("en-US");
  const detectedAt = formatIsoLocal(detection.detectedAt);
  const source = formatContextWindowSource(detection.source, t);

  if (matches) {
    return (
      <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 rounded-lg border border-emerald-500/30 bg-emerald-500/5 px-3 py-2 text-[12px] text-[var(--muted-foreground)] sm:col-span-2">
        <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
        <span className="text-[var(--foreground)]/80">
          {t("Detected value matches your current setting")}
        </span>
        <span className="text-[var(--muted-foreground)]/70">
          ({detectedFormatted} · {source})
        </span>
      </div>
    );
  }

  return (
    <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-2 rounded-lg border border-[var(--border)] bg-[var(--muted)]/30 px-3 py-2 sm:col-span-2">
      <div className="flex min-w-0 flex-1 flex-wrap items-baseline gap-x-2 gap-y-0.5 text-[12px]">
        <span className="text-[var(--muted-foreground)]">{t("Detected")}:</span>
        <span className="font-mono text-[13px] font-medium text-[var(--foreground)] tabular-nums">
          {detectedFormatted}
        </span>
        <span className="text-[var(--muted-foreground)]/80">· {source}</span>
        {detectedAt && (
          <span className="text-[var(--muted-foreground)]/60">
            · {detectedAt}
          </span>
        )}
      </div>
      <button
        type="button"
        onClick={onApply}
        className="shrink-0 rounded-md border border-[var(--border)] bg-[var(--background)] px-2.5 py-1 text-[11.5px] font-medium text-[var(--foreground)] transition-colors hover:border-[var(--foreground)]"
      >
        {t("Apply")}
      </button>
    </div>
  );
}
