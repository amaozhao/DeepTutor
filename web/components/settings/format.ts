export function defaultModelLabel(language: "en" | "zh", index: number): string {
  const safeIndex = index > 0 ? index : 1;
  return language === "zh" ? `\u6a21\u578b${safeIndex}` : `Model ${safeIndex}`;
}

export function formatCompactTokens(value: string | number | undefined): string {
  if (value === undefined || value === "") return "";
  const parsed =
    typeof value === "number"
      ? value
      : Number.parseInt(String(value).replace(/[^\d]/g, ""), 10);
  if (!Number.isFinite(parsed) || parsed <= 0) return "";
  if (parsed >= 1_000_000) {
    const m = parsed / 1_000_000;
    return `${m >= 10 ? m.toFixed(0) : m.toFixed(1).replace(/\.0$/, "")}M`;
  }
  if (parsed >= 1_000) {
    const k = parsed / 1_000;
    return `${k >= 10 ? k.toFixed(0) : k.toFixed(1).replace(/\.0$/, "")}K`;
  }
  return String(parsed);
}

export function formatVoiceBadge(value: string | undefined): string {
  const voice = (value || "").trim();
  if (!voice) return "";
  const tail = voice.includes(":")
    ? voice.slice(voice.lastIndexOf(":") + 1)
    : voice;
  return tail.length > 14 ? `${tail.slice(0, 13)}\u2026` : tail;
}

export function formatDimensionBadge(
  value: string | number | undefined,
): string {
  if (value === undefined || value === "") return "";
  const parsed =
    typeof value === "number"
      ? value
      : Number.parseInt(String(value).replace(/[^\d]/g, ""), 10);
  if (!Number.isFinite(parsed) || parsed <= 0) return "";
  return `${parsed}d`;
}

export function formatIsoLocal(value: string | undefined): string {
  if (!value) return "";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  const pad = (n: number) => String(n).padStart(2, "0");
  return (
    `${parsed.getFullYear()}-${pad(parsed.getMonth() + 1)}-${pad(parsed.getDate())} ` +
    `${pad(parsed.getHours())}:${pad(parsed.getMinutes())}`
  );
}
