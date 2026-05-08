"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { AUTH_ENABLED, fetchAuthStatus } from "@/lib/auth";

export default function AuthGate({ children }: { children: React.ReactNode }) {
  const { t } = useTranslation();
  const pathname = usePathname();
  const router = useRouter();
  const [loading, setLoading] = useState(AUTH_ENABLED);
  const [authenticated, setAuthenticated] = useState(!AUTH_ENABLED);

  useEffect(() => {
    if (!AUTH_ENABLED) return;

    let cancelled = false;
    fetchAuthStatus()
      .then((status) => {
        if (cancelled) return;
        const ok = Boolean(status?.authenticated);
        setAuthenticated(ok);
        if (!ok) {
          router.replace(`/login?next=${encodeURIComponent(pathname || "/")}`);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [pathname, router]);

  if (!AUTH_ENABLED) {
    return <>{children}</>;
  }

  if (loading || !authenticated) {
    return (
      <div className="flex h-screen items-center justify-center bg-[var(--background)] text-sm text-[var(--muted-foreground)]">
        {t("Loading...")}
      </div>
    );
  }

  return <>{children}</>;
}
