"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createElement } from "react";
import {
  ArrowLeft,
  Download,
  ImageUp,
  LogOut,
  ShieldCheck,
  Trash2,
  Unplug,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { fetchAuthStatus, logout } from "@/lib/auth";
import {
  getProfile,
  changePassword,
  deleteMyAccount,
  downloadMyData,
  removeAvatarImage,
  revokeMySessions,
  setAvatarMarker,
  uploadAvatarImage,
  type ProfileInfo,
} from "@/lib/profile-api";
import type { DeleteDataAction } from "@/features/multi-user/types";
import {
  AVATAR_COLOR_NAMES,
  AVATAR_COLORS,
  AVATAR_ICON_NAMES,
  AVATAR_ICONS,
  fallbackAvatarFor,
  UserAvatar,
} from "@/components/UserAvatar";
import { parseAvatarMarker } from "@/lib/avatar";
import { formatDate, type Language } from "@/lib/datetime";

const AVATAR_OUTPUT_SIZE = 256;
// Decoding a huge photo just to throw away most pixels wastes memory; the
// server enforces its own 1 MB cap on the (much smaller) cropped result.
const MAX_SOURCE_BYTES = 20 * 1024 * 1024;

/** Center-crop to a square and downscale; canvas re-encode also strips EXIF. */
async function cropToSquareBlob(file: File): Promise<Blob> {
  let source: CanvasImageSource;
  let width: number;
  let height: number;
  try {
    const bitmap = await createImageBitmap(file, {
      imageOrientation: "from-image",
    });
    source = bitmap;
    width = bitmap.width;
    height = bitmap.height;
  } catch {
    // Older Safari: fall back to decoding via an <img> element.
    const url = URL.createObjectURL(file);
    try {
      const image = await new Promise<HTMLImageElement>((resolve, reject) => {
        const el = new Image();
        el.onload = () => resolve(el);
        el.onerror = () => reject(new Error("Could not decode image"));
        el.src = url;
      });
      source = image;
      width = image.naturalWidth;
      height = image.naturalHeight;
    } finally {
      URL.revokeObjectURL(url);
    }
  }
  if (!width || !height) throw new Error("Could not decode image");

  const side = Math.min(width, height);
  const canvas = document.createElement("canvas");
  canvas.width = AVATAR_OUTPUT_SIZE;
  canvas.height = AVATAR_OUTPUT_SIZE;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("Could not decode image");
  ctx.drawImage(
    source,
    (width - side) / 2,
    (height - side) / 2,
    side,
    side,
    0,
    0,
    AVATAR_OUTPUT_SIZE,
    AVATAR_OUTPUT_SIZE,
  );
  // Release the decoder/GPU memory now instead of waiting for GC.
  if (typeof ImageBitmap !== "undefined" && source instanceof ImageBitmap) {
    source.close();
  }

  const toBlob = (type: string, quality?: number) =>
    new Promise<Blob | null>((resolve) =>
      canvas.toBlob(resolve, type, quality),
    );
  // WebP keeps avatars tiny; browsers without a WebP encoder return null.
  const blob =
    (await toBlob("image/webp", 0.85)) ?? (await toBlob("image/png"));
  if (!blob) throw new Error("Could not encode image");
  return blob;
}

export default function ProfilePage() {
  const router = useRouter();
  const inSettings = (usePathname() ?? "").startsWith("/settings/");
  const { t, i18n } = useTranslation();
  const [profile, setProfile] = useState<ProfileInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [passwordBusy, setPasswordBusy] = useState(false);
  const [exportBusy, setExportBusy] = useState(false);
  const [accountBusy, setAccountBusy] = useState(false);
  const [sessionBusy, setSessionBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [passwordMessage, setPasswordMessage] = useState<string | null>(null);
  const [accountMessage, setAccountMessage] = useState<string | null>(null);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deletePassword, setDeletePassword] = useState("");
  const [deleteDataAction, setDeleteDataAction] =
    useState<DeleteDataAction>("keep");
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const status = await fetchAuthStatus();
      if (cancelled) return;
      if (!status?.enabled) {
        router.replace("/");
        return;
      }
      if (!status.authenticated) {
        router.replace("/login");
        return;
      }
      try {
        const info = await getProfile();
        if (!cancelled) setProfile(info);
      } catch {
        if (!cancelled) setError(t("Failed to load profile"));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [router, t]);

  const applyMarker = useCallback(async (marker: string) => {
    setBusy(true);
    setError(null);
    try {
      const saved = await setAvatarMarker(marker);
      setProfile((prev) => (prev ? { ...prev, avatar: saved } : prev));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }, []);

  const handleUpload = useCallback(
    async (file: File) => {
      setBusy(true);
      setError(null);
      try {
        if (file.size > MAX_SOURCE_BYTES) {
          throw new Error(t("Image is too large"));
        }
        const blob = await cropToSquareBlob(file);
        const marker = await uploadAvatarImage(blob);
        setProfile((prev) => (prev ? { ...prev, avatar: marker } : prev));
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setBusy(false);
        if (fileInputRef.current) fileInputRef.current.value = "";
      }
    },
    [t],
  );

  const handleRemoveImage = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      await removeAvatarImage();
      setProfile((prev) => (prev ? { ...prev, avatar: "" } : prev));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }, []);

  const handleSignOut = useCallback(async () => {
    await logout();
    router.replace("/login");
  }, [router]);

  const handleRevokeSessions = useCallback(async () => {
    setSessionBusy(true);
    setError(null);
    try {
      await revokeMySessions();
      router.replace("/login");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setSessionBusy(false);
    }
  }, [router]);

  const handlePasswordSubmit = useCallback(
    async (event: FormEvent) => {
      event.preventDefault();
      setPasswordMessage(null);
      if (newPassword !== confirmPassword) {
        setPasswordMessage(t("Passwords do not match"));
        return;
      }
      setPasswordBusy(true);
      try {
        await changePassword(currentPassword, newPassword);
        setCurrentPassword("");
        setNewPassword("");
        setConfirmPassword("");
        setPasswordMessage(t("Password updated. Please sign in again."));
      } catch (err) {
        setPasswordMessage(err instanceof Error ? err.message : String(err));
      } finally {
        setPasswordBusy(false);
      }
    },
    [confirmPassword, currentPassword, newPassword, t],
  );

  const handleDataExport = useCallback(async () => {
    setExportBusy(true);
    setError(null);
    try {
      await downloadMyData();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setExportBusy(false);
    }
  }, []);

  const handleDeleteAccount = useCallback(
    async (event: FormEvent) => {
      event.preventDefault();
      setAccountMessage(null);
      if (!deletePassword) {
        setAccountMessage(t("Please enter your current password"));
        return;
      }
      setAccountBusy(true);
      try {
        await deleteMyAccount(deletePassword, deleteDataAction);
        setDeletePassword("");
        router.replace("/login");
      } catch (err) {
        setAccountMessage(err instanceof Error ? err.message : String(err));
      } finally {
        setAccountBusy(false);
      }
    },
    [deleteDataAction, deletePassword, router, t],
  );

  const descriptor = parseAvatarMarker(profile?.avatar);
  const hasImage = descriptor.kind === "image";
  const fallback = fallbackAvatarFor(profile?.username ?? "");
  const selectedIcon =
    descriptor.kind === "icon"
      ? descriptor.icon
      : hasImage
        ? null
        : fallback.icon;
  const selectedColor =
    descriptor.kind === "icon"
      ? descriptor.color
      : hasImage
        ? null
        : fallback.color;
  const isAdmin = profile?.role === "admin";
  const lang: Language = i18n.language?.startsWith("zh") ? "zh" : "en";
  const joinedDate = profile?.created_at ? new Date(profile.created_at) : null;
  const joined =
    joinedDate && !Number.isNaN(joinedDate.getTime())
      ? formatDate(joinedDate, lang)
      : null;

  return (
    <div
      className={
        inSettings
          ? ""
          : "h-screen overflow-y-auto bg-[var(--background)] px-4 py-10 [scrollbar-gutter:stable]"
      }
    >
      <div className={inSettings ? "max-w-2xl" : "mx-auto max-w-2xl"}>
        {/* Header */}
        <div className="mb-8">
          {!inSettings && (
            <Link
              href="/settings"
              className="mb-4 inline-flex items-center gap-1.5 text-sm text-[var(--muted-foreground)] hover:text-[var(--foreground)] transition-colors"
            >
              <ArrowLeft size={16} />
              {t("Back")}
            </Link>
          )}
          <div>
            <h1 className="text-xl font-semibold text-[var(--foreground)]">
              {t("My profile")}
            </h1>
            <p className="mt-0.5 text-sm text-[var(--muted-foreground)]">
              {t("View your account and personalize your avatar")}
            </p>
          </div>
        </div>

        {error && (
          <div className="mb-4 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-600 dark:text-red-400">
            {error}
          </div>
        )}

        {loading ? (
          <div className="flex items-center justify-center rounded-2xl border border-[var(--border)] bg-[var(--card)] py-16 text-sm text-[var(--muted-foreground)] shadow-sm">
            {t("Loading…")}
          </div>
        ) : !profile ? null : (
          <>
            {/* Account card */}
            <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-6 shadow-sm">
              <div className="flex items-center gap-5">
                <UserAvatar
                  username={profile.username}
                  userId={profile.id}
                  avatar={profile.avatar}
                  role={profile.role}
                  size={72}
                />
                <div className="min-w-0">
                  <div className="flex items-center gap-2.5">
                    <span className="truncate text-lg font-semibold text-[var(--foreground)]">
                      {profile.username}
                    </span>
                    <span
                      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ${
                        isAdmin
                          ? "bg-amber-500/15 text-amber-600 dark:text-amber-400"
                          : "bg-[var(--muted)]/70 text-[var(--muted-foreground)]"
                      }`}
                    >
                      {isAdmin && <ShieldCheck size={11} strokeWidth={2} />}
                      {isAdmin ? t("Administrator") : t("User")}
                    </span>
                  </div>
                  {joined && (
                    <p className="mt-1 text-sm text-[var(--muted-foreground)]">
                      {t("Joined")}: {joined}
                    </p>
                  )}
                </div>
              </div>
            </div>

            {/* Avatar card */}
            <div className="mt-4 rounded-2xl border border-[var(--border)] bg-[var(--card)] p-6 shadow-sm">
              <h2 className="text-sm font-semibold text-[var(--foreground)]">
                {t("Avatar")}
              </h2>
              <p className="mt-0.5 text-sm text-[var(--muted-foreground)]">
                {t("Upload a picture or pick an icon")}
              </p>

              <div className="mt-4 flex flex-wrap items-center gap-2.5">
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/png,image/jpeg,image/webp"
                  className="hidden"
                  onChange={(event) => {
                    const file = event.target.files?.[0];
                    if (file) void handleUpload(file);
                  }}
                />
                <button
                  onClick={() => fileInputRef.current?.click()}
                  disabled={busy}
                  className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm
                             border border-[var(--border)] text-[var(--foreground)]
                             hover:bg-[var(--background)]/60 disabled:opacity-50 transition-colors"
                >
                  <ImageUp size={14} />
                  {t("Upload image")}
                </button>
                {hasImage && (
                  <button
                    onClick={() => void handleRemoveImage()}
                    disabled={busy}
                    className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm
                               border border-[var(--border)] text-[var(--muted-foreground)]
                               hover:text-red-500 disabled:opacity-50 transition-colors"
                  >
                    <Trash2 size={14} />
                    {t("Remove photo")}
                  </button>
                )}
              </div>

              {/* Icon grid */}
              <div className="mt-5">
                <p className="mb-2 text-xs font-medium uppercase tracking-wider text-[var(--muted-foreground)]">
                  {t("Or pick an icon")}
                </p>
                <div className="flex flex-wrap gap-2">
                  {AVATAR_ICON_NAMES.map((name) => {
                    const active = !hasImage && name === selectedIcon;
                    const color = selectedColor ?? fallback.color;
                    return (
                      <button
                        key={name}
                        onClick={() =>
                          void applyMarker(`icon:${name}:${color}`)
                        }
                        disabled={busy}
                        aria-label={name}
                        aria-pressed={active}
                        className={`flex h-10 w-10 items-center justify-center rounded-full text-white transition-all disabled:opacity-50 ${
                          active
                            ? "ring-2 ring-[var(--foreground)] ring-offset-2 ring-offset-[var(--card)]"
                            : "opacity-75 hover:opacity-100"
                        }`}
                        style={{ backgroundColor: AVATAR_COLORS[color] }}
                      >
                        {createElement(AVATAR_ICONS[name], {
                          size: 18,
                          strokeWidth: 1.8,
                        })}
                      </button>
                    );
                  })}
                </div>
                <p className="mb-2 mt-4 text-xs font-medium uppercase tracking-wider text-[var(--muted-foreground)]">
                  {t("Color")}
                </p>
                <div className="flex flex-wrap gap-2">
                  {AVATAR_COLOR_NAMES.map((name) => {
                    const active = !hasImage && name === selectedColor;
                    const icon = selectedIcon ?? fallback.icon;
                    return (
                      <button
                        key={name}
                        onClick={() => void applyMarker(`icon:${icon}:${name}`)}
                        disabled={busy}
                        aria-label={name}
                        aria-pressed={active}
                        className={`h-7 w-7 rounded-full transition-all disabled:opacity-50 ${
                          active
                            ? "ring-2 ring-[var(--foreground)] ring-offset-2 ring-offset-[var(--card)]"
                            : "opacity-75 hover:opacity-100"
                        }`}
                        style={{ backgroundColor: AVATAR_COLORS[name] }}
                      />
                    );
                  })}
                </div>
              </div>
            </div>

            {/* Password card */}
            <form
              onSubmit={handlePasswordSubmit}
              className="mt-4 rounded-2xl border border-[var(--border)] bg-[var(--card)] p-6 shadow-sm"
            >
              <h2 className="text-sm font-semibold text-[var(--foreground)]">
                {t("Password")}
              </h2>
              <div className="mt-4 grid gap-3 sm:grid-cols-3">
                <input
                  type="password"
                  value={currentPassword}
                  onChange={(e) => setCurrentPassword(e.target.value)}
                  placeholder={t("Current password")}
                  autoComplete="current-password"
                  className="rounded-lg border border-[var(--border)] bg-transparent px-3 py-2 text-sm text-[var(--foreground)] outline-none focus:border-[var(--ring)]"
                />
                <input
                  type="password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  placeholder={t("New password")}
                  autoComplete="new-password"
                  className="rounded-lg border border-[var(--border)] bg-transparent px-3 py-2 text-sm text-[var(--foreground)] outline-none focus:border-[var(--ring)]"
                />
                <input
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder={t("Confirm password")}
                  autoComplete="new-password"
                  className="rounded-lg border border-[var(--border)] bg-transparent px-3 py-2 text-sm text-[var(--foreground)] outline-none focus:border-[var(--ring)]"
                />
              </div>
              {passwordMessage && (
                <p className="mt-3 text-sm text-[var(--muted-foreground)]">
                  {passwordMessage}
                </p>
              )}
              <button
                type="submit"
                disabled={passwordBusy}
                className="mt-4 rounded-lg border border-[var(--border)] px-3 py-1.5 text-sm text-[var(--foreground)] hover:bg-[var(--background)]/60 disabled:opacity-50"
              >
                {passwordBusy ? t("Saving…") : t("Change password")}
              </button>
            </form>

            {!isAdmin && (
              <>
                {/* Data export card */}
                <div className="mt-4 flex flex-col gap-4 rounded-2xl border border-[var(--border)] bg-[var(--card)] p-6 shadow-sm sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <h2 className="text-sm font-semibold text-[var(--foreground)]">
                      {t("Account data")}
                    </h2>
                    <p className="mt-0.5 text-sm text-[var(--muted-foreground)]">
                      {t(
                        "Download a copy of your workspace and account records",
                      )}
                    </p>
                  </div>
                  <button
                    onClick={() => void handleDataExport()}
                    disabled={exportBusy}
                    className="flex items-center justify-center gap-1.5 rounded-lg border border-[var(--border)] px-3 py-1.5 text-sm text-[var(--foreground)] hover:bg-[var(--background)]/60 disabled:opacity-50"
                  >
                    <Download size={14} />
                    {exportBusy ? t("Exporting…") : t("Download data")}
                  </button>
                </div>

                {/* Account deletion card */}
                <div className="mt-4 rounded-2xl border border-red-500/30 bg-[var(--card)] p-6 shadow-sm">
                  <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                      <h2 className="text-sm font-semibold text-red-600 dark:text-red-400">
                        {t("Delete account")}
                      </h2>
                      <p className="mt-0.5 text-sm text-[var(--muted-foreground)]">
                        {t(
                          "Delete your account after confirming your current password",
                        )}
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => {
                        setDeleteOpen((value) => !value);
                        setAccountMessage(null);
                      }}
                      className="flex items-center justify-center gap-1.5 rounded-lg border border-red-500/40 px-3 py-1.5 text-sm text-red-600 transition-colors hover:bg-red-500/10 dark:text-red-400"
                    >
                      <Trash2 size={14} />
                      {deleteOpen ? t("Cancel") : t("Delete account")}
                    </button>
                  </div>

                  {deleteOpen && (
                    <form
                      onSubmit={handleDeleteAccount}
                      className="mt-4 grid gap-3 border-t border-red-500/20 pt-4 sm:grid-cols-[1fr_1fr_auto]"
                    >
                      <input
                        type="password"
                        value={deletePassword}
                        onChange={(e) => setDeletePassword(e.target.value)}
                        placeholder={t("Current password")}
                        autoComplete="current-password"
                        className="rounded-lg border border-[var(--border)] bg-transparent px-3 py-2 text-sm text-[var(--foreground)] outline-none focus:border-[var(--ring)]"
                      />
                      <select
                        value={deleteDataAction}
                        onChange={(e) =>
                          setDeleteDataAction(
                            e.target.value as DeleteDataAction,
                          )
                        }
                        className="rounded-lg border border-[var(--border)] bg-[var(--card)] px-3 py-2 text-sm text-[var(--foreground)] outline-none focus:border-[var(--ring)]"
                      >
                        <option value="keep">{t("Keep workspace data")}</option>
                        <option value="archive">
                          {t("Archive workspace data")}
                        </option>
                        <option value="delete">
                          {t("Delete workspace data")}
                        </option>
                      </select>
                      <button
                        type="submit"
                        disabled={accountBusy}
                        className="rounded-lg border border-red-500/40 px-3 py-2 text-sm text-red-600 transition-colors hover:bg-red-500/10 disabled:opacity-50 dark:text-red-400"
                      >
                        {accountBusy ? t("Deleting…") : t("Delete now")}
                      </button>
                      {accountMessage && (
                        <p className="text-sm text-[var(--muted-foreground)] sm:col-span-3">
                          {accountMessage}
                        </p>
                      )}
                    </form>
                  )}
                </div>
              </>
            )}

            {/* Sign out card */}
            <div className="mt-4 rounded-2xl border border-[var(--border)] bg-[var(--card)] p-6 shadow-sm">
              <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <h2 className="text-sm font-semibold text-[var(--foreground)]">
                    {t("Sessions")}
                  </h2>
                  <p className="mt-0.5 text-sm text-[var(--muted-foreground)]">
                    {t("Manage browser sessions for this account")}
                  </p>
                </div>
                <div className="flex flex-col gap-2 sm:flex-row">
                  <button
                    onClick={() => void handleRevokeSessions()}
                    disabled={sessionBusy}
                    className="flex items-center justify-center gap-1.5 rounded-lg border border-[var(--border)] px-3 py-1.5 text-sm text-[var(--foreground)] transition-colors hover:bg-[var(--background)]/60 disabled:opacity-50"
                  >
                    <Unplug size={14} />
                    {sessionBusy ? t("Revoking…") : t("Sign out everywhere")}
                  </button>
                  <button
                    onClick={() => void handleSignOut()}
                    className="flex items-center justify-center gap-1.5 rounded-lg px-3 py-1.5 text-sm
                               border border-red-500/40 text-red-600 dark:text-red-400
                               hover:bg-red-500/10 transition-colors"
                  >
                    <LogOut size={14} />
                    {t("Sign out")}
                  </button>
                </div>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
