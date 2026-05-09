"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTranslation } from "react-i18next";
import {
  ArrowLeft,
  BookOpen,
  Brain,
  Database,
  Layers3,
  Loader2,
  LogOut,
  Search,
  ShieldCheck,
  UserCircle,
  Wrench,
} from "lucide-react";
import {
  AUTH_ENABLED,
  fetchAuthStatus,
  logout,
  type AuthStatus,
} from "@/lib/auth";
import { fetchMyAccess } from "@/features/multi-user/api";
import type {
  CurrentUserAccess,
  ModelAccess,
  ModelAccessItem,
} from "@/features/multi-user/types";

type ModelKey = keyof ModelAccess;

const MODEL_ROWS: Array<[ModelKey, string, typeof Brain]> = [
  ["llm", "LLM", Brain],
  ["embedding", "Embedding", Database],
  ["search", "Search", Search],
];

function modelLabel(item: ModelAccessItem): string {
  return item.model || item.provider || item.name || item.model_id || "Model";
}

function spaceLabel(space: Record<string, unknown>, index: number): string {
  const value =
    space.space_id ||
    space.name ||
    space.target ||
    space.source_path ||
    `Space ${index + 1}`;
  return String(value);
}

function Field({
  label,
  value,
}: {
  label: string;
  value: string | undefined;
}) {
  return (
    <div>
      <dt className="text-xs text-[var(--muted-foreground)]">{label}</dt>
      <dd className="mt-1 truncate text-sm font-medium text-[var(--foreground)]">
        {value || "-"}
      </dd>
    </div>
  );
}

export default function AccountPage() {
  const router = useRouter();
  const { t } = useTranslation();
  const [status, setStatus] = useState<AuthStatus | null>(null);
  const [access, setAccess] = useState<CurrentUserAccess | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [nextStatus, nextAccess] = await Promise.all([
        fetchAuthStatus(),
        fetchMyAccess(),
      ]);
      setStatus(nextStatus);
      setAccess(nextAccess);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("Failed to load account"));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void load();
  }, [load]);

  const user = access?.user ?? {
    id: status?.user_id || "",
    username: status?.username || "",
    role: (status?.role === "admin" ? "admin" : "user") as "admin" | "user",
    is_admin: Boolean(status?.is_admin),
  };
  const modelAccess = useMemo(
    () => ({
      llm: access?.models?.llm || [],
      embedding: access?.models?.embedding || [],
      search: access?.models?.search || [],
    }),
    [access],
  );
  const canLogout = Boolean((status?.enabled || AUTH_ENABLED) && status?.authenticated);
  const canOpenAdmin = Boolean(status?.enabled && user.is_admin);

  async function handleLogout() {
    await logout();
    router.replace("/login");
  }

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-[var(--muted-foreground)]">
        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
        {t("Loading account...")}
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex h-full items-center justify-center px-6">
        <div className="w-full max-w-sm rounded-xl border border-[var(--border)] bg-[var(--card)] p-5 text-center">
          <p className="text-sm text-red-500">{error}</p>
          <button
            onClick={load}
            className="mt-4 rounded-lg border border-[var(--border)] px-3 py-1.5 text-sm text-[var(--foreground)] hover:bg-[var(--background)]"
          >
            {t("Retry")}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto bg-[var(--background)] px-4 py-8 [scrollbar-gutter:stable]">
      <div className="mx-auto max-w-4xl">
        <div className="mb-6 flex flex-wrap items-center gap-3">
          <Link
            href="/"
            className="flex items-center gap-1.5 text-sm text-[var(--muted-foreground)] transition-colors hover:text-[var(--foreground)]"
          >
            <ArrowLeft size={15} />
            {t("Back")}
          </Link>
          <div className="min-w-0 flex-1">
            <h1 className="text-xl font-semibold text-[var(--foreground)]">
              {t("Account")}
            </h1>
            <p className="mt-0.5 text-sm text-[var(--muted-foreground)]">
              {status?.enabled ? t("Signed in account") : t("Local workspace")}
            </p>
          </div>
          {canOpenAdmin && (
            <Link
              href="/admin/users"
              className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--border)] px-3 py-1.5 text-sm text-[var(--foreground)] transition-colors hover:bg-[var(--card)]"
            >
              <ShieldCheck size={14} />
              {t("User Management")}
            </Link>
          )}
          {canLogout && (
            <button
              onClick={handleLogout}
              className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--border)] px-3 py-1.5 text-sm text-red-500 transition-colors hover:bg-red-500/10"
            >
              <LogOut size={14} />
              {t("Sign out")}
            </button>
          )}
        </div>

        <section className="rounded-xl border border-[var(--border)] bg-[var(--card)] p-5 shadow-sm">
          <div className="flex flex-wrap items-center gap-4">
            <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-[var(--background)] text-[var(--foreground)]">
              <UserCircle size={25} strokeWidth={1.5} />
            </div>
            <div className="min-w-0 flex-1">
              <div className="truncate text-lg font-semibold text-[var(--foreground)]">
                {user.username || t("Account")}
              </div>
              <div className="mt-1 text-sm text-[var(--muted-foreground)]">
                {user.role === "admin" ? t("Admin") : t("User")}
              </div>
            </div>
          </div>

          <dl className="mt-6 grid gap-4 sm:grid-cols-3">
            <Field label={t("User ID")} value={user.id} />
            <Field
              label={t("Authentication")}
              value={status?.enabled ? t("Enabled") : t("Local mode")}
            />
            <Field
              label={t("Session")}
              value={status?.authenticated ? t("Active") : t("Signed out")}
            />
          </dl>
        </section>

        <div className="mt-5 grid gap-4 lg:grid-cols-3">
          {MODEL_ROWS.map(([key, label, Icon]) => {
            const items = modelAccess[key];
            return (
              <section
                key={key}
                className="rounded-xl border border-[var(--border)] bg-[var(--card)] p-4"
              >
                <div className="flex items-center gap-2 text-sm font-medium text-[var(--foreground)]">
                  <Icon size={16} strokeWidth={1.6} />
                  {t(label)}
                </div>
                {items.length ? (
                  <div className="mt-4 space-y-2">
                    {items.map((item, index) => (
                      <div
                        key={`${item.profile_id || key}-${item.model_id || index}`}
                        className="rounded-lg border border-[var(--border)]/70 bg-[var(--background)]/40 px-3 py-2"
                      >
                        <div className="truncate text-sm font-medium text-[var(--foreground)]">
                          {modelLabel(item)}
                        </div>
                        <div className="mt-0.5 text-xs text-[var(--muted-foreground)]">
                          {item.available === false ? t("Unavailable") : t("Ready")}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="mt-4 text-sm text-[var(--muted-foreground)]">
                    {user.is_admin ? t("Admin workspace") : t("Not assigned yet")}
                  </p>
                )}
              </section>
            );
          })}
        </div>

        <div className="mt-5 grid gap-4 lg:grid-cols-3">
          <section className="rounded-xl border border-[var(--border)] bg-[var(--card)] p-4">
            <div className="flex items-center gap-2 text-sm font-medium text-[var(--foreground)]">
              <BookOpen size={16} strokeWidth={1.6} />
              {t("Knowledge bases")}
            </div>
            {access?.knowledge_bases?.length ? (
              <div className="mt-4 space-y-2">
                {access.knowledge_bases.map((kb) => (
                  <div
                    key={kb.id}
                    className="rounded-lg border border-[var(--border)]/70 bg-[var(--background)]/40 px-3 py-2"
                  >
                    <div className="truncate text-sm font-medium text-[var(--foreground)]">
                      {kb.name}
                    </div>
                    <div className="mt-0.5 text-xs text-[var(--muted-foreground)]">
                      {kb.provenance_label || kb.source}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="mt-4 text-sm text-[var(--muted-foreground)]">
                {t("No knowledge bases")}
              </p>
            )}
          </section>

          <section className="rounded-xl border border-[var(--border)] bg-[var(--card)] p-4">
            <div className="flex items-center gap-2 text-sm font-medium text-[var(--foreground)]">
              <Wrench size={16} strokeWidth={1.6} />
              {t("Skills")}
            </div>
            {access?.skills?.length ? (
              <div className="mt-4 flex flex-wrap gap-2">
                {access.skills.map((skill) => (
                  <span
                    key={skill}
                    className="rounded-full border border-[var(--border)] bg-[var(--background)]/50 px-2.5 py-1 text-xs text-[var(--foreground)]"
                  >
                    {skill}
                  </span>
                ))}
              </div>
            ) : (
              <p className="mt-4 text-sm text-[var(--muted-foreground)]">
                {user.is_admin ? t("Admin workspace") : t("Not assigned yet")}
              </p>
            )}
          </section>

          <section className="rounded-xl border border-[var(--border)] bg-[var(--card)] p-4">
            <div className="flex items-center gap-2 text-sm font-medium text-[var(--foreground)]">
              <Layers3 size={16} strokeWidth={1.6} />
              {t("Spaces")}
            </div>
            {access?.spaces?.length ? (
              <div className="mt-4 space-y-2">
                {access.spaces.map((space, index) => (
                  <div
                    key={`${spaceLabel(space, index)}-${index}`}
                    className="rounded-lg border border-[var(--border)]/70 bg-[var(--background)]/40 px-3 py-2 text-sm text-[var(--foreground)]"
                  >
                    {spaceLabel(space, index)}
                  </div>
                ))}
              </div>
            ) : (
              <p className="mt-4 text-sm text-[var(--muted-foreground)]">
                {user.is_admin ? t("Admin workspace") : t("Not assigned yet")}
              </p>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}
