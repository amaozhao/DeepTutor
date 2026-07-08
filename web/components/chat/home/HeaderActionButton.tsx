"use client";

import type { LucideIcon } from "lucide-react";

import Tooltip from "@/components/common/Tooltip";

export default function HeaderActionButton({
  onClick,
  disabled,
  active,
  icon: Icon,
  label,
  title,
}: {
  onClick: () => void;
  disabled?: boolean;
  active?: boolean;
  icon: LucideIcon;
  label: string;
  title?: string;
}) {
  return (
    <Tooltip label={title ?? label} side="bottom">
      <button
        onClick={onClick}
        disabled={disabled}
        aria-label={label}
        aria-pressed={active}
        className={`inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg transition-[background-color,color,transform] duration-150 active:scale-90 disabled:cursor-not-allowed disabled:opacity-40 ${
          active
            ? "bg-[var(--primary)]/10 text-[var(--primary)]"
            : "text-[var(--muted-foreground)] hover:bg-[var(--muted)]/55 hover:text-[var(--foreground)] disabled:hover:bg-transparent disabled:hover:text-[var(--muted-foreground)]"
        }`}
      >
        <Icon size={16} strokeWidth={1.7} className="shrink-0" />
      </button>
    </Tooltip>
  );
}
