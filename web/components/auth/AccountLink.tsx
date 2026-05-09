"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { UserCircle } from "lucide-react";
import { useTranslation } from "react-i18next";
import { fetchAuthStatus, type AuthStatus } from "@/lib/auth";

interface AccountLinkProps {
  collapsed?: boolean;
}

export function AccountLink({ collapsed = false }: AccountLinkProps) {
  const pathname = usePathname();
  const { t } = useTranslation();
  const [status, setStatus] = useState<AuthStatus | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchAuthStatus().then((nextStatus) => {
      if (!cancelled) setStatus(nextStatus);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const active = pathname.startsWith("/account");
  const username = status?.username || t("Account");
  const role = status?.role || "";
  const title = role ? `${username} · ${role}` : username;

  if (collapsed) {
    return (
      <Link
        href="/account"
        className={`rounded-lg p-2 transition-colors ${
          active
            ? "bg-[var(--primary)]/10 text-[var(--primary)]"
            : "text-[var(--muted-foreground)] hover:bg-[var(--background)]/50 hover:text-[var(--foreground)]"
        }`}
        aria-label={t("Account")}
        title={title}
      >
        <UserCircle size={16} strokeWidth={1.5} />
      </Link>
    );
  }

  return (
    <Link
      href="/account"
      className={`flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-[13.5px] transition-colors ${
        active
          ? "bg-[var(--primary)]/10 text-[var(--primary)]"
          : "text-[var(--muted-foreground)] hover:bg-[var(--background)]/50 hover:text-[var(--foreground)]"
      }`}
      title={title}
    >
      <UserCircle size={16} strokeWidth={1.5} />
      <span className="min-w-0 flex-1 truncate">{username}</span>
      {role && (
        <span className="shrink-0 rounded-full bg-[var(--background)]/70 px-1.5 py-0.5 text-[10px] uppercase text-[var(--muted-foreground)]">
          {role}
        </span>
      )}
    </Link>
  );
}
