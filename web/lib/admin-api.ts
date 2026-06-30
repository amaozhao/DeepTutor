import { apiFetch, apiUrl } from "@/lib/api";
import type { DeleteDataAction } from "@/features/multi-user/types";
import { filenameFromContentDisposition } from "@/features/multi-user/download";

export interface UserRecord {
  id: string;
  username: string;
  role: "admin" | "user";
  created_at: string;
  disabled?: boolean;
  disabled_reason?: string;
  /** Avatar marker: "", "icon:<name>:<color>", or "img:<version>". */
  avatar?: string;
}

export async function listUsers(): Promise<UserRecord[]> {
  const res = await apiFetch(apiUrl("/api/v1/auth/users"));
  if (!res.ok) throw new Error("Failed to fetch users");
  return res.json();
}

export async function downloadUsersCsv(): Promise<void> {
  const res = await apiFetch(apiUrl("/api/v1/auth/users/export.csv"));
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail ?? "Failed to export users");
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filenameFromContentDisposition(
    res.headers.get("content-disposition"),
    "deeptutor-users.csv",
  );
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export interface UserImportResult {
  ok: boolean;
  created: number;
  usernames: string[];
}

export async function importUsersCsv(file: File): Promise<UserImportResult> {
  const formData = new FormData();
  formData.append("file", file);
  const res = await apiFetch(apiUrl("/api/v1/auth/users/import.csv"), {
    method: "POST",
    body: formData,
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail ?? "Failed to import users");
  }
  return (await res.json()) as UserImportResult;
}

export async function deleteUser(
  username: string,
  dataAction: DeleteDataAction = "keep",
): Promise<void> {
  const res = await apiFetch(
    apiUrl(
      `/api/v1/auth/users/${encodeURIComponent(username)}?data_action=${dataAction}`,
    ),
    {
      method: "DELETE",
    },
  );
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail ?? "Failed to delete user");
  }
}

export async function setUserRole(
  username: string,
  role: "admin" | "user",
): Promise<void> {
  const res = await apiFetch(
    apiUrl(`/api/v1/auth/users/${encodeURIComponent(username)}/role`),
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role }),
    },
  );
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail ?? "Failed to update role");
  }
}

export async function setUserDisabled(
  username: string,
  disabled: boolean,
  reason = "",
): Promise<void> {
  const res = await apiFetch(
    apiUrl(`/api/v1/auth/users/${encodeURIComponent(username)}/disabled`),
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ disabled, reason }),
    },
  );
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail ?? "Failed to update user status");
  }
}

export async function resetUserPassword(
  username: string,
  password: string,
): Promise<void> {
  const res = await apiFetch(
    apiUrl(`/api/v1/auth/users/${encodeURIComponent(username)}/password`),
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password }),
    },
  );
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail ?? "Failed to reset password");
  }
}

export async function revokeUserSessions(username: string): Promise<void> {
  const res = await apiFetch(
    apiUrl(`/api/v1/auth/users/${encodeURIComponent(username)}/revoke-sessions`),
    { method: "POST" },
  );
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail ?? "Failed to revoke sessions");
  }
}

export interface CreatedUser {
  user_id: string;
  username: string;
  role: "admin" | "user";
  is_admin: boolean;
}

export async function createUser(
  username: string,
  password: string,
): Promise<CreatedUser> {
  const res = await apiFetch(apiUrl("/api/v1/auth/users"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    const detail = data?.detail;
    const message =
      typeof detail === "string"
        ? detail
        : Array.isArray(detail) && detail.length > 0 && detail[0]?.msg
          ? String(detail[0].msg)
          : "Failed to create user";
    throw new Error(message);
  }
  return (await res.json()) as CreatedUser;
}

export interface InviteRecord {
  code: string;
  email: string;
  created_by: string;
  created_at: string;
  used_by: string;
  used_at: string;
}

export async function listInvites(): Promise<InviteRecord[]> {
  const res = await apiFetch(apiUrl("/api/v1/auth/invites"));
  if (!res.ok) throw new Error("Failed to fetch invites");
  return res.json();
}

export async function createInvite(email: string): Promise<InviteRecord> {
  const res = await apiFetch(apiUrl("/api/v1/auth/invites"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail ?? "Failed to create invite");
  }
  return (await res.json()) as InviteRecord;
}

export async function deleteInvite(code: string): Promise<void> {
  const res = await apiFetch(
    apiUrl(`/api/v1/auth/invites/${encodeURIComponent(code)}`),
    { method: "DELETE" },
  );
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail ?? "Failed to delete invite");
  }
}
