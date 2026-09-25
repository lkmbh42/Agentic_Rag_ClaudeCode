// Thin API client. Talks only to the documented FastAPI endpoints with a JWT
// bearer token — no privileged backdoor. Base URL is build-time configurable
// (VITE_API_BASE); dev default hits the backend directly (CORS-allowed), prod
// builds with VITE_API_BASE=/api behind the reverse proxy.
//
// Sessions: the access token lives 15 min. On a 401 the client rotates the
// refresh token once (single-flight, shared by concurrent requests) and retries;
// if that fails it clears both tokens and fires AUTH_EXPIRED so the app shows
// the sign-in screen instead of failing silently.

const BASE = (import.meta.env.VITE_API_BASE as string) || "http://localhost:8000";
const TOKEN_KEY = "rag_admin_token";
const REFRESH_KEY = "rag_refresh_token";
export const AUTH_EXPIRED = "recherche:auth-expired";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}
function setTokens(access: string, refresh?: string) {
  localStorage.setItem(TOKEN_KEY, access);
  if (refresh) localStorage.setItem(REFRESH_KEY, refresh);
}
export function clearTokens() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(REFRESH_KEY);
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

/** What a person can act on — never a bare status code. */
function describe(status: number, detail: unknown): string {
  const text = typeof detail === "string"
    ? detail
    : Array.isArray(detail)
      ? detail.map((d: any) => d?.msg).filter(Boolean).join(" · ")
      : "";
  switch (status) {
    case 401: return "Your session has expired. Sign in again.";
    case 403: return "You don't have access to this.";
    case 413: return "This file is too large to upload.";
    case 429: return "Too many requests. Wait a moment, then try again.";
    case 503: return "The assistant is unavailable right now. Try again in a minute.";
  }
  if (status >= 500) return "The server hit an error. Try again, and tell an admin if it keeps happening.";
  return text || `Request failed (${status}).`;
}

let refreshing: Promise<boolean> | null = null;
function refreshTokens(): Promise<boolean> {
  if (!refreshing) {
    refreshing = (async () => {
      const rt = localStorage.getItem(REFRESH_KEY);
      if (!rt) return false;
      try {
        const res = await fetch(`${BASE}/auth/refresh`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh_token: rt }),
        });
        if (!res.ok) return false;
        const d = await res.json();
        setTokens(d.access_token, d.refresh_token);
        return true;
      } catch {
        return false;
      }
    })().finally(() => { refreshing = null; });
  }
  return refreshing;
}

function expire() {
  clearTokens();
  window.dispatchEvent(new Event(AUTH_EXPIRED));
}

/** fetch with the bearer token; on 401 rotate the refresh token once and retry. */
async function authFetch(path: string, init: RequestInit = {}, retry = true): Promise<Response> {
  const headers = new Headers(init.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, { ...init, headers });
  } catch (e: any) {
    if (e?.name === "AbortError") throw e;
    throw new ApiError(0, "Can't reach the server. Check your connection and try again.");
  }
  if (res.status === 401 && retry && !path.startsWith("/auth/")) {
    if (await refreshTokens()) return authFetch(path, init, false);
    expire();
  }
  return res;
}

async function req<T = any>(path: string, opts: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = { ...(opts.headers as any) };
  if (opts.body && !(opts.body instanceof FormData)) headers["Content-Type"] = "application/json";
  const res = await authFetch(path, { ...opts, headers });
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  let data: any;
  try { data = text ? JSON.parse(text) : undefined; } catch { data = undefined; }
  if (!res.ok) {
    // Sign-in failures must say what the server said ("Invalid credentials"),
    // not "session expired".
    const msg = path === "/auth/login" && res.status === 401
      ? (typeof data?.detail === "string" ? data.detail : "Wrong email or password.")
      : describe(res.status, data?.detail);
    throw new ApiError(res.status, msg);
  }
  return data as T;
}

export type StreamHandlers = {
  signal?: AbortSignal;
  onToken?: (t: string) => void;
  onDone?: (p: any) => void;
  onError?: (e: Error) => void;
};

export const api = {
  base: BASE,
  async login(email: string, password: string) {
    const r = await req<{ access_token: string; refresh_token: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    setTokens(r.access_token, r.refresh_token);
    return r;
  },
  /** Revoke the access token server-side (best effort), then forget both. */
  async logout() {
    try { await authFetch("/auth/logout", { method: "POST" }, false); } catch { /* offline: still sign out locally */ }
    clearTokens();
  },
  me: () => req("/auth/me"),
  // chat (employee-facing)
  chatSessions: () => req<any[]>("/chat/sessions"),
  chatSession: (id: string) => req<any>(`/chat/sessions/${id}`),
  async chatStream(message: string, sessionId: string | null, h: StreamHandlers) {
    let res: Response;
    try {
      res = await authFetch("/chat/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, session_id: sessionId || undefined }),
        signal: h.signal,
      });
    } catch (e: any) {
      h.onError?.(e);
      return;
    }
    if (!res.ok || !res.body) {
      let detail: unknown;
      try { detail = (await res.json())?.detail; } catch { /* no body */ }
      h.onError?.(new ApiError(res.status, describe(res.status, detail)));
      return;
    }
    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        // sse-starlette delimits events with CRLF; strip CR so "\n\n" splits
        // (also survives a "\r\n" split across chunks).
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
          else if (event === "error") h.onError?.(new ApiError(500, "The assistant hit an error while answering. Try asking again."));
        }
      }
    } catch (e: any) {
      h.onError?.(e?.name === "AbortError" ? e : new ApiError(0, "The connection dropped while answering. Try again."));
    }
  },
  // listings
  users: () => req<any[]>("/admin/users"),
  departments: () => req<any[]>("/admin/departments"),
  collections: () => req<any[]>("/admin/collections"),
  permissions: () => req<any[]>("/admin/permissions"),
  documents: () => req<any[]>("/documents"),
  auditLogs: () => req<any[]>("/admin/audit-logs?limit=200"),
  knowledgeGaps: (days: number) => req<any>(`/admin/knowledge-gaps?days=${days}`),
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
  sendFeedback: (messageId: string, rating: "up" | "down", reason?: string) =>
    req(`/chat/messages/${messageId}/feedback`, {
      method: "POST",
      body: JSON.stringify({ rating, reason: reason || undefined }),
    }),
  // Images need the bearer token, so <img src> can't hit the API directly —
  // fetch with auth and hand back an object URL (caller revokes it).
  async fetchImage(path: string): Promise<string | null> {
    try {
      const res = await authFetch(path);
      if (!res.ok) return null; // no image / no access: hide quietly
      return URL.createObjectURL(await res.blob());
    } catch {
      return null;
    }
  },
};

// Media path for a citation's figure crop (s3://figures/{doc}/{figure}.png).
// Page renders are only produced on a GPU host, so they're not offered.
export function figurePath(c: { image_uri?: string | null }): string | null {
  const m = (c.image_uri || "").match(/^s3:\/\/([^/]+)\/([^/]+)\/(.+)\.png$/);
  return m && m[1] === "figures" ? `/media/figures/${m[2]}/${m[3]}` : null;
}

export type IngestJob = {
  status: "queued" | "parsing" | "captioning" | "indexing" | "indexed" | "failed";
  attempt: number;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
  updated_at: string;
};
