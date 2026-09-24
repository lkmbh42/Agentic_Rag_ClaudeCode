// Thin API client. Talks only to the documented FastAPI endpoints with a JWT
// bearer token — no privileged backdoor. Base URL is build-time configurable
// (VITE_API_BASE); dev default hits the backend directly (CORS-allowed), prod
// builds with VITE_API_BASE=/api behind the reverse proxy.

const BASE = (import.meta.env.VITE_API_BASE as string) || "http://localhost:8000";
const TOKEN_KEY = "rag_admin_token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}
export function setToken(t: string | null) {
  if (t) localStorage.setItem(TOKEN_KEY, t);
  else localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function req<T = any>(path: string, opts: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = { ...(opts.headers as any) };
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (opts.body && !(opts.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }
  const res = await fetch(`${BASE}${path}`, { ...opts, headers });
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  const data = text ? JSON.parse(text) : undefined;
  if (!res.ok) {
    const msg = data?.detail
      ? typeof data.detail === "string"
        ? data.detail
        : JSON.stringify(data.detail)
      : res.statusText;
    throw new ApiError(res.status, msg);
  }
  return data as T;
}

export const api = {
  base: BASE,
  async login(email: string, password: string) {
    const r = await req<{ access_token: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    setToken(r.access_token);
    return r;
  },
  me: () => req("/auth/me"),
  // chat (employee-facing)
  chatSessions: () => req<any[]>("/chat/sessions"),
  chatSession: (id: string) => req<any>(`/chat/sessions/${id}`),
  async chatStream(
    message: string,
    sessionId: string | null,
    h: { onToken?: (t: string) => void; onDone?: (p: any) => void; onError?: (e: Error) => void },
  ) {
    const token = getToken();
    const res = await fetch(`${BASE}/chat/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ message, session_id: sessionId || undefined }),
    });
    if (!res.ok || !res.body) {
      h.onError?.(new Error(`stream failed (${res.status})`));
      return;
    }
    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      // Normalize CRLF → LF: sse-starlette delimits events with "\r\n\r\n", but
      // we split on "\n\n". Without this the delimiter is never found, no event
      // ever parses, and the answer only shows after a manual reload. Stripping
      // CR (not significant in SSE) also survives a "\r\n" split across chunks.
      buf = (buf + dec.decode(value, { stream: true })).replace(/\r/g, "");
      let idx: number;
      while ((idx = buf.indexOf("\n\n")) >= 0) {
        const block = buf.slice(0, idx);
        buf = buf.slice(idx + 2);
        let event = "message";
        let data = "";
        for (const line of block.split("\n")) {
          if (line.startsWith("event:")) event = line.slice(6).trim();
          else if (line.startsWith("data:")) data += line.slice(5).trim();
        }
        if (!data) continue;
        let payload: any;
        try { payload = JSON.parse(data); } catch { continue; }
        if (event === "token") h.onToken?.(payload.token ?? "");
        else if (event === "done") h.onDone?.(payload);
        else if (event === "error") h.onError?.(new Error(payload.error ?? "stream error"));
      }
    }
  },
  // listings
  users: () => req<any[]>("/admin/users"),
  departments: () => req<any[]>("/admin/departments"),
  collections: () => req<any[]>("/admin/collections"),
  permissions: () => req<any[]>("/admin/permissions"),
  documents: () => req<any[]>("/documents"),
  auditLogs: () => req<any[]>("/admin/audit-logs?limit=100"),
  metrics: () => req("/admin/metrics"),
  // mutations
  createDepartment: (name: string) =>
    req("/admin/departments", { method: "POST", body: JSON.stringify({ name }) }),
  createCollection: (b: any) =>
    req("/admin/collections", { method: "POST", body: JSON.stringify(b) }),
  createUser: (b: any) => req("/admin/users", { method: "POST", body: JSON.stringify(b) }),
  updateUser: (id: string, b: any) =>
    req(`/admin/users/${id}`, { method: "PATCH", body: JSON.stringify(b) }),
  revokeSessions: (id: string) =>
    req(`/admin/users/${id}/revoke-sessions`, { method: "POST" }),
  resetCredential: (id: string) =>
    req<{ temporary_password: string }>(`/admin/users/${id}/reset-credential`, { method: "POST" }),
  grantPermission: (b: any) =>
    req("/admin/permissions", { method: "POST", body: JSON.stringify(b) }),
  editPermission: (id: string, access_level: string) =>
    req(`/admin/permissions/${id}`, { method: "PATCH", body: JSON.stringify({ access_level }) }),
  revokePermission: (id: string) => req(`/admin/permissions/${id}`, { method: "DELETE" }),
  uploadDocument: (collectionId: string, file: File) => {
    const fd = new FormData();
    fd.append("collection_id", collectionId);
    fd.append("file", file);
    return req("/documents/upload", { method: "POST", body: fd });
  },
  reindexDocument: (id: string) => req(`/documents/${id}/reindex`, { method: "POST" }),
  deleteDocument: (id: string) => req(`/documents/${id}`, { method: "DELETE" }),
  ingestStatus: (id: string) =>
    req<IngestJob | null>(`/documents/${id}/ingest-status`),
  // Phase 4: feedback + ACL-checked media (thumbnails)
  sendFeedback: (messageId: string, rating: "up" | "down", reason?: string) =>
    req(`/chat/messages/${messageId}/feedback`, {
      method: "POST",
      body: JSON.stringify({ rating, reason: reason || undefined }),
    }),
  // Images need the bearer token, so <img src> can't hit the API directly —
  // fetch with auth and hand back an object URL (caller revokes it).
  async fetchImage(path: string): Promise<string | null> {
    const token = getToken();
    const res = await fetch(`${BASE}${path}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) return null; // degraded visual path / no image: hide quietly
    return URL.createObjectURL(await res.blob());
  },
};

// Media paths for a citation (Phase 4). Figure chunks carry their MinIO crop
// as `image_uri` (s3://figures/{doc}/{figure}.png); anything with a page
// number can show the page render when the page pipeline produced one.
export function citationMediaPath(c: {
  document_id: string; page_number?: number | null; image_uri?: string | null;
}): string | null {
  const m = (c.image_uri || "").match(/^s3:\/\/([^/]+)\/([^/]+)\/(.+)\.png$/);
  if (m && m[1] === "figures") return `/media/figures/${m[2]}/${m[3]}`;
  if (c.page_number) return `/media/pages/${c.document_id}/${c.page_number}`;
  return null;
}

export type IngestJob = {
  status: "queued" | "parsing" | "captioning" | "indexing" | "indexed" | "failed";
  attempt: number;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
  updated_at: string;
};
