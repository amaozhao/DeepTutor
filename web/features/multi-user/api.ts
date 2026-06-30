import { apiFetch, apiUrl } from "@/lib/api";
import type {
  AuditEvent,
  GrantPayload,
  MultiUserResources,
  UserUsageResponse,
} from "./types";
import { filenameFromContentDisposition } from "./download";

async function readError(res: Response, fallback: string): Promise<string> {
  try {
    const data = await res.json();
    return String(data?.detail || fallback);
  } catch {
    return fallback;
  }
}

export async function fetchAdminResources(): Promise<MultiUserResources> {
  const res = await apiFetch(apiUrl("/api/v1/multi-user/admin/resources"));
  if (!res.ok)
    throw new Error(
      await readError(res, "Failed to load assignable resources"),
    );
  return (await res.json()) as MultiUserResources;
}

export async function fetchUserGrant(userId: string): Promise<GrantPayload> {
  const res = await apiFetch(
    apiUrl(`/api/v1/multi-user/users/${encodeURIComponent(userId)}/grants`),
  );
  if (!res.ok)
    throw new Error(await readError(res, "Failed to load user grant"));
  const data = await res.json();
  return data.grant as GrantPayload;
}

export async function saveUserGrant(
  userId: string,
  grant: GrantPayload,
): Promise<GrantPayload> {
  const res = await apiFetch(
    apiUrl(`/api/v1/multi-user/users/${encodeURIComponent(userId)}/grants`),
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ grant }),
    },
  );
  if (!res.ok)
    throw new Error(await readError(res, "Failed to save user grant"));
  const data = await res.json();
  return data.grant as GrantPayload;
}

export async function fetchUserUsage(
  userId: string,
): Promise<UserUsageResponse> {
  const res = await apiFetch(
    apiUrl(`/api/v1/multi-user/users/${encodeURIComponent(userId)}/usage`),
  );
  if (!res.ok)
    throw new Error(await readError(res, "Failed to load user usage"));
  return (await res.json()) as UserUsageResponse;
}

export async function fetchAdminAuditEvents(limit = 50): Promise<AuditEvent[]> {
  const res = await apiFetch(
    apiUrl(`/api/v1/multi-user/admin/audit?limit=${limit}`),
  );
  if (!res.ok)
    throw new Error(await readError(res, "Failed to load audit events"));
  const data = await res.json();
  return (data.events ?? []) as AuditEvent[];
}

export async function downloadUserExport(userId: string): Promise<void> {
  const res = await apiFetch(
    apiUrl(`/api/v1/multi-user/users/${encodeURIComponent(userId)}/export`),
  );
  if (!res.ok)
    throw new Error(await readError(res, "Failed to export user data"));
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filenameFromContentDisposition(
    res.headers.get("content-disposition"),
    `deeptutor-user-${userId}.zip`,
  );
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
