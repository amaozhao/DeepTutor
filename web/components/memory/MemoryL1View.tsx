"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  BookOpen,
  Bot,
  ClipboardList,
  ExternalLink,
  GitCommit,
  Library,
  Loader2,
  MessageSquare,
  NotebookPen,
  PenLine,
  RefreshCw,
  type LucideIcon,
} from "lucide-react";

import { apiFetch, apiUrl } from "@/lib/api";
import {
  SURFACES,
  SURFACE_LABELS,
  asString,
  entityAnchorId,
  entityDeepLinkUrl,
  formatTimestamp,
  shorten,
  type ChangeEntryDTO,
  type ChangesResponse,
  type Entity,
  type KbQueriesResponse,
  type KbQueryDTO,
  type SnapshotResponse,
  type Surface,
} from "@/components/memory/model";

type L1Mode = "snapshot" | "changes" | "queries";

interface SurfaceMeta {
  icon: LucideIcon;
  label: string;
}

const SURFACE_META: Record<Surface, SurfaceMeta> = {
  chat: { icon: MessageSquare, label: SURFACE_LABELS.chat },
  notebook: { icon: NotebookPen, label: SURFACE_LABELS.notebook },
  quiz: { icon: ClipboardList, label: SURFACE_LABELS.quiz },
  kb: { icon: BookOpen, label: SURFACE_LABELS.kb },
  book: { icon: Library, label: SURFACE_LABELS.book },
  partner: { icon: Bot, label: SURFACE_LABELS.partner },
  cowriter: { icon: PenLine, label: SURFACE_LABELS.cowriter },
};

export interface L1ViewProps {
  surface: Surface;
  onSurfaceChange: (s: Surface) => void;
  focusRef: string | null;
  onClearFocus: () => void;
  onToast: (msg: string) => void;
  t: (key: string, opts?: Record<string, unknown>) => string;
  compact?: boolean;
}

export function L1View({
  surface,
  onSurfaceChange,
  focusRef,
  onClearFocus,
  onToast,
  t,
  compact = false,
}: L1ViewProps) {
  const [mode, setMode] = useState<L1Mode>("snapshot");
  const [snapshot, setSnapshot] = useState<SnapshotResponse | null>(null);
  const [changes, setChanges] = useState<ChangeEntryDTO[]>([]);
  const [kbQueries, setKbQueries] = useState<KbQueryDTO[]>([]);
  const [loadingSnapshot, setLoadingSnapshot] = useState(false);
  const [loadingChanges, setLoadingChanges] = useState(false);
  const [loadingQueries, setLoadingQueries] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (mode === "queries" && surface !== "kb") {
      setMode("snapshot");
    }
  }, [surface, mode]);

  const loadSnapshot = useCallback(async () => {
    setLoadingSnapshot(true);
    try {
      const res = await apiFetch(apiUrl(`/api/v1/memory/snapshot/${surface}`));
      const data = (await res.json()) as SnapshotResponse;
      setSnapshot(data);
    } catch (e) {
      onToast(e instanceof Error ? e.message : "Failed to load snapshot");
    } finally {
      setLoadingSnapshot(false);
    }
  }, [surface, onToast]);

  const loadChanges = useCallback(async () => {
    setLoadingChanges(true);
    try {
      const res = await apiFetch(
        apiUrl(`/api/v1/memory/snapshot/${surface}/changes`),
      );
      const data = (await res.json()) as ChangesResponse;
      setChanges(data.changes);
    } catch (e) {
      onToast(e instanceof Error ? e.message : "Failed to load changes");
    } finally {
      setLoadingChanges(false);
    }
  }, [surface, onToast]);

  const loadKbQueries = useCallback(async () => {
    if (surface !== "kb") return;
    setLoadingQueries(true);
    try {
      const res = await apiFetch(apiUrl("/api/v1/memory/trace/kb?limit=200"));
      const data = (await res.json()) as KbQueriesResponse;
      setKbQueries(data.events);
    } catch (e) {
      onToast(e instanceof Error ? e.message : "Failed to load queries");
    } finally {
      setLoadingQueries(false);
    }
  }, [surface, onToast]);

  useEffect(() => {
    setSnapshot(null);
    setChanges([]);
    setKbQueries([]);
    void loadSnapshot();
    void loadChanges();
    if (surface === "kb") void loadKbQueries();
  }, [surface, loadSnapshot, loadChanges, loadKbQueries]);

  useEffect(() => {
    const refetch = () => {
      if (typeof document !== "undefined" && document.hidden) return;
      void loadSnapshot();
    };
    window.addEventListener("focus", refetch);
    document.addEventListener("visibilitychange", refetch);
    return () => {
      window.removeEventListener("focus", refetch);
      document.removeEventListener("visibilitychange", refetch);
    };
  }, [loadSnapshot]);

  useEffect(() => {
    if (!focusRef || !containerRef.current) return;
    if (!snapshot) return;
    const el = containerRef.current.querySelector(
      `[data-entity-ref="${focusRef}"]`,
    ) as HTMLElement | null;
    if (el) {
      el.scrollIntoView({ block: "center", behavior: "smooth" });
    }
  }, [focusRef, snapshot]);

  const pendingByEntity = useMemo(() => {
    const m = new Map<string, ChangeEntryDTO["kind"]>();
    for (const c of snapshot?.pending_changes ?? []) {
      m.set(c.entity_id, c.kind);
    }
    return m;
  }, [snapshot?.pending_changes]);
  const pendingCount = snapshot?.pending_changes?.length ?? 0;

  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    try {
      const res = await apiFetch(
        apiUrl(`/api/v1/memory/snapshot/${surface}/refresh`),
        { method: "POST" },
      );
      const data = await res.json();
      const newChanges: ChangeEntryDTO[] = data?.changes || [];
      onToast(
        newChanges.length > 0
          ? t("Refreshed: {{n}} changes", { n: newChanges.length })
          : t("Refreshed: no changes"),
      );
      await loadSnapshot();
      await loadChanges();
    } catch (e) {
      onToast(e instanceof Error ? e.message : "Refresh failed");
    } finally {
      setRefreshing(false);
    }
  }, [surface, loadSnapshot, loadChanges, onToast, t]);

  return (
    <div className="space-y-3" ref={containerRef}>
      {!compact && (
        <div className="flex flex-wrap items-center gap-2">
          {SURFACES.map((s) => {
            const meta = SURFACE_META[s];
            return (
              <SurfacePill
                key={s}
                active={surface === s}
                onClick={() => onSurfaceChange(s)}
                icon={meta.icon}
                label={meta.label}
              />
            );
          })}
          <div className="ml-auto flex items-center gap-2">
            <PendingCount pendingCount={pendingCount} t={t} />
            <RefreshButton refreshing={refreshing} onRefresh={onRefresh} t={t} />
          </div>
        </div>
      )}

      <div className="flex items-center justify-between gap-2">
        <ModeStrip mode={mode} setMode={setMode} surface={surface} t={t} />
        {compact && (
          <div className="flex items-center gap-2">
            <PendingCount pendingCount={pendingCount} t={t} />
            <RefreshButton refreshing={refreshing} onRefresh={onRefresh} t={t} />
          </div>
        )}
      </div>

      {mode === "snapshot" && (
        <SnapshotList
          surface={surface}
          loading={loadingSnapshot}
          snapshot={snapshot}
          pendingByEntity={pendingByEntity}
          focusRef={focusRef}
          onClearFocus={onClearFocus}
          t={t}
        />
      )}

      {mode === "changes" && (
        <ChangesList
          loading={loadingChanges}
          changes={changes}
          pending={snapshot?.pending_changes ?? []}
          t={t}
        />
      )}

      {mode === "queries" && surface === "kb" && (
        <KbQueriesList loading={loadingQueries} queries={kbQueries} t={t} />
      )}
    </div>
  );
}

function PendingCount({
  pendingCount,
  t,
}: {
  pendingCount: number;
  t: (key: string, opts?: Record<string, unknown>) => string;
}) {
  if (pendingCount <= 0) return null;
  return (
    <span
      className="inline-flex items-center gap-1 rounded-full border border-amber-500/40 bg-amber-500/10 px-2 py-0.5 text-[11px] font-medium text-amber-700 dark:text-amber-300"
      title={t(
        "Workspace changed since last refresh. Click Refresh to commit these to the changes log.",
      )}
    >
      {t("{{n}} pending", { n: pendingCount })}
    </span>
  );
}

function RefreshButton({
  refreshing,
  onRefresh,
  t,
}: {
  refreshing: boolean;
  onRefresh: () => Promise<void>;
  t: (key: string, opts?: Record<string, unknown>) => string;
}) {
  return (
    <button
      onClick={() => void onRefresh()}
      disabled={refreshing}
      className="inline-flex items-center gap-1.5 rounded-md border border-[var(--border)] bg-[var(--card)] px-2.5 py-1 text-[12px] text-[var(--muted-foreground)] hover:text-[var(--foreground)] disabled:opacity-50"
      title={t("Re-scan workspace and record any changes")}
    >
      {refreshing ? (
        <Loader2 className="h-3 w-3 animate-spin" />
      ) : (
        <RefreshCw className="h-3 w-3" />
      )}
      {t("Refresh")}
    </button>
  );
}

interface SurfacePillProps {
  active: boolean;
  onClick: () => void;
  icon: LucideIcon;
  label: string;
}

function SurfacePill({ active, onClick, icon: Icon, label }: SurfacePillProps) {
  return (
    <button
      onClick={onClick}
      className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-[12px] transition-colors ${
        active
          ? "border-[var(--primary)]/40 bg-[var(--primary)]/10 text-[var(--primary)]"
          : "border-[var(--border)] text-[var(--muted-foreground)] hover:bg-[var(--muted)]/50 hover:text-[var(--foreground)]"
      }`}
    >
      <Icon className="h-3 w-3" />
      <span>{label}</span>
    </button>
  );
}

interface ModeStripProps {
  mode: L1Mode;
  setMode: (m: L1Mode) => void;
  surface: Surface;
  t: (key: string, opts?: Record<string, unknown>) => string;
}

function ModeStrip({ mode, setMode, surface, t }: ModeStripProps) {
  const tabs: Array<{ key: L1Mode; label: string; hidden?: boolean }> = [
    { key: "snapshot", label: t("Snapshot") },
    { key: "changes", label: t("Changes") },
    { key: "queries", label: t("Queries"), hidden: surface !== "kb" },
  ];
  return (
    <div className="inline-flex items-center gap-0.5 rounded-md border border-[var(--border)] bg-[var(--card)] p-0.5 text-[12px]">
      {tabs
        .filter((x) => !x.hidden)
        .map(({ key, label }) => {
          const active = mode === key;
          return (
            <button
              key={key}
              onClick={() => setMode(key)}
              className={`rounded px-2.5 py-1 transition-colors ${
                active
                  ? "bg-[var(--muted)] text-[var(--foreground)]"
                  : "text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
              }`}
            >
              {label}
            </button>
          );
        })}
    </div>
  );
}

interface SnapshotListProps {
  surface: Surface;
  loading: boolean;
  snapshot: SnapshotResponse | null;
  pendingByEntity: Map<string, ChangeEntryDTO["kind"]>;
  focusRef: string | null;
  onClearFocus: () => void;
  t: (key: string, opts?: Record<string, unknown>) => string;
}

function SnapshotList({
  surface,
  loading,
  snapshot,
  pendingByEntity,
  focusRef,
  onClearFocus,
  t,
}: SnapshotListProps) {
  const entities = snapshot?.entities ?? [];
  return (
    <>
      <div className="flex items-baseline justify-between text-[11.5px] text-[var(--muted-foreground)]">
        <span>
          {t("{{n}} entities", { n: entities.length })}
          {snapshot?.last_refresh && (
            <>
              {" \u00b7 "}
              {t("last refresh {{ts}}", {
                ts: formatTimestamp(snapshot.last_refresh, ""),
              })}
            </>
          )}
        </span>
        {focusRef && (
          <button
            onClick={onClearFocus}
            className="text-[var(--primary)] hover:underline"
          >
            {t("Clear focus")}
          </button>
        )}
      </div>
      {loading && entities.length === 0 ? (
        <div className="flex items-center justify-center rounded-xl border border-[var(--border)] py-12">
          <Loader2 className="h-4 w-4 animate-spin text-[var(--muted-foreground)]" />
        </div>
      ) : entities.length === 0 ? (
        <p className="rounded-xl border border-[var(--border)] px-4 py-10 text-center text-[13px] text-[var(--muted-foreground)]">
          {t("Nothing in workspace yet.")}
        </p>
      ) : (
        <ol className="rounded-xl border border-[var(--border)]">
          {entities.map((ent, idx) => (
            <EntityRow
              key={`${ent.id}#${idx}`}
              surface={surface}
              ent={ent}
              focused={focusRef === `${surface}:${ent.id}`}
              pendingKind={pendingByEntity.get(ent.id) ?? null}
              t={t}
            />
          ))}
        </ol>
      )}
    </>
  );
}

interface EntityRowProps {
  surface: Surface;
  ent: Entity;
  focused: boolean;
  pendingKind: ChangeEntryDTO["kind"] | null;
  t: (key: string, opts?: Record<string, unknown>) => string;
}

function EntityRow({ surface, ent, focused, pendingKind, t }: EntityRowProps) {
  const url = entityDeepLinkUrl(surface, ent);
  const ref = `${surface}:${ent.id}`;
  const meta = SURFACE_META[surface];
  const Icon = meta.icon;
  const preview = shorten(ent.content, 220);

  const inner = (
    <>
      <span
        className={`mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded ${
          focused
            ? "bg-[var(--primary)]/25 text-[var(--primary)]"
            : "bg-[var(--muted)] text-[var(--muted-foreground)]"
        }`}
      >
        <Icon className="h-3 w-3" />
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-baseline gap-x-2 text-[11px] text-[var(--muted-foreground)]">
          <span className="truncate text-[13px] font-medium text-[var(--foreground)]">
            {ent.label}
          </span>
          <span className="font-mono opacity-70">{ent.id}</span>
          {ent.ts && <span>{formatTimestamp(ent.ts, "")}</span>}
          {pendingKind && <PendingBadge kind={pendingKind} t={t} />}
        </div>
        {preview && (
          <p className="mt-1 line-clamp-2 text-[12px] text-[var(--muted-foreground)]/90">
            {preview}
          </p>
        )}
      </div>
      {url && (
        <ExternalLink className="mt-1 h-3.5 w-3.5 shrink-0 text-[var(--muted-foreground)] group-hover:text-[var(--primary)]" />
      )}
    </>
  );

  const focusedRing = focused
    ? "border-l-[3px] border-l-[var(--primary)] bg-[var(--primary)]/12 ring-1 ring-[var(--primary)]/30"
    : pendingKind === "added"
      ? "border-l-[3px] border-l-emerald-500 bg-emerald-500/5 hover:bg-emerald-500/10"
      : pendingKind === "modified"
        ? "border-l-[3px] border-l-amber-500 bg-amber-500/5 hover:bg-amber-500/10"
        : "border-l-[3px] border-l-transparent hover:bg-[var(--muted)]/40";
  const rowClass = `group flex items-start gap-3 border-b border-[var(--border)]/50 px-4 py-2.5 transition-colors last:border-0 ${focusedRing}`;

  return (
    <li
      id={entityAnchorId(ref)}
      data-entity-ref={ref}
      title={t("Open in {{label}}", { label: meta.label })}
    >
      {url ? (
        <Link href={url} className={rowClass}>
          {inner}
        </Link>
      ) : (
        <div className={rowClass}>{inner}</div>
      )}
    </li>
  );
}

function PendingBadge({
  kind,
  t,
}: {
  kind: ChangeEntryDTO["kind"];
  t: (key: string, opts?: Record<string, unknown>) => string;
}) {
  const map = {
    added: {
      label: t("new"),
      cls: "border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
    },
    modified: {
      label: t("modified"),
      cls: "border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-300",
    },
    removed: {
      label: t("removed"),
      cls: "border-rose-500/40 bg-rose-500/10 text-rose-700 dark:text-rose-300",
    },
  } as const;
  const cfg = map[kind];
  return (
    <span
      className={`inline-flex items-center rounded-full border px-1.5 py-0 text-[10px] font-medium ${cfg.cls}`}
      title={t("Pending \u2014 not yet committed to changes log")}
    >
      {cfg.label}
    </span>
  );
}

interface ChangesListProps {
  loading: boolean;
  changes: ChangeEntryDTO[];
  pending: ChangeEntryDTO[];
  t: (key: string, opts?: Record<string, unknown>) => string;
}

function ChangesList({ loading, changes, pending, t }: ChangesListProps) {
  if (loading && changes.length === 0 && pending.length === 0) {
    return (
      <div className="flex items-center justify-center rounded-xl border border-[var(--border)] py-12">
        <Loader2 className="h-4 w-4 animate-spin text-[var(--muted-foreground)]" />
      </div>
    );
  }
  const hasAny = changes.length > 0 || pending.length > 0;
  if (!hasAny) {
    return (
      <p className="rounded-xl border border-[var(--border)] px-4 py-10 text-center text-[13px] text-[var(--muted-foreground)]">
        {t("No changes recorded yet. Run Refresh to capture the baseline.")}
      </p>
    );
  }
  return (
    <div className="space-y-2">
      {pending.length > 0 && (
        <div className="rounded-xl border border-amber-500/40 bg-amber-500/5">
          <div className="flex items-center justify-between border-b border-amber-500/30 px-4 py-1.5 text-[11px] font-medium text-amber-700 dark:text-amber-300">
            <span>
              {t("Pending \u2014 {{n}} change(s) since last refresh", {
                n: pending.length,
              })}
            </span>
            <span className="opacity-70">{t("Click Refresh to commit")}</span>
          </div>
          <ol>
            {pending.map((c, i) => (
              <ChangeRow key={`pending-${c.entity_id}-${i}`} c={c} />
            ))}
          </ol>
        </div>
      )}
      {changes.length > 0 && (
        <ol className="rounded-xl border border-[var(--border)]">
          {changes.map((c, i) => (
            <ChangeRow key={`${c.ts}-${c.entity_id}-${i}`} c={c} />
          ))}
        </ol>
      )}
    </div>
  );
}

function ChangeRow({ c }: { c: ChangeEntryDTO }) {
  return (
    <li className="flex items-start gap-3 border-b border-[var(--border)]/50 px-4 py-2 last:border-0">
      <ChangeGlyph kind={c.kind} />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-baseline gap-x-2 text-[11px] text-[var(--muted-foreground)]">
          <span className="font-medium text-[var(--foreground)]">
            {c.label || c.entity_id}
          </span>
          <span className="font-mono opacity-70">{c.entity_id}</span>
          <span>{formatTimestamp(c.ts, "")}</span>
        </div>
      </div>
    </li>
  );
}

function ChangeGlyph({ kind }: { kind: ChangeEntryDTO["kind"] }) {
  const map = {
    added: { ch: "+", bg: "bg-emerald-500/15", fg: "text-emerald-600" },
    modified: { ch: "~", bg: "bg-amber-500/15", fg: "text-amber-600" },
    removed: { ch: "\u2212", bg: "bg-rose-500/15", fg: "text-rose-600" },
  } as const;
  const cfg = map[kind];
  return (
    <span
      className={`mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded font-mono text-[12px] font-bold ${cfg.bg} ${cfg.fg}`}
    >
      {cfg.ch}
    </span>
  );
}

interface KbQueriesListProps {
  loading: boolean;
  queries: KbQueryDTO[];
  t: (key: string, opts?: Record<string, unknown>) => string;
}

function KbQueriesList({ loading, queries, t }: KbQueriesListProps) {
  if (loading && queries.length === 0) {
    return (
      <div className="flex items-center justify-center rounded-xl border border-[var(--border)] py-12">
        <Loader2 className="h-4 w-4 animate-spin text-[var(--muted-foreground)]" />
      </div>
    );
  }
  if (queries.length === 0) {
    return (
      <p className="rounded-xl border border-[var(--border)] px-4 py-10 text-center text-[13px] text-[var(--muted-foreground)]">
        {t("No RAG queries recorded yet.")}
      </p>
    );
  }
  return (
    <ol className="rounded-xl border border-[var(--border)]">
      {queries.map((q) => {
        const kb = asString(q.payload?.kb_name) || "?";
        const query = asString(q.payload?.query);
        return (
          <li
            key={q.id}
            className="flex items-start gap-3 border-b border-[var(--border)]/50 px-4 py-2 last:border-0"
          >
            <GitCommit className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[var(--muted-foreground)]" />
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-baseline gap-x-2 text-[11px] text-[var(--muted-foreground)]">
                <span className="font-medium text-[var(--foreground)]">
                  {kb}
                </span>
                <span>{formatTimestamp(q.ts, "")}</span>
              </div>
              <p className="mt-0.5 truncate text-[12.5px] text-[var(--foreground)]">
                {query}
              </p>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
