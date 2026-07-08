export type Layer = "L2" | "L3";

export type Surface =
  | "chat"
  | "notebook"
  | "quiz"
  | "kb"
  | "book"
  | "partner"
  | "cowriter";

export const SURFACES: readonly Surface[] = [
  "chat",
  "notebook",
  "quiz",
  "kb",
  "book",
  "partner",
  "cowriter",
] as const;

export type Tab = "L1" | "L2" | "L3";

export interface Entity {
  id: string;
  label: string;
  ts: string;
  content: string;
  metadata: Record<string, unknown>;
  fingerprint: string;
}

export interface SnapshotResponse {
  surface: Surface;
  entities: Entity[];
  last_refresh: string | null;
  pending_changes: ChangeEntryDTO[];
}

export interface ChangeEntryDTO {
  ts: string;
  kind: "added" | "modified" | "removed";
  entity_id: string;
  label: string;
  prev_fingerprint: string | null;
  new_fingerprint: string | null;
}

export interface ChangesResponse {
  surface: Surface;
  changes: ChangeEntryDTO[];
}

export interface KbQueryDTO {
  id: string;
  ts: string;
  surface: Surface;
  kind: string;
  payload: Record<string, unknown>;
  session_id: string | null;
  turn_id: string | null;
}

export interface KbQueriesResponse {
  surface: Surface;
  events: KbQueryDTO[];
}

export interface DocOverview {
  layer: Layer;
  key: string;
  exists: boolean;
  updated_at: string | null;
  entry_count: number;
  backlog: number;
}

export interface OverviewResponse {
  docs: DocOverview[];
  backups: string[];
}

export interface StreamStage {
  stage: string;
  count?: number;
  delta?: string;
  ops?: unknown[];
  report?: { accepted: boolean; reason?: string; results?: unknown[] };
  message?: string;
  turn?: number;
  name?: string;
  args?: Record<string, unknown>;
  brief?: string;
  action?: string;
  turns_used?: number;
  tools_used?: Record<string, number>;
  ops_emitted?: number;
  summary?: string;
}

export const SURFACE_LABELS: Record<Surface, string> = {
  chat: "Chat",
  notebook: "Notebook",
  quiz: "\u9898\u5e93",
  kb: "Knowledge base",
  book: "Book",
  partner: "Partner",
  cowriter: "Co-writer",
};

export const L3_LABELS: Record<string, string> = {
  recent: "\u8fd1\u671f\u603b\u7ed3",
  profile: "\u7528\u6237\u753b\u50cf",
  scope: "\u77e5\u8bc6 Scope",
  preferences: "\u504f\u597d",
};

const ENTITY_REF_RE =
  /\b(chat|notebook|quiz|kb|book|partner|cowriter):[A-Za-z0-9_.\-:]+/g;

export function entityAnchorId(ref: string): string {
  return `entity-${ref.replace(/:/g, "__")}`;
}

export function parseEntityAnchor(anchor: string): {
  surface: Surface;
  ref: string;
} | null {
  if (!anchor.startsWith("entity-")) return null;
  const body = anchor.slice("entity-".length);
  const sep = body.indexOf("__");
  if (sep <= 0) return null;
  const surface = body.slice(0, sep);
  const rest = body.slice(sep + 2).replace(/__/g, ":");
  if (!(SURFACES as readonly string[]).includes(surface)) return null;
  return { surface: surface as Surface, ref: `${surface}:${rest}` };
}

export function linkifyEntityRefs(content: string): string {
  return content.replace(
    ENTITY_REF_RE,
    (ref) => `[${ref}](#${entityAnchorId(ref)})`,
  );
}

export function labelFor(doc: Pick<DocOverview, "layer" | "key">): string {
  if (doc.layer === "L2")
    return SURFACE_LABELS[doc.key as Surface] ?? doc.key;
  return L3_LABELS[doc.key] ?? doc.key;
}

export function formatTimestamp(value: string | null, fallback: string): string {
  if (!value) return fallback;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString();
}

export function shorten(s: string, n: number): string {
  const trimmed = (s || "").replace(/\s+/g, " ").trim();
  return trimmed.length > n ? `${trimmed.slice(0, n - 1)}\u2026` : trimmed;
}

export function asString(v: unknown): string {
  if (typeof v === "string") return v;
  if (typeof v === "number") return String(v);
  return "";
}

export function entityDeepLinkUrl(surface: Surface, ent: Entity): string | null {
  const m = ent.metadata || {};
  switch (surface) {
    case "chat":
      return `/home/${encodeURIComponent(ent.id)}`;
    case "cowriter":
      return `/co-writer/${encodeURIComponent(ent.id)}`;
    case "notebook": {
      const nbId = asString(m.notebook_id);
      return nbId
        ? `/space/notebooks?notebook=${encodeURIComponent(nbId)}`
        : "/space/notebooks";
    }
    case "book":
      return `/book?book=${encodeURIComponent(ent.id)}`;
    case "partner": {
      const partnerId = asString(m.partner_id) || ent.id.split(":")[0];
      return partnerId
        ? `/partners/${encodeURIComponent(partnerId)}`
        : "/partners";
    }
    case "quiz": {
      const sessionId = asString(m.session_id) || ent.id.split(":")[0];
      return sessionId
        ? `/?session=${encodeURIComponent(sessionId)}`
        : "/space/questions";
    }
    case "kb":
      return `/knowledge?kb=${encodeURIComponent(ent.id)}`;
  }
  return null;
}
