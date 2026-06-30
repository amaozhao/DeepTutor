import { Suspense } from "react";
import { Loader2 } from "lucide-react";

import KnowledgePage from "@/components/knowledge/KnowledgePage";

export default function KnowledgeCenterSettingsPage() {
  return (
    <div className="-mx-10 -mb-16 h-[calc(100vh-9rem)]">
      <Suspense
        fallback={
          <div className="flex h-full items-center justify-center text-[13px] text-[var(--muted-foreground)]">
            <Loader2 className="h-5 w-5 animate-spin" />
          </div>
        }
      >
        <KnowledgePage />
      </Suspense>
    </div>
  );
}
