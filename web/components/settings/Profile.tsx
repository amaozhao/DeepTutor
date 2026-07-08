"use client";

import { useState, type Dispatch, type SetStateAction } from "react";
import { ChevronDown, Eye, EyeOff } from "lucide-react";
import { useTranslation } from "react-i18next";

import ProviderIcon from "@/components/common/ProviderIcon";
import {
  type CatalogProfile,
  type ServiceName,
  useSettings,
} from "./SettingsContext";
import { nextProfileName } from "./profile-naming";
import { searchProviderFields } from "./search-providers";
import {
  inputClass,
  selectClass,
  selectOptionClass,
  stringifyExtraHeaders,
} from "./shared";

export function ProfileFields({
  service,
  profile,
  showApiKey,
  setShowApiKey,
  showSearchProviderWarning,
  isSupportedSearchProvider,
  isDeprecatedSearchProvider,
  isPerplexityMissingKey,
}: {
  service: ServiceName;
  profile: CatalogProfile;
  showApiKey: boolean;
  setShowApiKey: Dispatch<SetStateAction<boolean>>;
  showSearchProviderWarning: boolean;
  isSupportedSearchProvider: boolean;
  isDeprecatedSearchProvider: boolean;
  isPerplexityMissingKey: boolean;
}) {
  const { t } = useTranslation();
  const { providers, updateProfileField, updateModelField } = useSettings();
  const [extraOpen, setExtraOpen] = useState(false);

  const providerValue =
    service === "search" ? profile.provider || "" : profile.binding || "";

  const fields =
    service === "search"
      ? searchProviderFields(profile.provider)
      : { apiKey: true, baseUrl: true, baseUrlRequired: false };
  const searxngMissingBaseUrl =
    fields.baseUrlRequired && !String(profile.base_url || "").trim();

  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <div className="sm:col-span-2">
        <div className="mb-1.5 text-[12px] text-[var(--muted-foreground)]">
          {t("Provider")}
        </div>
        <div className="relative">
          {providerValue && (
            <ProviderIcon
              provider={providerValue}
              size={15}
              className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2"
            />
          )}
          <select
            className={`${selectClass} ${providerValue ? "pl-9" : ""}`}
            value={providerValue}
            onChange={(e) => {
              const val = e.target.value;
              const field = service === "search" ? "provider" : "binding";
              const options = providers[service] || [];
              const previousLabel =
                options.find((p) => p.value === providerValue)?.label ?? "";
              const match = options.find((p) => p.value === val);
              updateProfileField(service, field, val);
              const renamed = nextProfileName(
                profile.name,
                previousLabel,
                match?.label ?? "",
              );
              if (renamed !== profile.name) {
                updateProfileField(service, "name", renamed);
              }
              if (match?.base_url) {
                updateProfileField(service, "base_url", match.base_url);
              }
              if (service === "embedding" && match?.default_dim) {
                updateModelField(service, "dimension", match.default_dim);
              }
              if (
                (service === "tts" ||
                  service === "stt" ||
                  service === "imagegen" ||
                  service === "videogen") &&
                match?.default_model
              ) {
                updateModelField(service, "model", match.default_model);
              }
              if (service === "tts" && match?.default_voice) {
                updateModelField(service, "voice", match.default_voice);
              }
            }}
          >
            <option className={selectOptionClass} value="">
              {t("Select provider...")}
            </option>
            {(providers[service] || []).map((p) => (
              <option className={selectOptionClass} key={p.value} value={p.value}>
                {p.label}
              </option>
            ))}
          </select>
          <ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[var(--muted-foreground)]" />
        </div>
        {showSearchProviderWarning && (
          <p
            className={`mt-1.5 text-[11px] ${
              isSupportedSearchProvider
                ? "text-emerald-600 dark:text-emerald-400"
                : isDeprecatedSearchProvider
                  ? "text-amber-600 dark:text-amber-400"
                  : "text-red-500"
            }`}
          >
            {isSupportedSearchProvider
              ? isPerplexityMissingKey
                ? t(
                    "Perplexity requires API key. It will fail hard without credentials.",
                  )
                : t("Supported provider.")
              : isDeprecatedSearchProvider
                ? t(
                    "Deprecated provider. Switch to brave/tavily/jina/searxng/duckduckgo/perplexity.",
                  )
                : t(
                    "Unsupported provider. Use brave/tavily/jina/searxng/duckduckgo/perplexity.",
                  )}
          </p>
        )}
      </div>
      {fields.baseUrl && (
        <div className="sm:col-span-2">
          <div className="mb-1.5 text-[12px] text-[var(--muted-foreground)]">
            {service === "embedding" ? t("Endpoint URL") : t("Base URL")}
          </div>
          <input
            className={inputClass}
            value={profile.base_url}
            onChange={(e) =>
              updateProfileField(service, "base_url", e.target.value)
            }
            placeholder={
              service === "embedding"
                ? "https://api.openai.com/v1/embeddings"
                : service === "search"
                  ? "http://localhost:8888"
                  : "https://api.openai.com/v1"
            }
          />
          {service === "embedding" && (
            <p className="mt-1.5 text-[11px] text-[var(--muted-foreground)]">
              {t(
                "Embedding requests are sent to this URL exactly; DeepTutor does not append /embeddings or /api/embed at request time.",
              )}
            </p>
          )}
          {searxngMissingBaseUrl && (
            <p className="mt-1.5 text-[11px] text-amber-600 dark:text-amber-400">
              {t("Required — without it, search falls back to DuckDuckGo.")}
            </p>
          )}
        </div>
      )}
      {fields.apiKey && (
        <div className="sm:col-span-2">
          <div className="mb-1.5 text-[12px] text-[var(--muted-foreground)]">
            {t("API Key")}
          </div>
          <div className="relative">
            <input
              type={showApiKey ? "text" : "password"}
              autoComplete="new-password"
              spellCheck={false}
              className={`${inputClass} pr-10 font-mono`}
              value={profile.api_key}
              onChange={(e) =>
                updateProfileField(service, "api_key", e.target.value)
              }
              placeholder="sk-..."
            />
            <button
              type="button"
              onClick={() => setShowApiKey((prev) => !prev)}
              className="absolute right-1 top-1/2 -translate-y-1/2 rounded-md p-1.5 text-[var(--muted-foreground)] hover:bg-[var(--muted)] hover:text-[var(--foreground)]"
              aria-label={showApiKey ? t("Hide API key") : t("Show API key")}
              title={showApiKey ? t("Hide API key") : t("Show API key")}
            >
              {showApiKey ? (
                <EyeOff className="h-4 w-4" />
              ) : (
                <Eye className="h-4 w-4" />
              )}
            </button>
          </div>
        </div>
      )}
      <div className="sm:col-span-2 rounded-xl border border-[var(--border)]/60 bg-[var(--muted)]/20">
        <button
          type="button"
          onClick={() => setExtraOpen((value) => !value)}
          className="flex w-full items-center justify-between gap-3 px-3.5 py-3 text-left"
          aria-expanded={extraOpen}
        >
          <span>
            <span className="block text-[12px] font-medium text-[var(--foreground)]">
              {t("Extra (optional)")}
            </span>
            <span className="mt-0.5 block text-[11px] text-[var(--muted-foreground)]">
              {service === "search"
                ? t("API version and proxy")
                : t("API version and extra request headers")}
            </span>
          </span>
          <ChevronDown
            className={`h-4 w-4 text-[var(--muted-foreground)] transition-transform ${
              extraOpen ? "rotate-180" : ""
            }`}
          />
        </button>
        {extraOpen && (
          <div className="grid gap-4 border-t border-[var(--border)]/60 px-3.5 py-4 sm:grid-cols-2">
            <div>
              <div className="mb-1.5 text-[12px] text-[var(--muted-foreground)]">
                {t("API Version")}
              </div>
              <input
                className={inputClass}
                value={profile.api_version}
                onChange={(e) =>
                  updateProfileField(service, "api_version", e.target.value)
                }
                placeholder={t("Optional")}
              />
            </div>
            {service === "search" ? (
              <div>
                <div className="mb-1.5 text-[12px] text-[var(--muted-foreground)]">
                  {t("Proxy")}
                </div>
                <input
                  className={inputClass}
                  value={profile.proxy || ""}
                  onChange={(e) =>
                    updateProfileField(service, "proxy", e.target.value)
                  }
                  placeholder={t("http://127.0.0.1:7890 (optional)")}
                />
              </div>
            ) : (
              <div className="sm:col-span-2">
                <div className="mb-1.5 text-[12px] text-[var(--muted-foreground)]">
                  {t("Extra Headers (JSON)")}
                </div>
                <textarea
                  className={`${inputClass} min-h-[84px] resize-y`}
                  value={stringifyExtraHeaders(profile.extra_headers)}
                  onChange={(e) =>
                    updateProfileField(service, "extra_headers", e.target.value)
                  }
                  placeholder='{"APP-Code":"your-app-code"}'
                />
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
