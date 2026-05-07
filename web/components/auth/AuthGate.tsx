"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "@/context/AuthContext";

export default function AuthGate({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const { t } = useTranslation();
  const pathname = usePathname();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) {
      router.replace(`/login?next=${encodeURIComponent(pathname || "/")}`);
    }
  }, [loading, pathname, router, user]);

  if (loading || !user) {
    return (
      <div className="flex h-screen items-center justify-center bg-[var(--background)] text-sm text-[var(--muted-foreground)]">
        {t("Loading...")}
      </div>
    );
  }

  return <>{children}</>;
}
