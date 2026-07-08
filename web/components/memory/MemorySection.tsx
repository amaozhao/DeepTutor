"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Archive,
  Brain,
  Loader2,
  Pencil,
  RefreshCw,
  Save,
  X,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { apiFetch, apiUrl } from "@/lib/api";
import SpaceSectionHeader from "@/components/space/SpaceSectionHeader";
import { L1View } from "@/components/memory/MemoryL1View";
import {
  formatTimestamp,
  labelFor,
  linkifyEntityRefs,
  parseEntityAnchor,
  type DocOverview,
  type Layer,
  type OverviewResponse,
  type StreamStage,
  type Surface,
  type Tab,
} from "@/components/memory/model";

const MarkdownRenderer = dynamic(
  () => import("@/components/common/MarkdownRenderer"),
  { ssr: false },
);

// ── Main component ──────────────────────────────────────────────────

interface MemorySectionProps {
  forcedTab?: Tab; // when provided, hides the TabStrip and locks the active tab
  hideHeader?: boolean; // when true, skips the SpaceSectionHeader (parent page renders its own)
}

export default function MemorySection({
  forcedTab,
  hideHeader = false,
}: MemorySectionProps = {}) {
  const { t, i18n } = useTranslation();
  const [tab, setTab] = useState<Tab>(forcedTab ?? "L2");
  const [overview, setOverview] = useState<OverviewResponse | null>(null);
  const [selected, setSelected] = useState<{
    layer: Layer;
    key: string;
  } | null>(null);
  const [content, setContent] = useState("");
  const [editing, setEditing] = useState(false);
  const [editorValue, setEditorValue] = useState("");
  const [stream, setStream] = useState<StreamStage[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState("");
  const [l1Surface, setL1Surface] = useState<Surface>("notebook");
  const [l1FocusRef, setL1FocusRef] = useState<string | null>(null);
  const [dismissedBackup, setDismissedBackup] = useState<string | null>(null);

  useEffect(() => {
    if (typeof window === "undefined") return;
    setDismissedBackup(
      window.localStorage.getItem("dt:memory:banner-dismissed") || null,
    );
  }, []);

  const latestBackup = overview?.backups?.[overview.backups.length - 1] ?? null;
  const showArchivedBanner = !!latestBackup && latestBackup !== dismissedBackup;

  const dismissArchivedBanner = useCallback(() => {
    if (!latestBackup) return;
    if (typeof window !== "undefined") {
      window.localStorage.setItem("dt:memory:banner-dismissed", latestBackup);
    }
    setDismissedBackup(latestBackup);
  }, [latestBackup]);

  const loadOverview = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiFetch(apiUrl("/api/v1/memory/overview"));
      const data = (await res.json()) as OverviewResponse;
      setOverview(data);
    } catch (e) {
      setToast(e instanceof Error ? e.message : "Failed to load overview");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadOverview();
  }, [loadOverview]);

  useEffect(() => {
    if (!toast) return;
    const id = setTimeout(() => setToast(""), 3500);
    return () => clearTimeout(id);
  }, [toast]);

  const loadDoc = useCallback(async (layer: Layer, key: string) => {
    setSelected({ layer, key });
    setEditing(false);
    setStream([]);
    try {
      const res = await apiFetch(apiUrl(`/api/v1/memory/doc/${layer}/${key}`));
      const data = await res.json();
      const md = String(data?.content || "");
      setContent(md);
      setEditorValue(md);
    } catch (e) {
      setToast(e instanceof Error ? e.message : "Failed to load document");
    }
  }, []);

  const saveDoc = useCallback(async () => {
    if (!selected) return;
    setBusy(true);
    try {
      await apiFetch(
        apiUrl(`/api/v1/memory/doc/${selected.layer}/${selected.key}`),
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ content: editorValue }),
        },
      );
      setContent(editorValue);
      setEditing(false);
      setToast(t("Saved"));
      void loadOverview();
    } catch (e) {
      setToast(e instanceof Error ? e.message : "Failed to save");
    } finally {
      setBusy(false);
    }
  }, [editorValue, loadOverview, selected, t]);

  const runUpdate = useCallback(async () => {
    if (!selected) return;
    if (selected.layer === "L3" && selected.key === "preferences") {
      setToast(
        t("Preferences is written by the chat assistant, not consolidated."),
      );
      return;
    }
    setBusy(true);
    setStream([]);
    try {
      const res = await apiFetch(
        apiUrl(`/api/v1/memory/doc/${selected.layer}/${selected.key}/update`),
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ language: i18n.language || "en" }),
        },
      );
      const reader = res.body?.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (reader) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let nl = buffer.indexOf("\n\n");
        while (nl !== -1) {
          const chunk = buffer.slice(0, nl);
          buffer = buffer.slice(nl + 2);
          const line = chunk
            .split("\n")
            .find((l) => l.startsWith("data:"))
            ?.replace(/^data:\s?/, "");
          if (line) {
            try {
              const evt = JSON.parse(line) as StreamStage;
              setStream((prev) => [...prev, evt]);
            } catch {
              // ignore malformed chunk
            }
          }
          nl = buffer.indexOf("\n\n");
        }
      }
      void loadDoc(selected.layer, selected.key);
      void loadOverview();
    } catch (e) {
      setToast(e instanceof Error ? e.message : "Update failed");
    } finally {
      setBusy(false);
    }
  }, [i18n.language, loadDoc, loadOverview, selected, t]);

  // Clicking a `<surface>:<entity_id>` ref inside an L2/L3 doc opens
  // the L1 tab focused on that entity.
  const handleEntityLinkClick = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      const link = (e.target as HTMLElement | null)?.closest("a");
      if (!link) return;
      const href = link.getAttribute("href") || "";
      if (!href.startsWith("#entity-")) return;
      const parsed = parseEntityAnchor(href.slice(1));
      if (!parsed) return;
      setTab("L1");
      setL1Surface(parsed.surface);
      setL1FocusRef(parsed.ref);
    },
    [],
  );

  const l2Rows = useMemo(
    () => (overview?.docs || []).filter((d) => d.layer === "L2"),
    [overview],
  );
  const l3Rows = useMemo(
    () => (overview?.docs || []).filter((d) => d.layer === "L3"),
    [overview],
  );

  return (
    <div className="space-y-6">
      {!hideHeader && (
        <SpaceSectionHeader
          icon={Brain}
          title={t("Memory")}
          description={t(
            "L1 mirrors your workspace, L2 summarises per-surface content, L3 is cross-surface knowledge.",
          )}
          meta={
            toast ? (
              <span className="rounded-full border border-[var(--primary)]/30 bg-[var(--primary)]/10 px-2 py-0.5 text-[10.5px] font-medium text-[var(--primary)]">
                {toast}
              </span>
            ) : null
          }
        />
      )}

      {!forcedTab && showArchivedBanner && latestBackup && (
        <div className="relative flex items-start gap-2 rounded-xl border border-[var(--border)] bg-[var(--muted)] px-4 py-3 pr-10 text-[13px]">
          <Archive className="mt-0.5 h-4 w-4 shrink-0 text-[var(--muted-foreground)]" />
          <div>
            <p className="font-medium text-[var(--foreground)]">
              {t("Your v1 memory was archived")}
            </p>
            <p className="mt-0.5 text-[var(--muted-foreground)]">
              {t(
                "Stored at memory/backup/{{name}}. v2 starts fresh — interact with DeepTutor and click Update on each doc to build memory.",
                { name: latestBackup },
              )}
            </p>
          </div>
          <button
            type="button"
            onClick={dismissArchivedBanner}
            aria-label={t("Dismiss")}
            className="absolute right-2 top-2 rounded-md p-1.5 text-[var(--muted-foreground)] transition hover:bg-[var(--background)] hover:text-[var(--foreground)]"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      )}

      {!forcedTab && (
        <TabStrip
          tab={tab}
          onChange={setTab}
          l2Count={l2Rows.length}
          l3Count={l3Rows.length}
          t={t}
        />
      )}

      {tab === "L1" && (
        <L1View
          surface={l1Surface}
          onSurfaceChange={(s) => {
            setL1Surface(s);
            setL1FocusRef(null);
          }}
          focusRef={l1FocusRef}
          onClearFocus={() => setL1FocusRef(null)}
          onToast={setToast}
          t={t}
        />
      )}

      {tab !== "L1" && (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[280px,1fr]">
          <div className="space-y-4">
            <DocList
              title={t(
                tab === "L2" ? "L2 · Per-surface" : "L3 · Cross-surface",
              )}
              rows={tab === "L2" ? l2Rows : l3Rows}
              selected={selected}
              onSelect={loadDoc}
            />
          </div>

          <div className="space-y-4">
            {loading ? (
              <div className="flex min-h-[300px] items-center justify-center">
                <Loader2 className="h-5 w-5 animate-spin text-[var(--muted-foreground)]" />
              </div>
            ) : !selected || selected.layer !== tab ? (
              <div className="flex min-h-[300px] flex-col items-center justify-center rounded-xl border border-dashed border-[var(--border)] text-center">
                <Brain className="mb-3 h-5 w-5 text-[var(--muted-foreground)]" />
                <p className="text-[14px] text-[var(--foreground)]">
                  {t("Pick a document to view or update")}
                </p>
              </div>
            ) : (
              <DocPane
                selected={selected}
                content={content}
                editing={editing}
                editorValue={editorValue}
                busy={busy}
                onEditValue={setEditorValue}
                onEditToggle={() => {
                  setEditing((v) => !v);
                  setEditorValue(content);
                }}
                onSave={saveDoc}
                onUpdate={runUpdate}
                onEntityLinkClick={handleEntityLinkClick}
                t={t}
              />
            )}

            {stream.length > 0 && (
              <StreamPanel
                stages={stream}
                onDismiss={() => setStream([])}
                t={t}
              />
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ── TabStrip ────────────────────────────────────────────────────────

interface TabStripProps {
  tab: Tab;
  onChange: (tab: Tab) => void;
  l2Count: number;
  l3Count: number;
  t: (key: string, opts?: Record<string, unknown>) => string;
}

function TabStrip({ tab, onChange, l2Count, l3Count, t }: TabStripProps) {
  const tabs: Array<{ key: Tab; label: string; count?: number; hint: string }> =
    [
      {
        key: "L1",
        label: t("L1 · Workspace"),
        hint: t(
          "Live snapshot of your workspace — one entry per real artifact.",
        ),
      },
      {
        key: "L2",
        label: t("L2 · Per-surface"),
        count: l2Count,
        hint: t("Per-surface summaries consolidated from L1 content."),
      },
      {
        key: "L3",
        label: t("L3 · Cross-surface"),
        count: l3Count,
        hint: t("Cross-surface knowledge consolidated from L2."),
      },
    ];
  return (
    <div className="border-b border-[var(--border)]">
      <div className="flex gap-1">
        {tabs.map(({ key, label, count, hint }) => {
          const active = tab === key;
          return (
            <button
              key={key}
              onClick={() => onChange(key)}
              title={hint}
              className={`relative px-4 py-2 text-[13px] font-medium transition-colors ${
                active
                  ? "text-[var(--foreground)]"
                  : "text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
              }`}
            >
              {label}
              {typeof count === "number" && (
                <span className="ml-2 rounded-full bg-[var(--muted)] px-1.5 py-0.5 text-[10px] font-normal text-[var(--muted-foreground)]">
                  {count}
                </span>
              )}
              {active && (
                <span
                  aria-hidden
                  className="absolute -bottom-px left-0 right-0 h-[2px] bg-[var(--foreground)]"
                />
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}

// ── DocList / DocPane / StreamPanel (mostly unchanged) ──────────────

interface DocListProps {
  title: string;
  rows: DocOverview[];
  selected: { layer: Layer; key: string } | null;
  onSelect: (layer: Layer, key: string) => void;
}

function DocList({ title, rows, selected, onSelect }: DocListProps) {
  const { t } = useTranslation();
  return (
    <div className="rounded-xl border border-[var(--border)]">
      <div className="border-b border-[var(--border)] px-4 py-2 text-[11px] font-semibold uppercase tracking-wide text-[var(--muted-foreground)]">
        {title}
      </div>
      <ul>
        {rows.map((row) => {
          const isActive =
            selected?.layer === row.layer && selected.key === row.key;
          return (
            <li
              key={`${row.layer}-${row.key}`}
              className={`flex items-center justify-between border-b border-[var(--border)]/50 px-4 py-2 text-[13px] last:border-0 ${
                isActive ? "bg-[var(--muted)]" : "hover:bg-[var(--muted)]/50"
              }`}
            >
              <button
                onClick={() => onSelect(row.layer, row.key)}
                className="flex-1 text-left"
              >
                <span className="font-medium text-[var(--foreground)]">
                  {labelFor(row)}
                </span>
                <span className="ml-2 text-[11px] text-[var(--muted-foreground)]">
                  {row.entry_count} ·{" "}
                  {formatTimestamp(row.updated_at, t("not built"))}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

interface DocPaneProps {
  selected: { layer: Layer; key: string };
  content: string;
  editing: boolean;
  editorValue: string;
  busy: boolean;
  onEditValue: (v: string) => void;
  onEditToggle: () => void;
  onSave: () => void;
  onUpdate: () => void;
  onEntityLinkClick: (e: React.MouseEvent<HTMLDivElement>) => void;
  t: (key: string, opts?: Record<string, unknown>) => string;
}

function DocPane({
  selected,
  content,
  editing,
  editorValue,
  busy,
  onEditValue,
  onEditToggle,
  onSave,
  onUpdate,
  onEntityLinkClick,
  t,
}: DocPaneProps) {
  const isPrefs = selected.layer === "L3" && selected.key === "preferences";
  const renderedContent = useMemo(() => linkifyEntityRefs(content), [content]);
  return (
    <div className="rounded-xl border border-[var(--border)]">
      <div className="flex items-center justify-between border-b border-[var(--border)] px-4 py-2">
        <span className="text-[14px] font-medium text-[var(--foreground)]">
          {selected.layer} ·{" "}
          {labelFor({
            layer: selected.layer,
            key: selected.key,
          } as DocOverview)}
        </span>
        <div className="flex items-center gap-2">
          <button
            onClick={onEditToggle}
            className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--border)] px-2.5 py-1 text-[12px] text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
          >
            <Pencil className="h-3 w-3" />
            {editing ? t("Cancel") : t("Edit")}
          </button>
          {editing && (
            <button
              onClick={onSave}
              disabled={busy}
              className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--primary)]/40 bg-[var(--primary)]/10 px-2.5 py-1 text-[12px] font-medium text-[var(--primary)] disabled:opacity-50"
            >
              {busy ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : (
                <Save className="h-3 w-3" />
              )}
              {t("Save")}
            </button>
          )}
          {!isPrefs && (
            <button
              onClick={onUpdate}
              disabled={busy || editing}
              className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--primary)]/40 bg-[var(--primary)]/10 px-2.5 py-1 text-[12px] font-medium text-[var(--primary)] disabled:opacity-50"
            >
              {busy ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : (
                <RefreshCw className="h-3 w-3" />
              )}
              {t("Update")}
            </button>
          )}
        </div>
      </div>
      <div className="px-5 py-4">
        {editing ? (
          <textarea
            value={editorValue}
            onChange={(e) => onEditValue(e.target.value)}
            spellCheck={false}
            className="min-h-[420px] w-full resize-none rounded-lg border border-[var(--border)] bg-transparent p-3 font-mono text-[13px] leading-6 outline-none focus:border-[var(--ring)]"
          />
        ) : content.trim() ? (
          <div onClick={onEntityLinkClick}>
            <MarkdownRenderer
              content={renderedContent}
              variant="prose"
              className="text-[14px]"
            />
          </div>
        ) : (
          <p className="text-[13px] text-[var(--muted-foreground)]">
            {isPrefs
              ? t(
                  "Preferences are written when you explicitly tell the chat assistant your preferences (style, language, format).",
                )
              : t(
                  "Empty. Click Update to consolidate from the current snapshot.",
                )}
          </p>
        )}
      </div>
    </div>
  );
}

interface StreamPanelProps {
  stages: StreamStage[];
  onDismiss: () => void;
  t: (key: string, opts?: Record<string, unknown>) => string;
}

function StreamPanel({ stages, onDismiss, t }: StreamPanelProps) {
  return (
    <div className="rounded-xl border border-[var(--border)]">
      <div className="flex items-center justify-between border-b border-[var(--border)] px-4 py-2">
        <span className="text-[12px] font-semibold uppercase tracking-wide text-[var(--muted-foreground)]">
          {t("Update progress")}
        </span>
        <button
          onClick={onDismiss}
          className="rounded p-1 text-[var(--muted-foreground)] hover:bg-[var(--muted)]"
        >
          <X className="h-3 w-3" />
        </button>
      </div>
      <ol className="space-y-2 px-4 py-3 text-[12px]">
        {stages.map((s, i) => (
          <li
            key={i}
            className="rounded bg-[var(--muted)]/50 px-3 py-2 font-mono"
          >
            <span className="font-semibold text-[var(--foreground)]">
              {s.stage}
              {typeof s.turn === "number" ? ` · t${s.turn}` : ""}
              {s.name ? ` · ${s.name}` : ""}
            </span>
            {typeof s.count === "number" && (
              <span className="ml-2 text-[var(--muted-foreground)]">
                count={s.count}
              </span>
            )}
            {s.delta && (
              <div className="mt-1 whitespace-pre-wrap text-[var(--muted-foreground)]">
                {s.delta}
              </div>
            )}
            {s.brief && (
              <div className="mt-1 text-[var(--muted-foreground)]">
                {s.brief}
              </div>
            )}
            {s.args && Object.keys(s.args).length > 0 && (
              <div className="mt-1 text-[var(--muted-foreground)]">
                args: {JSON.stringify(s.args)}
              </div>
            )}
            {s.ops && (
              <div className="mt-1 text-[var(--muted-foreground)]">
                ops: {s.ops.length}
              </div>
            )}
            {typeof s.ops_emitted === "number" && (
              <div className="mt-1 text-[var(--muted-foreground)]">
                ops_emitted={s.ops_emitted} · turns={s.turns_used ?? "?"}
                {s.tools_used
                  ? ` · ${Object.entries(s.tools_used)
                      .map(([k, v]) => `${k}=${v}`)
                      .join(", ")}`
                  : ""}
              </div>
            )}
            {s.report && (
              <div className="mt-1 text-[var(--muted-foreground)]">
                accepted={String(s.report.accepted)}
                {s.report.reason ? ` · ${s.report.reason}` : ""}
              </div>
            )}
            {s.message && (
              <div className="mt-1 text-[var(--muted-foreground)]">
                {s.message}
              </div>
            )}
            {s.summary && (
              <div className="mt-1 text-[var(--muted-foreground)]">
                {s.summary}
              </div>
            )}
          </li>
        ))}
      </ol>
    </div>
  );
}
