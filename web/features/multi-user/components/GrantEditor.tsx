"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertCircle, CheckCircle2, Loader2, Save } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  fetchAdminResources,
  fetchUserGrant,
  fetchUserUsage,
  saveUserGrant,
} from "../api";
import type {
  GrantPayload,
  McpToolOption,
  MultiUserResources,
  UserQuota,
  UserUsageResponse,
} from "../types";

type SaveState = "idle" | "saving" | "saved" | "error";

const quotaFields: Array<{
  key: keyof UserQuota;
  step?: string;
}> = [
  { key: "daily_token_limit" },
  { key: "monthly_token_limit" },
  { key: "daily_call_limit" },
  { key: "monthly_call_limit" },
  { key: "daily_cost_limit_usd", step: "0.01" },
  { key: "monthly_cost_limit_usd", step: "0.01" },
];

type Tr = (cn: string, en: string) => string;

function quotaLabel(key: keyof UserQuota, tr: Tr): string {
  switch (key) {
    case "daily_token_limit":
      return tr("每日 token", "Daily tokens");
    case "monthly_token_limit":
      return tr("每月 token", "Monthly tokens");
    case "daily_call_limit":
      return tr("每日调用", "Daily calls");
    case "monthly_call_limit":
      return tr("每月调用", "Monthly calls");
    case "daily_cost_limit_usd":
      return tr("每日美元", "Daily USD");
    case "monthly_cost_limit_usd":
      return tr("每月美元", "Monthly USD");
  }
}

function emptyQuota(): UserQuota {
  return {
    daily_token_limit: 0,
    monthly_token_limit: 0,
    daily_call_limit: 0,
    monthly_call_limit: 0,
    daily_cost_limit_usd: 0,
    monthly_cost_limit_usd: 0,
  };
}

function emptyGrant(userId: string): GrantPayload {
  return {
    version: 2,
    user_id: userId,
    models: { llm: [] },
    knowledge_bases: [],
    skills: [],
    partners: [],
    enabled_tools: null,
    mcp_tools: null,
    exec_enabled: null,
    quota: emptyQuota(),
  };
}

function hasModel(grant: GrantPayload, profileId: string, modelId?: string) {
  return grant.models.llm.some((item) => {
    if (item.profile_id !== profileId) return false;
    if (!modelId) return true;
    return Array.isArray(item.model_ids) && item.model_ids.includes(modelId);
  });
}

function grantFingerprint(grant: GrantPayload): string {
  return JSON.stringify(grant);
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--muted-foreground)]">
      {children}
    </h3>
  );
}

function CheckRow({
  label,
  description,
  checked,
  disabled,
  onToggle,
}: {
  label: string;
  description?: string;
  checked: boolean;
  disabled: boolean;
  onToggle: () => void;
}) {
  return (
    <label className="flex cursor-pointer items-start gap-2 rounded-lg border border-[var(--border)]/60 p-2 text-[var(--foreground)]">
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={onToggle}
        className="mt-0.5"
      />
      <span className="min-w-0">
        <span className="block truncate">{label}</span>
        {description ? (
          <span className="block truncate text-[11px] text-[var(--muted-foreground)]">
            {description}
          </span>
        ) : null}
      </span>
    </label>
  );
}

/**
 * Default-vs-custom switch for a whitelist field. ``null`` selects the
 * "default" mode; what that resolves to server-side depends on the field —
 * built-in tools default to *all*, MCP tools default to *none* (deny until
 * explicitly granted) — so the default-mode label is caller-supplied.
 */
function ModeSwitch({
  isCustom,
  disabled,
  onDefault,
  onCustom,
  defaultLabel = "Default · all",
  customLabel = "Custom",
}: {
  isCustom: boolean;
  disabled: boolean;
  onDefault: () => void;
  onCustom: () => void;
  defaultLabel?: string;
  customLabel?: string;
}) {
  const base =
    "rounded-md px-2 py-0.5 text-[11px] font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-45";
  return (
    <div className="mb-2 inline-flex gap-1 rounded-lg bg-[var(--muted)]/50 p-0.5">
      <button
        type="button"
        disabled={disabled}
        onClick={onDefault}
        className={`${base} ${
          !isCustom
            ? "bg-[var(--card)] text-[var(--foreground)] shadow-sm"
            : "text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
        }`}
      >
        {defaultLabel}
      </button>
      <button
        type="button"
        disabled={disabled}
        onClick={onCustom}
        className={`${base} ${
          isCustom
            ? "bg-[var(--card)] text-[var(--foreground)] shadow-sm"
            : "text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
        }`}
      >
        {customLabel}
      </button>
    </div>
  );
}

export function GrantEditor({ userId }: { userId: string }) {
  const { i18n } = useTranslation();
  const zh = i18n.language?.toLowerCase().startsWith("zh");
  const tr = useCallback((cn: string, en: string) => (zh ? cn : en), [zh]);
  const [resources, setResources] = useState<MultiUserResources | null>(null);
  const [grant, setGrant] = useState<GrantPayload>(() => emptyGrant(userId));
  const [usage, setUsage] = useState<UserUsageResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [savedFingerprint, setSavedFingerprint] = useState("");
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [message, setMessage] = useState("");

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      fetchAdminResources(),
      fetchUserGrant(userId),
      fetchUserUsage(userId),
    ])
      .then(([nextResources, nextGrant, nextUsage]) => {
        if (cancelled) return;
        setResources(nextResources);
        setGrant(nextGrant);
        setUsage(nextUsage);
        setSavedFingerprint(grantFingerprint(nextGrant));
      })
      .catch((error) => {
        setSaveState("error");
        setMessage(
          error instanceof Error ? error.message : tr("加载授权失败", "Failed to load grants"),
        );
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [tr, userId]);

  const currentFingerprint = useMemo(() => grantFingerprint(grant), [grant]);
  const dirty =
    Boolean(savedFingerprint) && currentFingerprint !== savedFingerprint;

  const kbIds = useMemo(
    () =>
      new Set(
        grant.knowledge_bases.map((item) =>
          String(item.resource_id || item.id || ""),
        ),
      ),
    [grant.knowledge_bases],
  );
  const skillIds = useMemo(
    () =>
      new Set(
        grant.skills.map((item) => String(item.skill_id || item.id || "")),
      ),
    [grant.skills],
  );
  const partnerIds = useMemo(
    () =>
      new Set(
        grant.partners.map((item) => String(item.partner_id || item.id || "")),
      ),
    [grant.partners],
  );

  const selectedModelCount = useMemo(
    () =>
      grant.models.llm.reduce((total, item) => {
        if (Array.isArray(item.model_ids)) return total + item.model_ids.length;
        return total + 1;
      }, 0),
    [grant.models.llm],
  );

  const saving = saveState === "saving";
  const controlsDisabled = loading || saving;

  function toggleModel(profileId: string, modelId: string) {
    setGrant((current) => {
      const next = structuredClone(current) as GrantPayload;
      const items = next.models.llm;
      const existing = items.find((item) => item.profile_id === profileId);
      if (!existing) {
        items.push({
          profile_id: profileId,
          model_ids: [modelId],
          source: "admin",
        });
        return next;
      }
      const modelIds = new Set(
        Array.isArray(existing.model_ids) ? existing.model_ids : [],
      );
      if (modelIds.has(modelId)) modelIds.delete(modelId);
      else modelIds.add(modelId);
      existing.model_ids = Array.from(modelIds);
      next.models.llm = items.filter((item) =>
        Array.isArray(item.model_ids) ? item.model_ids.length > 0 : true,
      );
      return next;
    });
  }

  function toggleKb(resourceId: string, name: string) {
    setGrant((current) => {
      const next = structuredClone(current) as GrantPayload;
      const exists = kbIds.has(resourceId);
      next.knowledge_bases = exists
        ? next.knowledge_bases.filter(
            (item) => String(item.resource_id || item.id || "") !== resourceId,
          )
        : [
            ...next.knowledge_bases,
            { resource_id: resourceId, name, access: "read", source: "admin" },
          ];
      return next;
    });
  }

  function toggleSkill(name: string) {
    setGrant((current) => {
      const next = structuredClone(current) as GrantPayload;
      const exists = skillIds.has(name);
      next.skills = exists
        ? next.skills.filter(
            (item) => String(item.skill_id || item.id || "") !== name,
          )
        : [...next.skills, { skill_id: name, access: "use", source: "admin" }];
      return next;
    });
  }

  function togglePartner(partnerId: string, name: string) {
    setGrant((current) => {
      const next = structuredClone(current) as GrantPayload;
      const exists = partnerIds.has(partnerId);
      next.partners = exists
        ? next.partners.filter(
            (item) => String(item.partner_id || item.id || "") !== partnerId,
          )
        : [...next.partners, { partner_id: partnerId, name, source: "admin" }];
      return next;
    });
  }

  function setToolList(
    key: "enabled_tools" | "mcp_tools",
    value: string[] | null,
  ) {
    setGrant((current) => ({ ...current, [key]: value }));
  }

  function toggleToolName(key: "enabled_tools" | "mcp_tools", name: string) {
    setGrant((current) => {
      const list = current[key];
      if (list === null) return current;
      const next = list.includes(name)
        ? list.filter((item) => item !== name)
        : [...list, name];
      return { ...current, [key]: next };
    });
  }

  function setQuota(key: keyof UserQuota, raw: string) {
    const number = Number(raw);
    setGrant((current) => ({
      ...current,
      quota: {
        ...(current.quota || emptyQuota()),
        [key]: Number.isFinite(number) && number > 0 ? number : 0,
      },
    }));
  }

  async function save() {
    setSaveState("saving");
    setMessage("");
    try {
      const saved = await saveUserGrant(userId, grant);
      setGrant(saved);
      setSavedFingerprint(grantFingerprint(saved));
      setSaveState("saved");
      setMessage(tr("刚刚已保存", "Saved just now"));
    } catch (error) {
      setSaveState("error");
      setMessage(error instanceof Error ? error.message : tr("保存失败", "Failed to save"));
    }
  }

  const status = loading
    ? tr("正在加载授权…", "Loading assignments...")
    : saveState === "saving"
      ? tr("正在保存更改…", "Saving changes...")
      : saveState === "error"
        ? message || tr("保存失败", "Failed to save")
        : saveState === "saved" && !dirty
          ? message || tr("刚刚已保存", "Saved just now")
          : dirty
            ? tr("有未保存更改", "Unsaved changes")
            : tr("就绪", "Ready");

  const statusTone =
    saveState === "error"
      ? "text-red-600 dark:text-red-400"
      : saveState === "saved" && !dirty
        ? "text-emerald-700 dark:text-emerald-300"
        : "text-[var(--muted-foreground)]";

  const toolsSummary =
    grant.enabled_tools === null
      ? tr("全部工具", "all tools")
      : tr(`${grant.enabled_tools.length} 个工具`, `${grant.enabled_tools.length} tools`);
  // MCP tools deny-by-default for non-admin users: ``null`` grants none until
  // the admin switches to Custom and picks specific tool names.
  const mcpSummary =
    grant.mcp_tools === null ? tr("无 MCP", "no MCP") : `${grant.mcp_tools.length} MCP`;
  const todayUsage = usage?.usage.today;

  const mcpByServer = useMemo(() => {
    const groups = new Map<string, McpToolOption[]>();
    for (const tool of resources?.mcp_tools || []) {
      const key = tool.server || "other";
      groups.set(key, [...(groups.get(key) ?? []), tool]);
    }
    return groups;
  }, [resources?.mcp_tools]);

  if (loading && !resources) {
    return (
      <div className="border-t border-[var(--border)] bg-[var(--background)]/40 p-4">
        <div className="flex h-[420px] items-center justify-center rounded-2xl border border-[var(--border)] bg-[var(--card)] text-sm text-[var(--muted-foreground)]">
          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          {tr("正在加载授权…", "Loading assignments...")}
        </div>
      </div>
    );
  }

  return (
    <div className="border-t border-[var(--border)] bg-[var(--background)]/40 p-4">
      <div className="flex h-[620px] max-h-[calc(100vh-170px)] min-h-[420px] flex-col overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--card)] shadow-sm">
        <div className="shrink-0 border-b border-[var(--border)] px-5 py-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="text-sm font-semibold text-[var(--foreground)]">
                {tr("分配访问权限", "Assign access")}
              </h2>
              <p className="mt-0.5 text-xs text-[var(--muted-foreground)]">
                {tr(
                  "管理员资源仍由服务端关联，用户只获得被允许的访问权限。",
                  "Admin resources stay linked server-side; users only receive allowed access.",
                )}
              </p>
            </div>
            <div className="flex flex-wrap gap-1.5 text-[11px] text-[var(--muted-foreground)]">
              <span className="rounded-full bg-[var(--muted)]/60 px-2 py-1">
                {tr(`${selectedModelCount} 个模型`, `${selectedModelCount} models`)}
              </span>
              <span className="rounded-full bg-[var(--muted)]/60 px-2 py-1">
                {kbIds.size} KBs
              </span>
              <span className="rounded-full bg-[var(--muted)]/60 px-2 py-1">
                {tr(`${skillIds.size} 个技能`, `${skillIds.size} skills`)}
              </span>
              <span className="rounded-full bg-[var(--muted)]/60 px-2 py-1">
                {tr(`${partnerIds.size} 个伙伴`, `${partnerIds.size} partners`)}
              </span>
              <span className="rounded-full bg-[var(--muted)]/60 px-2 py-1">
                {toolsSummary}
              </span>
              <span className="rounded-full bg-[var(--muted)]/60 px-2 py-1">
                {mcpSummary}
              </span>
              {todayUsage ? (
                <span className="rounded-full bg-[var(--muted)]/60 px-2 py-1">
                  {tr(
                    `今天 ${todayUsage.total_calls} 次调用 · ${todayUsage.total_tokens} token · $${todayUsage.total_cost_usd.toFixed(4)}`,
                    `Today ${todayUsage.total_calls} calls · ${todayUsage.total_tokens} tokens · $${todayUsage.total_cost_usd.toFixed(4)}`,
                  )}
                </span>
              ) : null}
            </div>
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5 [scrollbar-gutter:stable]">
          <div className="grid gap-5 md:grid-cols-3">
            <section className="min-w-0">
              <SectionTitle>{tr("模型", "Models")}</SectionTitle>
              <div className="space-y-1.5 text-xs">
                {(resources?.models.llm || []).map((profile) => (
                  <div
                    key={profile.profile_id}
                    className="rounded-lg border border-[var(--border)]/60 p-2"
                  >
                    <div className="mb-1 truncate text-[var(--muted-foreground)]">
                      {profile.name}
                    </div>
                    {(profile.models || []).map((model) => (
                      <label
                        key={model.model_id}
                        className="flex cursor-pointer items-center gap-2 py-1 text-[var(--foreground)]"
                      >
                        <input
                          type="checkbox"
                          checked={hasModel(
                            grant,
                            profile.profile_id,
                            model.model_id,
                          )}
                          disabled={controlsDisabled}
                          onChange={() =>
                            toggleModel(profile.profile_id, model.model_id)
                          }
                        />
                        <span className="truncate">{model.name}</span>
                      </label>
                    ))}
                  </div>
                ))}
              </div>
            </section>
            <section className="min-w-0">
              <SectionTitle>{tr("知识库", "Knowledge")}</SectionTitle>
              <div className="space-y-1.5 text-xs">
                {(resources?.knowledge_bases || []).map((kb) => (
                  <CheckRow
                    key={kb.resource_id}
                    label={kb.name}
                    checked={kbIds.has(kb.resource_id)}
                    disabled={controlsDisabled}
                    onToggle={() => toggleKb(kb.resource_id, kb.name)}
                  />
                ))}
              </div>
            </section>
            <section className="min-w-0">
              <SectionTitle>{tr("技能", "Skills")}</SectionTitle>
              <div className="space-y-1.5 text-xs">
                {(resources?.skills || []).map((skill) => (
                  <CheckRow
                    key={skill.name}
                    label={skill.name}
                    checked={skillIds.has(skill.name)}
                    disabled={controlsDisabled}
                    onToggle={() => toggleSkill(skill.name)}
                  />
                ))}
              </div>
            </section>
            <section className="min-w-0">
              <SectionTitle>{tr("伙伴", "Partners")}</SectionTitle>
              <div className="space-y-1.5 text-xs">
                {(resources?.partners || []).length === 0 ? (
                  <p className="px-1 text-[11px] leading-relaxed text-[var(--muted-foreground)]">
                    {tr(
                      "暂无伙伴。先在伙伴页面创建，再分配给用户。",
                      "No partners yet. Create one under Partners to assign it.",
                    )}
                  </p>
                ) : (
                  (resources?.partners || []).map((partner) => (
                    <CheckRow
                      key={partner.partner_id}
                      label={partner.name || partner.partner_id}
                      description={partner.description}
                      checked={partnerIds.has(partner.partner_id)}
                      disabled={controlsDisabled}
                      onToggle={() =>
                        togglePartner(
                          partner.partner_id,
                          partner.name || partner.partner_id,
                        )
                      }
                    />
                  ))
                )}
              </div>
            </section>

            <section className="min-w-0">
              <SectionTitle>{tr("系统工具", "System tools")}</SectionTitle>
              <ModeSwitch
                isCustom={grant.enabled_tools !== null}
                disabled={controlsDisabled}
                defaultLabel={tr("默认 · 全部", "Default · all")}
                customLabel={tr("自定义", "Custom")}
                onDefault={() => setToolList("enabled_tools", null)}
                onCustom={() =>
                  setToolList(
                    "enabled_tools",
                    (resources?.tools || []).map((tool) => tool.name),
                  )
                }
              />
              {grant.enabled_tools !== null && (
                <div className="space-y-1.5 text-xs">
                  {(resources?.tools || []).map((tool) => (
                    <CheckRow
                      key={tool.name}
                      label={tool.name}
                      description={tool.description}
                      checked={grant.enabled_tools!.includes(tool.name)}
                      disabled={controlsDisabled}
                      onToggle={() =>
                        toggleToolName("enabled_tools", tool.name)
                      }
                    />
                  ))}
                </div>
              )}
            </section>
            <section className="min-w-0">
              <SectionTitle>{tr("MCP 工具", "MCP tools")}</SectionTitle>
              <ModeSwitch
                isCustom={grant.mcp_tools !== null}
                disabled={controlsDisabled}
                defaultLabel={tr("默认 · 无", "Default · none")}
                customLabel={tr("自定义", "Custom")}
                onDefault={() => setToolList("mcp_tools", null)}
                onCustom={() =>
                  setToolList(
                    "mcp_tools",
                    (resources?.mcp_tools || []).map((tool) => tool.name),
                  )
                }
              />
              {grant.mcp_tools === null ? (
                <p className="px-1 text-[11px] leading-relaxed text-[var(--muted-foreground)]">
                  {tr(
                    "MCP 工具会代理宿主机能力，所以默认不授权。切换到自定义后再选择具体工具。",
                    "MCP tools proxy host-side capabilities, so they stay denied by default. Switch to Custom to grant specific tools.",
                  )}
                </p>
              ) : null}
              {grant.mcp_tools !== null &&
                (resources?.mcp_tools?.length ? (
                  <div className="space-y-2 text-xs">
                    {[...mcpByServer.entries()].map(([server, tools]) => (
                      <div key={server}>
                        <p className="mb-1 px-1 font-mono text-[11px] text-[var(--muted-foreground)]">
                          {server}
                        </p>
                        <div className="space-y-1.5">
                          {tools.map((tool) => (
                            <CheckRow
                              key={tool.name}
                              label={tool.name}
                              description={tool.description}
                              checked={grant.mcp_tools!.includes(tool.name)}
                              disabled={controlsDisabled}
                              onToggle={() =>
                                toggleToolName("mcp_tools", tool.name)
                              }
                            />
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-[var(--muted-foreground)]">
                    {tr("尚未配置 MCP 服务器。", "No MCP servers configured.")}
                  </p>
                ))}
            </section>
            <section className="min-w-0">
              <SectionTitle>{tr("代码执行", "Code execution")}</SectionTitle>
              <div className="space-y-1.5 text-xs">
                <CheckRow
                  label={tr("允许代码执行", "Allow code execution")}
                  description={tr(
                    "遵循部署沙箱策略。取消勾选会禁用该用户的 exec 能力。",
                    "Follows the deployment sandbox policy. Uncheck to disable exec for this user.",
                  )}
                  checked={grant.exec_enabled !== false}
                  disabled={controlsDisabled}
                  onToggle={() =>
                    setGrant((current) => ({
                      ...current,
                      exec_enabled:
                        current.exec_enabled === false ? null : false,
                    }))
                  }
                />
              </div>
            </section>
            <section className="min-w-0">
              <SectionTitle>{tr("LLM 配额", "LLM quota")}</SectionTitle>
              <div className="grid grid-cols-2 gap-2 text-xs">
                {quotaFields.map((field) => (
                  <label key={field.key} className="min-w-0">
                    <span className="mb-1 block truncate text-[11px] text-[var(--muted-foreground)]">
                      {quotaLabel(field.key, tr)}
                    </span>
                    <input
                      type="number"
                      min="0"
                      step={field.step || "1"}
                      value={grant.quota?.[field.key] ?? 0}
                      disabled={controlsDisabled}
                      onChange={(event) => setQuota(field.key, event.target.value)}
                      className="w-full rounded-md border border-[var(--border)] bg-[var(--background)] px-2 py-1 text-[var(--foreground)] outline-none focus:border-[var(--foreground)] disabled:opacity-45"
                    />
                  </label>
                ))}
              </div>
              <p className="mt-2 px-1 text-[11px] leading-relaxed text-[var(--muted-foreground)]">
                {tr(
                  "0 表示不限制。配额用尽后会阻止下一轮对话。",
                  "0 means unlimited. A spent quota blocks the next turn.",
                )}
              </p>
            </section>
          </div>
        </div>

        <div className="flex shrink-0 items-center justify-between gap-3 border-t border-[var(--border)] bg-[var(--card)] px-5 py-3">
          <div
            aria-live="polite"
            className={`flex min-w-0 items-center gap-1.5 text-xs ${statusTone}`}
          >
            {saveState === "error" ? (
              <AlertCircle className="h-3.5 w-3.5 shrink-0" />
            ) : saveState === "saved" && !dirty ? (
              <CheckCircle2 className="h-3.5 w-3.5 shrink-0" />
            ) : null}
            <span className="truncate">{status}</span>
          </div>
          <button
            onClick={save}
            disabled={controlsDisabled || !dirty}
            className="inline-flex shrink-0 items-center gap-1.5 rounded-lg bg-[var(--foreground)] px-3 py-1.5 text-xs font-medium text-[var(--background)] transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-45"
          >
            {saving ? (
              <Loader2 className="h-3 w-3 animate-spin" />
            ) : saveState === "saved" && !dirty ? (
              <CheckCircle2 className="h-3 w-3" />
            ) : (
              <Save className="h-3 w-3" />
            )}
            {saving
              ? tr("保存中…", "Saving...")
              : saveState === "saved" && !dirty
                ? tr("已保存", "Saved")
                : tr("保存授权", "Save assignments")}
          </button>
        </div>
      </div>
    </div>
  );
}
