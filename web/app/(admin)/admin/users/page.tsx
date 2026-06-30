"use client";

import { Fragment, useEffect, useState, useCallback, useRef } from "react";
import { usePathname, useRouter } from "next/navigation";
import { fetchAuthStatus } from "@/lib/auth";
import {
  listUsers,
  deleteUser,
  setUserRole,
  setUserDisabled,
  resetUserPassword,
  createUser,
  revokeUserSessions,
  listInvites,
  createInvite,
  deleteInvite,
  downloadUsersCsv,
  importUsersCsv,
  type UserRecord,
  type InviteRecord,
} from "@/lib/admin-api";
import { GrantEditor } from "@/features/multi-user/components/GrantEditor";
import {
  downloadUserExport,
  fetchAdminAuditEvents,
} from "@/features/multi-user/api";
import type {
  AuditEvent,
  DeleteDataAction,
} from "@/features/multi-user/types";
import { UserAvatar } from "@/components/UserAvatar";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { filterUsersByQuery } from "@/lib/admin-users";
import {
  Search,
  Shield,
  ShieldCheck,
  ShieldOff,
  Trash2,
  RefreshCw,
  ArrowLeft,
  SlidersHorizontal,
  UserPlus,
  Users,
  X,
  Ban,
  CheckCircle2,
  KeyRound,
  Download,
  ScrollText,
  LogOut,
  Copy,
  Upload,
} from "lucide-react";
import Link from "next/link";
import { useTranslation } from "react-i18next";

function formatDate(iso: string): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  } catch {
    return "—";
  }
}

function isEmail(value: string): boolean {
  return /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(value.trim());
}

export default function AdminUsersPage() {
  const router = useRouter();
  const { i18n } = useTranslation();
  const zh = i18n.language?.toLowerCase().startsWith("zh");
  const tr = useCallback((cn: string, en: string) => (zh ? cn : en), [zh]);
  const inSettings = (usePathname() ?? "").startsWith("/settings/");
  const importInputRef = useRef<HTMLInputElement>(null);
  const [currentUser, setCurrentUser] = useState<string | null>(null);
  const [users, setUsers] = useState<UserRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [actionError, setActionError] = useState("");
  const [actionNotice, setActionNotice] = useState("");
  const [expandedUserId, setExpandedUserId] = useState<string | null>(null);
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [query, setQuery] = useState("");
  const [confirmTarget, setConfirmTarget] = useState<{
    kind:
      | "delete"
      | "promote"
      | "demote"
      | "disable"
      | "enable"
      | "revoke";
    user: UserRecord;
  } | null>(null);
  const [resetTarget, setResetTarget] = useState<UserRecord | null>(null);
  const [resetPassword, setResetPassword] = useState("");
  const [resetError, setResetError] = useState("");
  const [resetSubmitting, setResetSubmitting] = useState(false);
  const [confirmBusy, setConfirmBusy] = useState(false);
  const [disableReason, setDisableReason] = useState("");
  const [createUsername, setCreateUsername] = useState("");
  const [createPassword, setCreatePassword] = useState("");
  const [createSubmitting, setCreateSubmitting] = useState(false);
  const [createError, setCreateError] = useState("");
  const [invites, setInvites] = useState<InviteRecord[]>([]);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteSubmitting, setInviteSubmitting] = useState(false);
  const [inviteError, setInviteError] = useState("");
  const [copiedInvite, setCopiedInvite] = useState("");
  const [deleteDataAction, setDeleteDataAction] =
    useState<DeleteDataAction>("keep");
  const [exportingUserId, setExportingUserId] = useState<string | null>(null);
  const [exportingUsersCsv, setExportingUsersCsv] = useState(false);
  const [importingUsersCsv, setImportingUsersCsv] = useState(false);
  const [showAudit, setShowAudit] = useState(false);
  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>([]);
  const [auditLoading, setAuditLoading] = useState(false);
  const [auditError, setAuditError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [userData, inviteData] = await Promise.all([
        listUsers(),
        listInvites(),
      ]);
      setUsers(userData);
      setInvites(inviteData);
    } catch (e) {
      setError(e instanceof Error ? e.message : tr("加载用户失败", "Failed to load users"));
    } finally {
      setLoading(false);
    }
  }, [tr]);

  useEffect(() => {
    fetchAuthStatus().then((status) => {
      if (!status?.authenticated) {
        router.replace("/login");
        return;
      }
      if (status.role !== "admin") {
        router.replace("/");
        return;
      }
      setCurrentUser(status.username ?? null);
      void load();
    });
  }, [router, load]);

  function openCreateDialog() {
    setCreateUsername("");
    setCreatePassword("");
    setCreateError("");
    setShowCreateDialog(true);
  }

  function closeCreateDialog() {
    if (createSubmitting) return;
    setShowCreateDialog(false);
  }

  async function handleCreateSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (createSubmitting) return;
    setCreateError("");
    const username = createUsername.trim().toLowerCase();
    if (!username) {
      setCreateError(tr("邮箱不能为空。", "Email is required."));
      return;
    }
    if (!isEmail(username)) {
      setCreateError(tr("请输入有效的邮箱地址。", "Enter a valid email address."));
      return;
    }
    if (createPassword.length < 8) {
      setCreateError(tr("密码至少需要 8 个字符。", "Password must be at least 8 characters."));
      return;
    }
    setCreateSubmitting(true);
    try {
      await createUser(username, createPassword);
      setShowCreateDialog(false);
      await load();
    } catch (e) {
      setCreateError(e instanceof Error ? e.message : tr("创建用户失败", "Failed to create user"));
    } finally {
      setCreateSubmitting(false);
    }
  }

  function inviteLink(code: string): string {
    const path = `/register?invite=${encodeURIComponent(code)}`;
    return `${window.location.origin}${path}`;
  }

  async function copyInvite(invite: InviteRecord) {
    try {
      await navigator.clipboard.writeText(inviteLink(invite.code));
      setCopiedInvite(invite.code);
      window.setTimeout(() => setCopiedInvite(""), 1500);
    } catch {
      setActionError(
        tr(
          "邀请码已创建，但无法复制链接。",
          "Invite created, but the link could not be copied.",
        ),
      );
    }
  }

  async function handleInviteSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (inviteSubmitting) return;
    setInviteError("");
    setActionError("");
    setInviteSubmitting(true);
    try {
      const invite = await createInvite(inviteEmail.trim());
      setInvites((prev) => [invite, ...prev]);
      setInviteEmail("");
      await copyInvite(invite);
    } catch (e) {
      setInviteError(e instanceof Error ? e.message : tr("创建邀请失败", "Failed to create invite"));
    } finally {
      setInviteSubmitting(false);
    }
  }

  async function handleDeleteInvite(code: string) {
    setActionError("");
    try {
      await deleteInvite(code);
      setInvites((prev) => prev.filter((invite) => invite.code !== code));
    } catch (e) {
      setActionError(e instanceof Error ? e.message : tr("删除邀请失败", "Failed to delete invite"));
    }
  }

  async function handleConfirmAction() {
    if (!confirmTarget || confirmBusy) return;
    const { kind, user } = confirmTarget;
    setConfirmBusy(true);
    setActionError("");
    try {
      if (kind === "delete") {
        await deleteUser(user.username, deleteDataAction);
        setUsers((prev) => prev.filter((u) => u.username !== user.username));
      } else if (kind === "disable" || kind === "enable") {
        const disabled = kind === "disable";
        await setUserDisabled(user.username, disabled, disableReason);
        setUsers((prev) =>
          prev.map((u) =>
            u.username === user.username
              ? {
                  ...u,
                  disabled,
                  disabled_reason: disabled ? disableReason.trim() : "",
                }
              : u,
          ),
        );
      } else if (kind === "revoke") {
        await revokeUserSessions(user.username);
      } else {
        const newRole = kind === "promote" ? "admin" : "user";
        await setUserRole(user.username, newRole);
        setUsers((prev) =>
          prev.map((u) =>
            u.username === user.username ? { ...u, role: newRole } : u,
          ),
        );
        if (newRole === "admin") {
          setExpandedUserId((current) =>
            current === user.id ? null : current,
          );
        }
      }
      setConfirmTarget(null);
      setDeleteDataAction("keep");
      setDisableReason("");
    } catch (e) {
      setConfirmTarget(null);
      setDisableReason("");
      setActionError(
        e instanceof Error
          ? e.message
          : confirmTarget.kind === "delete"
            ? tr("删除用户失败", "Failed to delete user")
            : tr("更新角色失败", "Failed to update role"),
      );
    } finally {
      setConfirmBusy(false);
    }
  }

  async function handleExport(user: UserRecord) {
    if (!user.id || exportingUserId) return;
    setActionError("");
    setExportingUserId(user.id);
    try {
      await downloadUserExport(user.id);
    } catch (e) {
      setActionError(e instanceof Error ? e.message : tr("导出用户失败", "Failed to export user"));
    } finally {
      setExportingUserId(null);
    }
  }

  async function handleUsersCsvExport() {
    if (exportingUsersCsv) return;
    setActionError("");
    setActionNotice("");
    setExportingUsersCsv(true);
    try {
      await downloadUsersCsv();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : tr("导出用户列表失败", "Failed to export users"));
    } finally {
      setExportingUsersCsv(false);
    }
  }

  async function handleUsersCsvImport(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file || importingUsersCsv) return;
    setActionError("");
    setActionNotice("");
    setImportingUsersCsv(true);
    try {
      const result = await importUsersCsv(file);
      setActionNotice(
        tr(
          `已导入 ${result.created} 个用户。`,
          `Imported ${result.created} user${result.created === 1 ? "" : "s"}.`,
        ),
      );
      await load();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : tr("导入用户失败", "Failed to import users"));
    } finally {
      setImportingUsersCsv(false);
    }
  }

  async function openAudit() {
    setShowAudit(true);
    setAuditLoading(true);
    setAuditError("");
    try {
      setAuditEvents(await fetchAdminAuditEvents(50));
    } catch (e) {
      setAuditError(e instanceof Error ? e.message : tr("加载审计日志失败", "Failed to load audit"));
    } finally {
      setAuditLoading(false);
    }
  }

  async function handleResetSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!resetTarget || resetSubmitting) return;
    setResetError("");
    if (resetPassword.length < 8) {
      setResetError(tr("密码至少需要 8 个字符。", "Password must be at least 8 characters."));
      return;
    }
    setResetSubmitting(true);
    try {
      await resetUserPassword(resetTarget.username, resetPassword);
      setResetTarget(null);
      setResetPassword("");
    } catch (e) {
      setResetError(e instanceof Error ? e.message : tr("重置密码失败", "Failed to reset password"));
    } finally {
      setResetSubmitting(false);
    }
  }

  useEffect(() => {
    if (!expandedUserId) return;
    const expanded = users.find((user) => user.id === expandedUserId);
    if (!expanded || expanded.role === "admin") {
      setExpandedUserId(null);
    }
  }, [expandedUserId, users]);

  const normalizedQuery = query.trim().toLowerCase();
  const filteredUsers = filterUsersByQuery(users, query);

  return (
    <div
      className={
        inSettings
          ? ""
          : "h-screen overflow-y-auto bg-[var(--background)] px-4 py-10 [scrollbar-gutter:stable]"
      }
    >
      <div className={inSettings ? "" : "mx-auto max-w-3xl"}>
        {/* Header */}
        <div className="mb-8">
          {!inSettings && (
            <Link
              href="/settings"
              className="mb-4 inline-flex items-center gap-1.5 text-sm text-[var(--muted-foreground)] hover:text-[var(--foreground)] transition-colors"
            >
              <ArrowLeft size={16} />
              {tr("返回", "Back")}
            </Link>
          )}
          <div className="flex items-start justify-between gap-4">
            <div>
              <h1 className="font-serif text-xl font-semibold text-[var(--foreground)]">
                {tr("用户管理", "User Management")}
              </h1>
              <p className="mt-0.5 text-sm text-[var(--muted-foreground)]">
                {tr("管理已注册账号", "Manage registered accounts")}
              </p>
            </div>
            <div className="flex shrink-0 flex-wrap items-center justify-end gap-2">
              <button
                onClick={openAudit}
                className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm
                           border border-[var(--border)] text-[var(--foreground)]
                           hover:bg-[var(--card)] transition-colors"
              >
                <ScrollText size={14} />
                {tr("审计", "Audit")}
              </button>
              <button
                onClick={handleUsersCsvExport}
                disabled={exportingUsersCsv}
                className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm
                           border border-[var(--border)] text-[var(--foreground)]
                           hover:bg-[var(--card)] disabled:opacity-50 transition-colors"
              >
                <Download size={14} />
                {exportingUsersCsv
                  ? tr("导出中…", "Exporting…")
                  : tr("导出 CSV", "Export CSV")}
              </button>
              <button
                onClick={() => importInputRef.current?.click()}
                disabled={importingUsersCsv}
                className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm
                           border border-[var(--border)] text-[var(--foreground)]
                           hover:bg-[var(--card)] disabled:opacity-50 transition-colors"
              >
                <Upload size={14} />
                {importingUsersCsv
                  ? tr("导入中…", "Importing…")
                  : tr("导入 CSV", "Import CSV")}
              </button>
              <input
                ref={importInputRef}
                type="file"
                accept=".csv,text/csv"
                className="hidden"
                onChange={handleUsersCsvImport}
              />
              <button
                onClick={openCreateDialog}
                className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm
                           border border-[var(--border)] text-[var(--foreground)]
                           hover:bg-[var(--card)] transition-colors"
              >
                <UserPlus size={14} />
                {tr("添加用户", "Add user")}
              </button>
              <button
                onClick={load}
                disabled={loading}
                className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm
                           border border-[var(--border)] text-[var(--muted-foreground)]
                           hover:text-[var(--foreground)] hover:bg-[var(--card)]
                           disabled:opacity-50 transition-colors"
              >
                <RefreshCw
                  size={14}
                  className={loading ? "animate-spin" : ""}
                />
                {tr("刷新", "Refresh")}
              </button>
            </div>
          </div>
        </div>

        {actionError && (
          <div className="mb-4 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-600 dark:text-red-400">
            {actionError}
          </div>
        )}
        {actionNotice && (
          <div className="mb-4 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-700 dark:text-emerald-300">
            {actionNotice}
          </div>
        )}

        {!loading && !error && (
          <section className="mb-4 rounded-2xl border border-[var(--border)] bg-[var(--card)] p-4 shadow-sm">
            <form
              onSubmit={handleInviteSubmit}
              className="flex flex-col gap-3 sm:flex-row sm:items-end"
            >
              <label className="flex-1 text-xs text-[var(--muted-foreground)]">
                {tr("注册邀请", "Registration invite")}
                <input
                  type="email"
                  value={inviteEmail}
                  onChange={(e) => setInviteEmail(e.target.value)}
                  disabled={inviteSubmitting}
                  placeholder="learner@example.com"
                  className="mt-1 w-full rounded-lg border border-[var(--border)] bg-transparent px-3 py-2 text-sm text-[var(--foreground)] outline-none focus:border-[var(--ring)]"
                />
              </label>
              <button
                type="submit"
                disabled={inviteSubmitting}
                className="inline-flex items-center justify-center gap-1.5 rounded-lg bg-[var(--foreground)] px-3 py-2 text-sm font-medium text-[var(--background)] hover:opacity-90 disabled:opacity-40"
              >
                <KeyRound size={14} />
                {inviteSubmitting
                  ? tr("创建中…", "Creating…")
                  : tr("创建邀请", "Create invite")}
              </button>
            </form>

            {inviteError && (
              <p className="mt-2 text-xs text-red-500">{inviteError}</p>
            )}

            {invites.length > 0 && (
              <div className="mt-3 divide-y divide-[var(--border)] rounded-lg border border-[var(--border)]">
                {invites.slice(0, 5).map((invite) => {
                  const used = Boolean(invite.used_at);
                  return (
                    <div
                      key={invite.code}
                      className="flex items-center justify-between gap-3 px-3 py-2 text-xs"
                    >
                      <div className="min-w-0">
                        <p className="truncate font-mono text-[var(--foreground)]">
                          {invite.code}
                        </p>
                        <p className="truncate text-[var(--muted-foreground)]">
                          {used
                            ? tr(
                                `已被 ${invite.used_by || "未知用户"} 使用`,
                                `Used by ${invite.used_by || "unknown"}`,
                              )
                            : invite.email || tr("任意邮箱", "Any email")}
                        </p>
                      </div>
                      <div className="flex shrink-0 items-center gap-1">
                        {!used && (
                          <button
                            type="button"
                            onClick={() => copyInvite(invite)}
                            className="rounded-md p-1.5 text-[var(--muted-foreground)] hover:bg-[var(--background)] hover:text-[var(--foreground)]"
                            aria-label={tr("复制邀请链接", "Copy invite link")}
                            title={tr("复制邀请链接", "Copy invite link")}
                          >
                            <Copy size={14} />
                          </button>
                        )}
                        <button
                          type="button"
                          onClick={() => void handleDeleteInvite(invite.code)}
                          className="rounded-md p-1.5 text-[var(--muted-foreground)] hover:bg-[var(--background)] hover:text-red-500"
                          aria-label={tr("删除邀请", "Delete invite")}
                          title={tr("删除邀请", "Delete invite")}
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                      {copiedInvite === invite.code && (
                        <span className="text-[var(--muted-foreground)]">
                          {tr("已复制", "Copied")}
                        </span>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </section>
        )}

        {!loading && !error && users.length > 0 && (
          <div className="mb-4 flex items-center gap-3">
            <div className="relative flex-1">
              <Search
                size={14}
                className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[var(--muted-foreground)]"
              />
              <input
                type="search"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder={tr("搜索用户…", "Search users…")}
                aria-label={tr("搜索用户", "Search users")}
                className="w-full rounded-lg border border-[var(--border)] bg-[var(--card)] py-2 pl-9 pr-3 text-sm
                           text-[var(--foreground)] placeholder:text-[var(--muted-foreground)]/70
                           outline-none focus:border-[var(--ring)] transition-colors"
              />
            </div>
            <span className="shrink-0 text-xs text-[var(--muted-foreground)]">
              {normalizedQuery
                ? tr(
                    `${filteredUsers.length} / ${users.length}`,
                    `${filteredUsers.length} of ${users.length}`,
                  )
                : tr(
                    `${users.length} 个用户`,
                    `${users.length} ${users.length === 1 ? "user" : "users"}`,
                  )}
            </span>
          </div>
        )}

        <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] overflow-hidden shadow-sm">
          {loading ? (
            <div className="divide-y divide-[var(--border)]" aria-hidden>
              {[0, 1, 2].map((row) => (
                <div
                  key={row}
                  className="flex animate-pulse items-center gap-3 px-5 py-4"
                >
                  <div className="h-8 w-8 rounded-full bg-[var(--muted)]/60" />
                  <div className="flex-1 space-y-2">
                    <div className="h-3 w-36 rounded bg-[var(--muted)]/60" />
                    <div className="h-2.5 w-24 rounded bg-[var(--muted)]/40" />
                  </div>
                  <div className="h-5 w-16 rounded-full bg-[var(--muted)]/40" />
                </div>
              ))}
            </div>
          ) : error ? (
            <div className="flex items-center justify-center py-16 text-red-500 text-sm">
              {error}
            </div>
          ) : users.length === 0 ? (
            <div className="flex flex-col items-center justify-center px-6 py-16 text-center">
              <Users
                size={28}
                strokeWidth={1.5}
                className="text-[var(--muted-foreground)]/50"
              />
              <p className="mt-3 text-sm font-medium text-[var(--foreground)]">
                {tr("暂无用户", "No users yet")}
              </p>
              <p className="mt-1 text-sm text-[var(--muted-foreground)]">
                {tr(
                  "你创建的账号会显示在这里。",
                  "Accounts you create will appear here.",
                )}
              </p>
              <button
                onClick={openCreateDialog}
                className="mt-4 flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm
                           border border-[var(--border)] text-[var(--foreground)]
                           hover:bg-[var(--background)]/60 transition-colors"
              >
                <UserPlus size={14} />
                {tr("添加用户", "Add user")}
              </button>
            </div>
          ) : filteredUsers.length === 0 ? (
            <div className="flex flex-col items-center justify-center px-6 py-16 text-center">
              <Search
                size={28}
                strokeWidth={1.5}
                className="text-[var(--muted-foreground)]/50"
              />
              <p className="mt-3 text-sm font-medium text-[var(--foreground)]">
                {tr(
                  `没有匹配“${query.trim()}”的用户`,
                  `No users match “${query.trim()}”`,
                )}
              </p>
              <button
                onClick={() => setQuery("")}
                className="mt-4 rounded-lg px-3 py-1.5 text-sm border border-[var(--border)]
                           text-[var(--muted-foreground)] hover:text-[var(--foreground)]
                           hover:bg-[var(--background)]/60 transition-colors"
              >
                {tr("清除搜索", "Clear search")}
              </button>
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[var(--border)] text-left text-xs text-[var(--muted-foreground)] uppercase tracking-wider">
                  <th className="px-5 py-3 font-medium">
                    {tr("用户名", "Username")}
                  </th>
                  <th className="px-5 py-3 font-medium">
                    {tr("角色", "Role")}
                  </th>
                  <th className="px-5 py-3 font-medium">
                    {tr("加入时间", "Joined")}
                  </th>
                  <th className="px-5 py-3 font-medium text-right">
                    {tr("操作", "Actions")}
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--border)]">
                {filteredUsers.map((user) => {
                  const isSelf = user.username === currentUser;
                  const isAdmin = user.role === "admin";
                  const canManageAssignments = !isAdmin && Boolean(user.id);
                  return (
                    <Fragment key={user.username}>
                      <tr className="group hover:bg-[var(--background)]/50 transition-colors">
                        <td className="px-5 py-3">
                          <div className="flex items-center gap-3">
                            <UserAvatar
                              username={user.username}
                              userId={user.id}
                              avatar={user.avatar}
                              role={user.role}
                              size={32}
                            />
                            <span className="min-w-0 truncate font-medium text-[var(--foreground)]">
                              {user.username}
                              {isSelf && (
                                <span className="ml-2 text-xs font-normal text-[var(--muted-foreground)]">
                                  {tr("（你）", "(you)")}
                                </span>
                              )}
                            </span>
                          </div>
                        </td>
                        <td className="px-5 py-3">
                          <span
                            className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium
                            ${
                              isAdmin
                                ? "bg-amber-500/15 text-amber-600 dark:text-amber-400"
                                : "bg-[var(--muted)]/50 text-[var(--muted-foreground)]"
                            }`}
                          >
                            {isAdmin && (
                              <ShieldCheck size={11} strokeWidth={2} />
                            )}
                            {isAdmin ? tr("管理员", "Admin") : tr("用户", "User")}
                          </span>
                          {user.disabled && (
                            <span
                              className="ml-1.5 inline-flex items-center gap-1 rounded-full bg-red-500/10 px-2 py-0.5 text-xs font-medium text-red-500"
                              title={user.disabled_reason || tr("已禁用", "Disabled")}
                            >
                              <Ban size={11} />
                              {tr("已禁用", "Disabled")}
                            </span>
                          )}
                        </td>
                        <td className="px-5 py-3.5 text-[var(--muted-foreground)]">
                          {formatDate(user.created_at)}
                        </td>
                        <td className="px-5 py-3.5">
                          <div className="flex items-center justify-end gap-1.5">
                            {canManageAssignments && (
                              <button
                                onClick={() =>
                                  setExpandedUserId((current) =>
                                    current === user.id ? null : user.id,
                                  )
                                }
                                title={tr("管理授权", "Manage assignments")}
                                className="rounded-lg p-1.5 text-[var(--muted-foreground)]
                                         hover:bg-[var(--background)] hover:text-[var(--foreground)]
                                         transition-colors"
                              >
                                <SlidersHorizontal size={15} />
                              </button>
                            )}
                            {canManageAssignments && (
                              <button
                                onClick={() => handleExport(user)}
                                disabled={exportingUserId === user.id}
                                title={tr(
                                  `导出 ${user.username}`,
                                  `Export ${user.username}`,
                                )}
                                className="rounded-lg p-1.5 text-[var(--muted-foreground)]
                                         hover:bg-[var(--background)] hover:text-[var(--foreground)]
                                         disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                              >
                                <Download size={15} />
                              </button>
                            )}
                            <button
                              onClick={() => {
                                setResetTarget(user);
                                setResetPassword("");
                                setResetError("");
                              }}
                              disabled={isSelf}
                              title={
                                isSelf
                                  ? tr(
                                      "请在个人资料中修改自己的密码",
                                      "Use profile settings to change your own password",
                                    )
                                  : tr(
                                      `重置 ${user.username} 的密码`,
                                      `Reset password for ${user.username}`,
                                    )
                              }
                              className="rounded-lg p-1.5 text-[var(--muted-foreground)]
                                       hover:bg-[var(--background)] hover:text-[var(--foreground)]
                                       disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                            >
                              <KeyRound size={15} />
                            </button>
                            <button
                              onClick={() =>
                                setConfirmTarget({ kind: "revoke", user })
                              }
                              disabled={isSelf}
                              title={
                                isSelf
                                  ? tr(
                                      "不能在这里撤销自己的当前会话",
                                      "Cannot revoke your current session here",
                                    )
                                  : tr(
                                      `让 ${user.username} 退出登录`,
                                      `Sign out ${user.username}`,
                                    )
                              }
                              className="rounded-lg p-1.5 text-[var(--muted-foreground)]
                                       hover:bg-[var(--background)] hover:text-[var(--foreground)]
                                       disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                            >
                              <LogOut size={15} />
                            </button>
                            <button
                              onClick={() => {
                                setDisableReason(user.disabled_reason ?? "");
                                setConfirmTarget({
                                  kind: user.disabled ? "enable" : "disable",
                                  user,
                                });
                              }}
                              disabled={isSelf}
                              title={
                                isSelf
                                  ? tr(
                                      "不能禁用自己的账号",
                                      "Cannot disable your own account",
                                    )
                                  : user.disabled
                                    ? tr(
                                        `启用 ${user.username}`,
                                        `Enable ${user.username}`,
                                      )
                                    : tr(
                                        `禁用 ${user.username}`,
                                        `Disable ${user.username}`,
                                      )
                              }
                              className="rounded-lg p-1.5 text-[var(--muted-foreground)]
                                       hover:bg-[var(--background)] hover:text-[var(--foreground)]
                                       disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                            >
                              {user.disabled ? (
                                <CheckCircle2 size={15} />
                              ) : (
                                <Ban size={15} />
                              )}
                            </button>
                            <button
                              onClick={() =>
                                setConfirmTarget({
                                  kind: isAdmin ? "demote" : "promote",
                                  user,
                                })
                              }
                              disabled={isSelf}
                              title={
                                isSelf
                                  ? tr(
                                      "不能修改自己的角色",
                                      "Cannot change your own role",
                                    )
                                  : user.role === "admin"
                                    ? tr("降级为用户", "Demote to user")
                                    : tr("提升为管理员", "Promote to admin")
                              }
                              className="rounded-lg p-1.5 text-[var(--muted-foreground)]
                                       hover:bg-[var(--background)] hover:text-[var(--foreground)]
                                       disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                            >
                              {user.role === "admin" ? (
                                <ShieldOff size={15} />
                              ) : (
                                <Shield size={15} />
                              )}
                            </button>
                            <button
                              onClick={() => {
                                setDeleteDataAction("keep");
                                setConfirmTarget({ kind: "delete", user });
                              }}
                              disabled={isSelf}
                              title={
                                isSelf
                                  ? tr(
                                      "不能删除自己的账号",
                                      "Cannot delete your own account",
                                    )
                                  : tr(
                                      `删除 ${user.username}`,
                                      `Delete ${user.username}`,
                                    )
                              }
                              className="rounded-lg p-1.5 text-[var(--muted-foreground)]
                                       hover:bg-red-500/10 hover:text-red-500
                                       disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                            >
                              <Trash2 size={15} />
                            </button>
                          </div>
                        </td>
                      </tr>
                      {canManageAssignments && expandedUserId === user.id && (
                        <tr>
                          <td colSpan={4} className="p-0">
                            <GrantEditor key={user.id} userId={user.id} />
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>

        <p className="mt-8 text-center text-xs text-[var(--muted-foreground)]">
          {tr("DeepTutor 管理 · 用户管理", "DeepTutor Admin · User Management")}
        </p>
      </div>

      <ConfirmDialog
        open={confirmTarget !== null}
        title={
          confirmTarget?.kind === "delete"
            ? tr("删除用户", "Delete user")
            : confirmTarget?.kind === "disable"
              ? tr("禁用用户", "Disable user")
              : confirmTarget?.kind === "enable"
                ? tr("启用用户", "Enable user")
            : confirmTarget?.kind === "promote"
              ? tr("提升为管理员", "Promote to admin")
              : confirmTarget?.kind === "revoke"
                ? tr("退出用户会话", "Sign out user")
              : tr("降级为用户", "Demote to user")
        }
        tone={
          confirmTarget?.kind === "delete" || confirmTarget?.kind === "disable"
            ? "danger"
            : "default"
        }
        confirmLabel={
          confirmTarget?.kind === "delete"
            ? tr("删除用户", "Delete user")
            : confirmTarget?.kind === "disable"
              ? tr("禁用", "Disable")
              : confirmTarget?.kind === "enable"
              ? tr("启用", "Enable")
            : confirmTarget?.kind === "promote"
              ? tr("提升", "Promote")
              : confirmTarget?.kind === "revoke"
                ? tr("退出登录", "Sign out")
              : tr("降级", "Demote")
        }
        cancelLabel={tr("取消", "Cancel")}
        busyLabel={
          confirmTarget?.kind === "delete"
            ? tr("删除中…", "Deleting…")
            : confirmTarget?.kind === "disable"
              ? tr("禁用中…", "Disabling…")
              : confirmTarget?.kind === "enable"
                ? tr("启用中…", "Enabling…")
            : confirmTarget?.kind === "promote"
              ? tr("提升中…", "Promoting…")
              : confirmTarget?.kind === "revoke"
                ? tr("退出中…", "Signing out…")
              : tr("降级中…", "Demoting…")
        }
        busy={confirmBusy}
        onConfirm={handleConfirmAction}
        onCancel={() => {
          setConfirmTarget(null);
          setDisableReason("");
        }}
      >
        {confirmTarget && (
          <>
            <div className="flex items-center gap-3 rounded-xl border border-[var(--border)] bg-[var(--background)]/50 px-3 py-2.5">
              <UserAvatar
                username={confirmTarget.user.username}
                userId={confirmTarget.user.id}
                avatar={confirmTarget.user.avatar}
                role={confirmTarget.user.role}
                size={32}
              />
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-[var(--foreground)]">
                  {confirmTarget.user.username}
                </p>
                <p className="text-xs text-[var(--muted-foreground)]">
                  {confirmTarget.user.role === "admin"
                    ? tr("管理员", "Admin")
                    : tr("用户", "User")}{" "}
                  · {tr("加入于", "joined")}{" "}
                  {formatDate(confirmTarget.user.created_at)}
                </p>
              </div>
            </div>
            <p className="mt-3">
              {confirmTarget.kind === "delete"
                ? tr(
                    "选择删除账号后如何处理该用户的工作区和授权。",
                    "Choose what happens to the user's workspace and assignments after removing the account.",
                  )
                : confirmTarget.kind === "disable"
                  ? tr(
                      "用户会在下一次请求时退出登录，并且禁用期间无法登录。",
                      "They will be signed out on their next request and cannot sign in while disabled.",
                    )
                  : confirmTarget.kind === "enable"
                  ? tr(
                      "用户可以继续使用当前密码登录。",
                      "They will be able to sign in again with their current password.",
                    )
                : confirmTarget.kind === "promote"
                  ? tr(
                      "管理员可以管理用户和授权，并使用共享主工作区。",
                      "Admins can manage users and assignments, and work in the shared main workspace.",
                    )
                  : confirmTarget.kind === "revoke"
                    ? tr(
                        "该用户现有浏览器会话和 bearer token 会在下一次请求时失效。",
                        "Their existing browser sessions and bearer tokens will stop working on the next request.",
                      )
                  : tr(
                      "该用户将失去管理后台访问权限，并切换到自己的授权工作区。",
                      "They will lose access to the admin area and switch to their own assigned workspace.",
                    )}
            </p>
            {confirmTarget.kind === "delete" && (
              <label className="mt-3 block text-xs text-[var(--muted-foreground)]">
                {tr("数据策略", "Data policy")}
                <select
                  value={deleteDataAction}
                  onChange={(e) =>
                    setDeleteDataAction(e.target.value as DeleteDataAction)
                  }
                  disabled={confirmBusy}
                  className="mt-1 w-full rounded-lg border border-[var(--border)] bg-transparent px-3 py-2 text-sm text-[var(--foreground)] outline-none focus:border-[var(--ring)]"
                >
                  <option value="keep">
                    {tr("保留工作区和授权", "Keep workspace and grants")}
                  </option>
                  <option value="archive">
                    {tr("归档工作区和授权", "Archive workspace and grants")}
                  </option>
                  <option value="delete">
                    {tr("删除工作区和授权", "Delete workspace and grants")}
                  </option>
                </select>
              </label>
            )}
            {confirmTarget.kind === "disable" && (
              <label className="mt-3 block text-xs text-[var(--muted-foreground)]">
                {tr("原因", "Reason")}
                <input
                  type="text"
                  value={disableReason}
                  onChange={(e) => setDisableReason(e.target.value)}
                  disabled={confirmBusy}
                  maxLength={500}
                  className="mt-1 w-full rounded-lg border border-[var(--border)] bg-transparent px-3 py-2 text-sm text-[var(--foreground)] outline-none focus:border-[var(--ring)]"
                />
              </label>
            )}
          </>
        )}
      </ConfirmDialog>

      {resetTarget && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-[var(--overlay)] px-4"
          role="dialog"
          aria-modal="true"
          onClick={() => {
            if (!resetSubmitting) setResetTarget(null);
          }}
        >
          <form
            onClick={(e) => e.stopPropagation()}
            onSubmit={handleResetSubmit}
            className="w-full max-w-sm rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5 shadow-xl"
          >
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-base font-semibold text-[var(--foreground)]">
                {tr("重置密码", "Reset password")}
              </h2>
              <button
                type="button"
                onClick={() => setResetTarget(null)}
                disabled={resetSubmitting}
                className="rounded-md p-1 text-[var(--muted-foreground)] hover:bg-[var(--background)] hover:text-[var(--foreground)] disabled:opacity-40"
                aria-label={tr("关闭", "Close")}
              >
                <X size={16} />
              </button>
            </div>

            <p className="mb-3 text-sm text-[var(--muted-foreground)]">
              {resetTarget.username}
            </p>

            <label className="mb-4 block text-xs text-[var(--muted-foreground)]">
              {tr("新密码（至少 8 个字符）", "New password (≥ 8 chars)")}
              <input
                type="password"
                value={resetPassword}
                onChange={(e) => setResetPassword(e.target.value)}
                disabled={resetSubmitting}
                autoComplete="new-password"
                autoFocus
                className="mt-1 w-full rounded-lg border border-[var(--border)] bg-transparent px-3 py-2 text-sm text-[var(--foreground)] outline-none focus:border-[var(--ring)]"
              />
            </label>

            {resetError && (
              <p className="mb-3 text-xs text-red-500">{resetError}</p>
            )}

            <div className="flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => setResetTarget(null)}
                disabled={resetSubmitting}
                className="rounded-lg px-3 py-1.5 text-sm text-[var(--muted-foreground)] hover:text-[var(--foreground)] disabled:opacity-40"
              >
                {tr("取消", "Cancel")}
              </button>
              <button
                type="submit"
                disabled={resetSubmitting}
                className="rounded-lg bg-[var(--foreground)] px-3 py-1.5 text-sm font-medium text-[var(--background)] hover:opacity-90 disabled:opacity-40"
              >
                {resetSubmitting
                  ? tr("重置中…", "Resetting…")
                  : tr("重置", "Reset")}
              </button>
            </div>
          </form>
        </div>
      )}

      {showAudit && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-[var(--overlay)] px-4"
          role="dialog"
          aria-modal="true"
          onClick={() => setShowAudit(false)}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="max-h-[80vh] w-full max-w-2xl overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--card)] shadow-xl"
          >
            <div className="flex items-center justify-between border-b border-[var(--border)] px-5 py-4">
              <h2 className="text-base font-semibold text-[var(--foreground)]">
                {tr("审计日志", "Audit log")}
              </h2>
              <button
                type="button"
                onClick={() => setShowAudit(false)}
                className="rounded-md p-1 text-[var(--muted-foreground)] hover:bg-[var(--background)] hover:text-[var(--foreground)]"
                aria-label={tr("关闭", "Close")}
              >
                <X size={16} />
              </button>
            </div>
            <div className="max-h-[60vh] overflow-y-auto px-5 py-4">
              {auditLoading ? (
                <p className="text-sm text-[var(--muted-foreground)]">
                  {tr("加载中…", "Loading…")}
                </p>
              ) : auditError ? (
                <p className="text-sm text-red-500">{auditError}</p>
              ) : auditEvents.length === 0 ? (
                <p className="text-sm text-[var(--muted-foreground)]">
                  {tr("暂无审计事件。", "No audit events yet.")}
                </p>
              ) : (
                <div className="space-y-2">
                  {auditEvents.map((event, index) => (
                    <div
                      key={`${event.time ?? index}-${event.action ?? "event"}`}
                      className="rounded-lg border border-[var(--border)] bg-[var(--background)]/40 px-3 py-2"
                    >
                      <div className="flex items-center justify-between gap-3">
                        <span className="truncate text-sm font-medium text-[var(--foreground)]">
                          {event.action ?? "audit_event"}
                        </span>
                        <span className="shrink-0 text-xs text-[var(--muted-foreground)]">
                          {event.time ? formatDate(event.time) : "—"}
                        </span>
                      </div>
                      <p className="mt-1 text-xs text-[var(--muted-foreground)]">
                        {event.actor_username ?? tr("系统", "system")}
                        {event.target_user_id
                          ? ` → ${event.target_user_id}`
                          : ""}
                      </p>
                      {event.summary && (
                        <pre className="mt-2 max-h-24 overflow-auto whitespace-pre-wrap break-words rounded bg-[var(--card)] px-2 py-1.5 text-[11px] text-[var(--muted-foreground)]">
                          {JSON.stringify(event.summary, null, 2)}
                        </pre>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {showCreateDialog && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-[var(--overlay)] px-4"
          role="dialog"
          aria-modal="true"
          onClick={closeCreateDialog}
        >
          <form
            onClick={(e) => e.stopPropagation()}
            onSubmit={handleCreateSubmit}
            className="w-full max-w-sm rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5 shadow-xl"
          >
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-base font-semibold text-[var(--foreground)]">
                {tr("添加用户", "Add user")}
              </h2>
              <button
                type="button"
                onClick={closeCreateDialog}
                disabled={createSubmitting}
                className="rounded-md p-1 text-[var(--muted-foreground)] hover:bg-[var(--background)] hover:text-[var(--foreground)] disabled:opacity-40"
                aria-label={tr("关闭", "Close")}
              >
                <X size={16} />
              </button>
            </div>

            <label className="mb-3 block text-xs text-[var(--muted-foreground)]">
              {tr("邮箱", "Email")}
              <input
                type="email"
                value={createUsername}
                onChange={(e) => setCreateUsername(e.target.value)}
                disabled={createSubmitting}
                autoComplete="email"
                autoFocus
                className="mt-1 w-full rounded-lg border border-[var(--border)] bg-transparent px-3 py-2 text-sm text-[var(--foreground)] outline-none focus:border-[var(--ring)]"
              />
            </label>

            <label className="mb-4 block text-xs text-[var(--muted-foreground)]">
              {tr("密码（至少 8 个字符）", "Password (≥ 8 chars)")}
              <input
                type="password"
                value={createPassword}
                onChange={(e) => setCreatePassword(e.target.value)}
                disabled={createSubmitting}
                autoComplete="new-password"
                className="mt-1 w-full rounded-lg border border-[var(--border)] bg-transparent px-3 py-2 text-sm text-[var(--foreground)] outline-none focus:border-[var(--ring)]"
              />
            </label>

            {createError && (
              <p className="mb-3 text-xs text-red-500">{createError}</p>
            )}

            <div className="flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={closeCreateDialog}
                disabled={createSubmitting}
                className="rounded-lg px-3 py-1.5 text-sm text-[var(--muted-foreground)] hover:text-[var(--foreground)] disabled:opacity-40"
              >
                {tr("取消", "Cancel")}
              </button>
              <button
                type="submit"
                disabled={createSubmitting}
                className="rounded-lg bg-[var(--foreground)] px-3 py-1.5 text-sm font-medium text-[var(--background)] hover:opacity-90 disabled:opacity-40"
              >
                {createSubmitting
                  ? tr("创建中…", "Creating…")
                  : tr("创建", "Create")}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
