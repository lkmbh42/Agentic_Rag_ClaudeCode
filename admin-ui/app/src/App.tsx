import { useEffect, useRef, useState } from "react";
import { api, ApiError, citationMediaPath, getToken, setToken } from "./api";

type AdminView =
  | "dashboard" | "users" | "departments" | "collections"
  | "documents" | "permissions" | "audit";

export default function App() {
  const [token, setTok] = useState<string | null>(getToken());
  const [me, setMe] = useState<any>(null);
  const [authError, setAuthError] = useState("");
  const [mode, setMode] = useState<"chat" | "admin">("chat");

  useEffect(() => {
    if (!token) { setMe(null); return; }
    api.me().then(setMe).catch(() => { setToken(null); setTok(null); });
  }, [token]);

  function logout() { setToken(null); setTok(null); setMe(null); setMode("chat"); }

  if (!token) return <Login onLogin={(t) => { setAuthError(""); setTok(t); }} error={authError} setError={setAuthError} />;
  if (!me) return <div className="login"><p className="muted">Loading…</p></div>;

  const isAdmin = me.role === "admin";
  if (mode === "admin" && isAdmin)
    return <AdminApp email={me.email} onExit={() => setMode("chat")} onLogout={logout} />;
  return <ChatApp email={me.email} isAdmin={isAdmin} onAdmin={() => setMode("admin")} onLogout={logout} />;
}

// ----- Admin app (separate from chat) ---------------------------------------
function AdminApp({ email, onExit, onLogout }: { email: string; onExit: () => void; onLogout: () => void }) {
  const [view, setView] = useState<AdminView>("dashboard");
  const nav: [AdminView, string][] = [
    ["dashboard", "Live ops"], ["users", "Users"], ["departments", "Departments"],
    ["collections", "Collections"], ["documents", "Documents"],
    ["permissions", "Permissions"], ["audit", "Audit log"],
  ];
  return (
    <div className="shell">
      <aside className="sidebar">
        <h2>Admin</h2>
        <button className="back" onClick={onExit}>← Back to chat</button>
        {nav.map(([v, label]) => (
          <button key={v} className={view === v ? "active" : ""} onClick={() => setView(v)}>{label}</button>
        ))}
        <div className="spacer" />
        <div className="muted" style={{ padding: ".4rem .6rem", fontSize: ".8rem" }}>{email} · admin</div>
        <button onClick={onLogout}>Log out</button>
      </aside>
      <main className="main">
        {view === "dashboard" && <Dashboard />}
        {view === "users" && <Users />}
        {view === "departments" && <Departments />}
        {view === "collections" && <Collections />}
        {view === "documents" && <Documents />}
        {view === "permissions" && <Permissions />}
        {view === "audit" && <Audit />}
      </main>
    </div>
  );
}

function Login({ onLogin, error, setError }: { onLogin: (t: string) => void; error: string; setError: (s: string) => void }) {
  const [email, setEmail] = useState("admin@example.com");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(e: any) {
    e.preventDefault();
    setBusy(true); setError("");
    try { const r = await api.login(email, password); onLogin(r.access_token); }
    catch (err: any) { setError(err.message || "Login failed"); }
    finally { setBusy(false); }
  }
  return (
    <div className="login">
      <form onSubmit={submit}>
        <h1>Admin sign in</h1>
        <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="email" />
        <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="password" />
        {error && <div className="error">{error}</div>}
        <button className="primary" disabled={busy}>{busy ? "…" : "Sign in"}</button>
      </form>
    </div>
  );
}

function useData<T>(loader: () => Promise<T>, deps: any[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");
  const [tick, setTick] = useState(0);
  useEffect(() => {
    loader().then((d) => { setData(d); setError(""); })
      .catch((e: ApiError) => setError(e.message));
  }, [tick, ...deps]);
  return { data, error, reload: () => setTick((t) => t + 1) };
}

function Dashboard() {
  const { data, error } = useData(() => api.metrics());
  if (error) return <Err msg={error} />;
  if (!data) return <p className="muted">Loading…</p>;
  const m: any = data;
  const cards = [
    ["Queue depth", m.queue_depth],
    ["Indexing backlog", m.indexing_backlog],
    ["Cache hit rate", `${(m.cache_hit_rate * 100).toFixed(1)}%`],
    ["p50 latency", `${m.latency_ms.p50} ms`],
    ["p95 latency", `${m.latency_ms.p95} ms`],
    ["p99 latency", `${m.latency_ms.p99} ms`],
    ["Users", m.counts.users],
    ["Documents", m.counts.documents],
    ["Collections", m.counts.collections],
    ["Evals scored", m.eval.scored],
    ["Avg faithfulness", m.eval.avg_faithfulness ?? "—"],
    ["Avg citation acc.", m.eval.avg_citation_accuracy ?? "—"],
  ];
  return (
    <>
      <h1>Live operations</h1>
      <div className="cards">
        {cards.map(([label, val]) => (
          <div className="card" key={label as string}>
            <div className="big">{val as any}</div>
            <div className="label">{label}</div>
          </div>
        ))}
      </div>
    </>
  );
}

function Users() {
  const { data, error, reload } = useData(() => api.users());
  const depts = useData(() => api.departments());
  const [email, setEmail] = useState("");
  const [pw, setPw] = useState("");
  const [role, setRole] = useState("user");
  const [dept, setDept] = useState("");
  const [msg, setMsg] = useState("");

  async function create(e: any) {
    e.preventDefault();
    try {
      await api.createUser({ email, password: pw, role, department_id: dept || null });
      setEmail(""); setPw(""); setMsg(""); reload();
    } catch (err: any) { setMsg(err.message); }
  }
  async function toggle(u: any) { await api.updateUser(u.id, { is_active: !u.is_active }); reload(); }
  async function revoke(u: any) { await api.revokeSessions(u.id); setMsg(`Sessions revoked for ${u.email}`); }
  async function reset(u: any) {
    const r = await api.resetCredential(u.id);
    setMsg(`Temp password for ${u.email}: ${r.temporary_password}`);
  }

  return (
    <>
      <h1>Users</h1>
      <form className="toolbar" onSubmit={create}>
        <input placeholder="email" value={email} onChange={(e) => setEmail(e.target.value)} />
        <input placeholder="password" value={pw} onChange={(e) => setPw(e.target.value)} />
        <select value={role} onChange={(e) => setRole(e.target.value)}>
          <option value="user">user</option><option value="admin">admin</option>
        </select>
        <select value={dept} onChange={(e) => setDept(e.target.value)}>
          <option value="">(no dept)</option>
          {depts.data?.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
        </select>
        <button className="primary">Create user</button>
      </form>
      {msg && <div className="notice">{msg}</div>}
      {error && <Err msg={error} />}
      <table>
        <thead><tr><th>Email</th><th>Role</th><th>Status</th><th>Actions</th></tr></thead>
        <tbody>
          {data?.map((u) => (
            <tr key={u.id}>
              <td>{u.email}</td><td>{u.role}</td>
              <td><span className={`badge ${u.is_active ? "ok" : "bad"}`}>{u.is_active ? "active" : "suspended"}</span></td>
              <td className="row-actions">
                <button onClick={() => toggle(u)}>{u.is_active ? "Suspend" : "Reactivate"}</button>
                <button onClick={() => revoke(u)}>Revoke sessions</button>
                <button onClick={() => reset(u)}>Reset credential</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

function Departments() {
  const { data, error, reload } = useData(() => api.departments());
  const [name, setName] = useState("");
  return (
    <>
      <h1>Departments</h1>
      <form className="toolbar" onSubmit={async (e) => { e.preventDefault(); await api.createDepartment(name); setName(""); reload(); }}>
        <input placeholder="name" value={name} onChange={(e) => setName(e.target.value)} />
        <button className="primary">Create</button>
      </form>
      {error && <Err msg={error} />}
      <table><thead><tr><th>Name</th><th>ID</th></tr></thead>
        <tbody>{data?.map((d) => <tr key={d.id}><td>{d.name}</td><td className="muted">{d.id}</td></tr>)}</tbody>
      </table>
    </>
  );
}

function Collections() {
  const { data, error, reload } = useData(() => api.collections());
  const depts = useData(() => api.departments());
  const [name, setName] = useState("");
  const [dept, setDept] = useState("");
  return (
    <>
      <h1>Collections</h1>
      <form className="toolbar" onSubmit={async (e) => { e.preventDefault(); await api.createCollection({ name, department_id: dept || null }); setName(""); reload(); }}>
        <input placeholder="name" value={name} onChange={(e) => setName(e.target.value)} />
        <select value={dept} onChange={(e) => setDept(e.target.value)}>
          <option value="">(no dept)</option>
          {depts.data?.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
        </select>
        <button className="primary">Create</button>
      </form>
      {error && <Err msg={error} />}
      <table><thead><tr><th>Name</th><th>Department</th><th>ID</th></tr></thead>
        <tbody>{data?.map((c) => <tr key={c.id}><td>{c.name}</td><td className="muted">{c.department_id ?? "—"}</td><td className="muted">{c.id}</td></tr>)}</tbody>
      </table>
    </>
  );
}

function Documents() {
  const { data, error, reload } = useData(() => api.documents());
  const colls = useData(() => api.collections());
  const [coll, setColl] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [msg, setMsg] = useState("");
  async function upload(e: any) {
    e.preventDefault();
    if (!coll || !file) { setMsg("Pick a collection and a file"); return; }
    try { const r: any = await api.uploadDocument(coll, file); setMsg(r.duplicate ? "Duplicate (already indexed)" : "Uploaded — indexing…"); reload(); }
    catch (err: any) { setMsg(err.message); }
  }
  return (
    <>
      <h1>Documents</h1>
      <form className="toolbar" onSubmit={upload}>
        <select value={coll} onChange={(e) => setColl(e.target.value)}>
          <option value="">(collection)</option>
          {colls.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        <input type="file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        <button className="primary">Upload</button>
        <button type="button" onClick={reload}>Refresh</button>
      </form>
      {msg && <div className="notice">{msg}</div>}
      {error && <Err msg={error} />}
      <table>
        <thead><tr><th>File</th><th>Type</th><th>Ingestion</th><th>Pages</th><th>Actions</th></tr></thead>
        <tbody>
          {data?.map((d) => (
            <tr key={d.id}>
              <td>{d.filename}</td><td>{d.file_type}</td>
              <td><IngestCell doc={d} /></td>
              <td>{d.page_count ?? "—"}</td>
              <td className="row-actions">
                <button onClick={async () => { await api.reindexDocument(d.id); reload(); }}>Re-ingest</button>
                <button className="danger" onClick={async () => { if (confirm(`Delete ${d.filename}?`)) { await api.deleteDocument(d.id); reload(); } }}>Delete</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

// Fine-grained ingestion status from ingest_jobs: shows the pipeline stage
// (queued/parsing/captioning/indexing/indexed/failed) and, on failure, the
// reason. Falls back to the coarse document status when no job row exists yet.
function IngestCell({ doc }: { doc: any }) {
  const [job, setJob] = useState<import("./api").IngestJob | null | undefined>(undefined);
  useEffect(() => {
    let live = true;
    api.ingestStatus(doc.id).then((j) => { if (live) setJob(j); }).catch(() => { if (live) setJob(null); });
    return () => { live = false; };
  }, [doc.id, doc.status]);

  const stage = job?.status ?? doc.status;
  const cls = stage === "indexed" ? "ok" : stage === "failed" ? "bad" : "";
  return (
    <span>
      <span className={`badge ${cls}`}>{stage}</span>
      {job?.attempt ? <span className="muted"> · try {job.attempt + 1}</span> : null}
      {stage === "failed" && (job?.error || doc.error) && (
        <div className="fail-reason" title={job?.error || doc.error}>{job?.error || doc.error}</div>
      )}
    </span>
  );
}

function Permissions() {
  const { data, error, reload } = useData(() => api.permissions());
  const users = useData(() => api.users());
  const depts = useData(() => api.departments());
  const colls = useData(() => api.collections());
  const [principalType, setPT] = useState("user");
  const [principalId, setPID] = useState("");
  const [resourceId, setRID] = useState("");
  const [level, setLevel] = useState("read");
  const [msg, setMsg] = useState("");

  const principals = principalType === "user" ? users.data : depts.data;

  async function grant(e: any) {
    e.preventDefault();
    try {
      await api.grantPermission({
        principal_type: principalType, principal_id: principalId,
        resource_type: "collection", resource_id: resourceId, access_level: level,
      });
      setMsg(""); reload();
    } catch (err: any) { setMsg(err.message); }
  }
  return (
    <>
      <h1>Permissions</h1>
      <p className="muted">Grant cross-scope access to a collection. Revoking invalidates any cached answers scoped to it.</p>
      <form className="toolbar" onSubmit={grant}>
        <select value={principalType} onChange={(e) => { setPT(e.target.value); setPID(""); }}>
          <option value="user">user</option><option value="department">department</option>
        </select>
        <select value={principalId} onChange={(e) => setPID(e.target.value)}>
          <option value="">(principal)</option>
          {principals?.map((p: any) => <option key={p.id} value={p.id}>{p.email ?? p.name}</option>)}
        </select>
        <select value={resourceId} onChange={(e) => setRID(e.target.value)}>
          <option value="">(collection)</option>
          {colls.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        <select value={level} onChange={(e) => setLevel(e.target.value)}>
          <option value="read">read</option><option value="write">write</option><option value="admin">admin</option>
        </select>
        <button className="primary">Grant</button>
      </form>
      {msg && <div className="notice">{msg}</div>}
      {error && <Err msg={error} />}
      <table>
        <thead><tr><th>Principal</th><th>Resource</th><th>Level</th><th>Actions</th></tr></thead>
        <tbody>
          {data?.map((p) => (
            <tr key={p.id}>
              <td>{p.principal_type}: <span className="muted">{p.principal_id.slice(0, 8)}</span></td>
              <td>{p.resource_type}: <span className="muted">{p.resource_id.slice(0, 8)}</span></td>
              <td>
                <select value={p.access_level} onChange={async (e) => { await api.editPermission(p.id, e.target.value); reload(); }}>
                  <option value="read">read</option><option value="write">write</option><option value="admin">admin</option>
                </select>
              </td>
              <td><button className="danger" onClick={async () => { if (confirm("Revoke this permission? (invalidates cache)")) { await api.revokePermission(p.id); reload(); } }}>Revoke</button></td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

function Audit() {
  const { data, error } = useData(() => api.auditLogs());
  return (
    <>
      <h1>Audit log</h1>
      {error && <Err msg={error} />}
      <table>
        <thead><tr><th>Action</th><th>User</th><th>Resource</th><th>Detail</th></tr></thead>
        <tbody>
          {data?.map((a) => (
            <tr key={a.id}>
              <td>{a.action}</td>
              <td className="muted">{a.user_id ? a.user_id.slice(0, 8) : "—"}</td>
              <td className="muted">{a.resource_type ? `${a.resource_type}:${(a.resource_id ?? "").slice(0, 8)}` : "—"}</td>
              <td className="muted">{a.detail ? JSON.stringify(a.detail) : "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

// ----- Chat app (ChatGPT/Claude-style: conversations on the left) ------------
// ----- Phase 4 chat widgets --------------------------------------------------

/** Citation chip: "[n] file.pdf · Seite N". Clicking toggles the source
 *  thumbnail (figure crop or page render) fetched through the ACL-checked
 *  /media endpoints. No image (degraded visual path) -> chip only. */
function CitationChip({ c }: { c: any }) {
  const [open, setOpen] = useState(false);
  const label = `${c.file_name || c.chunk_type || "source"}${c.page_number ? ` · Seite ${c.page_number}` : ""}`;
  const mediaPath = citationMediaPath(c);
  return (
    <span className="cite-wrap">
      <button type="button" className={`chip ${mediaPath ? "linky" : ""}`}
        title={c.document_id} onClick={() => mediaPath && setOpen(!open)}>
        [{c.marker}] {label}
      </button>
      {open && mediaPath && <AuthThumb path={mediaPath} alt={label} />}
    </span>
  );
}

/** <img> that fetches through the JWT-authenticated API (a plain src can't
 *  carry the bearer token). Missing images hide themselves — never an error. */
function AuthThumb({ path, alt }: { path: string; alt: string }) {
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let revoke: string | null = null;
    api.fetchImage(path).then((u) => {
      if (u) { revoke = u; setUrl(u); } else setFailed(true);
    });
    return () => { if (revoke) URL.revokeObjectURL(revoke); };
  }, [path]);
  if (failed) return <span className="muted thumb-missing">no preview available</span>;
  if (!url) return <span className="muted thumb-missing">loading preview…</span>;
  return <img className="cite-thumb" src={url} alt={alt} />;
}

/** 👍/👎 with an optional reason on 👎, persisted per (message, user). */
function FeedbackBar({ messageId, initial }: { messageId: string; initial?: string | null }) {
  const [rating, setRating] = useState<string | null>(initial ?? null);
  const [askReason, setAskReason] = useState(false);
  const [reason, setReason] = useState("");
  const [err, setErr] = useState("");

  async function send(r: "up" | "down", why?: string) {
    setErr("");
    try {
      await api.sendFeedback(messageId, r, why);
      setRating(r);
      setAskReason(false);
    } catch (e: any) { setErr(e.message); }
  }

  return (
    <div className="feedback">
      <button type="button" className={`fb ${rating === "up" ? "on" : ""}`}
        title="Helpful" onClick={() => send("up")}>👍</button>
      <button type="button" className={`fb ${rating === "down" ? "on" : ""}`}
        title="Not helpful" onClick={() => setAskReason(!askReason)}>👎</button>
      {askReason && (
        <span className="fb-reason">
          <input value={reason} placeholder="What was wrong? (optional)"
            onChange={(e) => setReason(e.target.value)} />
          <button type="button" onClick={() => send("down", reason.trim() || undefined)}>Send</button>
        </span>
      )}
      {err && <span className="muted"> {err}</span>}
    </div>
  );
}

function ChatApp({ email, isAdmin, onAdmin, onLogout }: {
  email: string; isAdmin: boolean; onAdmin: () => void; onLogout: () => void;
}) {
  const [sessions, setSessions] = useState<any[]>([]);
  const [sid, setSid] = useState<string | null>(null);
  const [messages, setMessages] = useState<any[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [streaming, setStreaming] = useState("");
  const [error, setError] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

  async function loadSessions() {
    try { setSessions(await api.chatSessions()); } catch (e: any) { setError(e.message); }
  }
  useEffect(() => { loadSessions(); }, []);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, streaming]);

  async function openSession(id: string) {
    setSid(id); setError("");
    try {
      const s = await api.chatSession(id);
      setMessages((s.messages || []).map((m: any) => ({
        role: m.role, content: m.content, message_id: m.id, feedback: m.feedback,
      })));
    } catch (e: any) { setError(e.message); }
  }
  function newChat() { setSid(null); setMessages([]); setError(""); }

  async function send(e: any) {
    e.preventDefault();
    const msg = input.trim();
    if (!msg || busy) return;
    setInput(""); setBusy(true); setStreaming(""); setError("");
    setMessages((m) => [...m, { role: "user", content: msg }]);
    let acc = "";
    await api.chatStream(msg, sid, {
      onToken: (t) => { acc += t; setStreaming(acc); },
      onDone: (p) => {
        setMessages((m) => [...m, {
          role: "assistant", content: p.answer || acc, citations: p.citations,
          route: p.route, cache_hit: p.cache_hit, insufficient: p.insufficient,
          message_id: p.message_id,
        }]);
        setStreaming(""); setBusy(false);
        if (!sid && p.session_id) { setSid(p.session_id); loadSessions(); }
      },
      onError: (err) => { setError(err.message); setStreaming(""); setBusy(false); },
    });
  }

  const currentTitle = sid ? (sessions.find((s) => s.id === sid)?.title || "Conversation") : "New chat";

  return (
    <div className="chatgpt">
      <aside className="conv-sidebar">
        <button className="newchat" onClick={newChat}>＋ New chat</button>
        <div className="conv-list">
          {sessions.length === 0 && <div className="conv-empty muted">No conversations yet</div>}
          {sessions.map((s) => (
            <button key={s.id} className={`conv ${sid === s.id ? "active" : ""}`} title={s.title || ""}
              onClick={() => openSession(s.id)}>
              {s.title || "New conversation"}
            </button>
          ))}
        </div>
        <div className="conv-footer">
          <div className="who muted">{email}{isAdmin ? " · admin" : ""}</div>
          {isAdmin && <button onClick={onAdmin}>⚙ Admin dashboard</button>}
          <button onClick={onLogout}>Log out</button>
        </div>
      </aside>

      <main className="conv-main">
        <header className="conv-head">
          <span className="conv-title">{currentTitle}</span>
          <span className="muted">Grounded only in documents you can access</span>
        </header>
        <div className="chat-thread">
          {messages.length === 0 && !busy && (
            <div className="welcome">
              <h2>Agentic RAG</h2>
              <p className="muted">Ask a question about your documents to begin.</p>
            </div>
          )}
          {messages.map((m, i) => (
            <div key={i} className={`bubble ${m.role}`}>
              <div className="bubble-body">{m.content}</div>
              {m.role === "assistant" && m.citations && m.citations.length > 0 && (
                <div className="cites">
                  {m.citations.map((c: any, j: number) => (
                    <CitationChip c={c} key={j} />
                  ))}
                </div>
              )}
              {m.role === "assistant" && (m.route || m.cache_hit) && (
                <div className="meta">
                  {m.cache_hit ? "⚡ cached" : `route: ${m.route ?? "—"}`}
                  {m.insufficient ? " · no supporting evidence" : ""}
                </div>
              )}
              {m.role === "assistant" && m.message_id && (
                <FeedbackBar messageId={m.message_id} initial={m.feedback} />
              )}
            </div>
          ))}
          {busy && (
            <div className="bubble assistant">
              <div className="bubble-body">{streaming || <span className="muted">thinking…</span>}</div>
            </div>
          )}
          <div ref={endRef} />
        </div>
        {error && <div className="notice error">{error}</div>}
        <form className="chat-input" onSubmit={send}>
          <input value={input} onChange={(e) => setInput(e.target.value)}
            placeholder="Message…" disabled={busy} autoFocus />
          <button className="primary" disabled={busy || !input.trim()}>{busy ? "…" : "Send"}</button>
        </form>
      </main>
    </div>
  );
}

function Err({ msg }: { msg: string }) {
  return <div className="notice error">Error: {msg}</div>;
}
