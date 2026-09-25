// Employee-facing research desk: ask a question, read the answer, verify it
// against the exact source page. Evidence always appears on "paper" (the source
// sheet); anything the machine wrote (answers, figure descriptions) never does.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, figurePath } from "./api";
import { Icon } from "./icons";
import { Markdown } from "./markdown";
import { AuthImage, Lightbox, Notice } from "./ui";

type Citation = {
  marker: number;
  document_id?: string;
  file_name?: string;
  page_number?: number | null;
  chunk_type?: string;
  section_title?: string | null;
  content?: string | null;
  image_uri?: string | null;
  revoked?: boolean;
};
type Msg = {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[] | null;
  message_id?: string;
  feedback?: string | null;
  insufficient?: boolean;
  stopped?: boolean;
};
type Zoom = { path: string; alt: string };

const VISUAL = new Set(["image", "chart", "diagram"]);
const prettyName = (name?: string) =>
  (name || "Document").replace(/\.[a-z0-9]{2,5}$/i, "").replace(/_+/g, " ").replace(/\s+/g, " ").trim();
const kindIcon = (t?: string) => (t === "table" ? "table" : VISUAL.has(t ?? "") ? "image" : "doc");

function groupSessions(list: any[], filter: string): [string, any[]][] {
  const q = filter.trim().toLowerCase();
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const DAY = 86_400_000;
  const groups: [string, any[]][] = [
    ["Today", []], ["Yesterday", []], ["Previous 7 days", []], ["Previous 30 days", []], ["Older", []],
  ];
  const sorted = [...list].sort((a, b) => +new Date(b.created_at) - +new Date(a.created_at));
  for (const s of sorted) {
    if (q && !(s.title || "").toLowerCase().includes(q)) continue;
    const t = +new Date(s.created_at);
    const i = t >= today ? 0 : t >= today - DAY ? 1 : t >= today - 7 * DAY ? 2 : t >= today - 30 * DAY ? 3 : 4;
    groups[i][1].push(s);
  }
  return groups.filter(([, v]) => v.length > 0);
}

export function ChatApp({ email, isAdmin, onAdmin, onLogout }: {
  email: string; isAdmin: boolean; onAdmin: () => void; onLogout: () => void;
}) {
  const [sessions, setSessions] = useState<any[]>([]);
  const [sessionsLoaded, setSessionsLoaded] = useState(false);
  const [library, setLibrary] = useState<any[] | null>(null);
  const [sid, setSid] = useState<string | null>(null);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [loadingSession, setLoadingSession] = useState(false);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [streaming, setStreaming] = useState("");
  const [error, setError] = useState("");
  const [source, setSource] = useState<Citation | null>(null);
  const [zoom, setZoom] = useState<Zoom | null>(null);
  const [navOpen, setNavOpen] = useState(false);
  const [filter, setFilter] = useState("");

  const threadRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const stick = useRef(true);            // follow new text only while the reader is at the bottom
  const abortRef = useRef<AbortController | null>(null);
  const reqId = useRef(0);               // any newer action invalidates older callbacks

  useEffect(() => { document.title = "Recherche"; }, []);

  const loadSessions = useCallback(async () => {
    try { setSessions(await api.chatSessions()); }
    catch (e: any) { setError(e.message); }
    finally { setSessionsLoaded(true); }
  }, []);
  useEffect(() => {
    loadSessions();
    api.documents().then(setLibrary).catch(() => setLibrary([]));
  }, [loadSessions]);

  useEffect(() => {
    const el = threadRef.current;
    if (el && stick.current) el.scrollTop = el.scrollHeight;
  }, [messages, streaming, busy]);

  // Grow the question box with its text (up to 200px). Re-fit on resize: a
  // height measured at another width (e.g. mid-layout) must not stick.
  const fitInput = useCallback(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "auto";
    if (el.value) el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, []);
  useEffect(fitInput, [input, fitInput]);
  useEffect(() => {
    window.addEventListener("resize", fitInput);
    return () => window.removeEventListener("resize", fitInput);
  }, [fitInput]);

  function onScroll() {
    const el = threadRef.current;
    if (el) stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
  }

  function abortStream() {
    reqId.current++;
    abortRef.current?.abort();
    abortRef.current = null;
    setBusy(false);
    setStreaming("");
  }

  async function openSession(id: string) {
    if (busy) abortStream();
    setNavOpen(false); setSource(null); setError("");
    setSid(id); setMessages([]); setLoadingSession(true);
    const my = ++reqId.current;
    try {
      const s = await api.chatSession(id);
      if (reqId.current !== my) return;
      setMessages((s.messages || []).map((m: any) => ({
        role: m.role, content: m.content, message_id: m.id,
        feedback: m.feedback, citations: m.citations,
      })));
      stick.current = true;
    } catch (e: any) {
      if (reqId.current === my) setError(e.message);
    } finally {
      if (reqId.current === my) setLoadingSession(false);
    }
  }

  function newQuestion() {
    if (busy) abortStream();
    reqId.current++;
    setSid(null); setMessages([]); setError(""); setSource(null);
    setNavOpen(false); setLoadingSession(false);
    inputRef.current?.focus();
  }

  async function ask(text?: string) {
    const q = (text ?? input).trim();
    if (!q || busy) return;
    const my = ++reqId.current;
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    const sessionAtSend = sid;
    setInput(""); setError(""); setBusy(true); setStreaming("");
    stick.current = true;
    setMessages((m) => [...m, { role: "user", content: q }]);
    let acc = "";
    await api.chatStream(q, sessionAtSend, {
      signal: ctrl.signal,
      onToken: (t) => {
        if (reqId.current !== my) return;
        acc += t;
        setStreaming(acc);
      },
      onDone: (p) => {
        if (reqId.current !== my) return;
        setMessages((m) => [...m, {
          role: "assistant", content: p.answer || acc, citations: p.citations,
          message_id: p.message_id, insufficient: p.insufficient,
        }]);
        setStreaming(""); setBusy(false);
        abortRef.current = null;
        if (!sessionAtSend && p.session_id) setSid(p.session_id);
        loadSessions();
      },
      onError: (err: any) => {
        if (err?.name === "AbortError" || reqId.current !== my) return;
        setError(err.message);
        setStreaming(""); setBusy(false);
        abortRef.current = null;
      },
    });
  }

  function stop() {
    const partial = streaming;
    abortStream();
    setMessages((m) => [...m, { role: "assistant", content: partial, stopped: true }]);
    loadSessions();
  }

  const turns = useMemo(() => {
    const out: { q: Msg | null; a?: Msg }[] = [];
    for (const m of messages) {
      if (m.role === "user") out.push({ q: m });
      else if (out.length && !out[out.length - 1].a) out[out.length - 1].a = m;
      else out.push({ q: null, a: m });
    }
    return out;
  }, [messages]);

  const groups = useMemo(() => groupSessions(sessions, filter), [sessions, filter]);
  const title = sid ? (sessions.find((s) => s.id === sid)?.title || "Conversation") : "New question";
  const ready = library?.filter((d) => d.status === "indexed").length ?? 0;

  return (
    <div className={`app ${source ? "with-source" : ""}`}>
      <aside className={`history ${navOpen ? "open" : ""}`} aria-label="Conversations">
        <div className="history-top">
          <div className="brand"><span className="mark" aria-hidden="true">R</span>Recherche</div>
          <button className="newq" onClick={newQuestion}><Icon name="plus" size={16} />New question</button>
          <label className="search">
            <Icon name="search" size={15} />
            <input value={filter} onChange={(e) => setFilter(e.target.value)}
              placeholder="Search conversations" aria-label="Search conversations" />
          </label>
        </div>
        <nav className="history-list">
          {!sessionsLoaded ? (
            <div className="skeleton-list" aria-label="Loading conversations">
              {Array.from({ length: 6 }, (_, i) => <span key={i} />)}
            </div>
          ) : groups.length === 0 ? (
            <p className="history-empty">{filter ? "No conversation matches that search." : "Your questions will be listed here."}</p>
          ) : groups.map(([label, items]) => (
            <section key={label}>
              <h2 className="history-label">{label}</h2>
              {items.map((s) => (
                <button key={s.id} className={`history-item ${sid === s.id ? "active" : ""}`}
                  aria-current={sid === s.id ? "page" : undefined}
                  onClick={() => openSession(s.id)} title={s.title || ""}>
                  {s.title || "Untitled question"}
                </button>
              ))}
            </section>
          ))}
        </nav>
        <div className="history-foot">
          <div className="who">
            <span className="avatar" aria-hidden="true">{(email[0] || "?").toUpperCase()}</span>
            <span className="who-mail" title={email}>{email}</span>
          </div>
          <div className="foot-actions">
            {isAdmin && <button className="ghost" onClick={onAdmin}><Icon name="shield" size={16} />Admin</button>}
            <button className="ghost" onClick={onLogout}><Icon name="out" size={16} />Sign out</button>
          </div>
        </div>
      </aside>
      {navOpen && <div className="scrim" onClick={() => setNavOpen(false)} />}

      <main className="desk">
        <header className="desk-head">
          <button className="icon-btn only-narrow" onClick={() => setNavOpen(true)} aria-label="Show conversations">
            <Icon name="menu" />
          </button>
          <h1 className="desk-title">{title}</h1>
          {library && (
            <span className="scope" title={library.map((d) => d.filename).join("\n")}>
              <Icon name="doc" size={15} />{ready} {ready === 1 ? "document" : "documents"}
            </span>
          )}
        </header>

        <div className="thread" ref={threadRef} onScroll={onScroll}>
          <div className="thread-inner">
            {loadingSession ? (
              <p className="thread-loading" role="status">Opening conversation…</p>
            ) : turns.length === 0 ? (
              <EmptyState library={library} onPick={(q) => { setInput(q); inputRef.current?.focus(); }} />
            ) : turns.map((t, i) => (
              <article className="turn" key={i}>
                {t.q && <h2 className="question">{t.q.content}</h2>}
                {t.a ? (
                  <Answer m={t.a} active={source} onSource={setSource} onZoom={setZoom} />
                ) : busy && i === turns.length - 1 ? (
                  <Pending streaming={streaming} count={ready} />
                ) : null}
              </article>
            ))}
          </div>
        </div>

        {error && <div className="thread-error"><Notice kind="error">{error}</Notice></div>}
        <form className="composer" onSubmit={(e) => { e.preventDefault(); ask(); }}>
          <textarea ref={inputRef} rows={1} value={input} autoFocus
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); ask(); }
            }}
            placeholder="Ask about your documents" aria-label="Your question" />
          {busy ? (
            <button type="button" className="send stop" onClick={stop} aria-label="Stop answering"><Icon name="stop" /></button>
          ) : (
            <button type="submit" className="send" disabled={!input.trim()} aria-label="Ask"><Icon name="send" /></button>
          )}
        </form>
        <p className="composer-note">Answers come only from your documents. Check the source before you rely on one.</p>
      </main>

      {source && <SourcePage c={source} onClose={() => setSource(null)} onZoom={setZoom} />}
      {zoom && <Lightbox path={zoom.path} alt={zoom.alt} onClose={() => setZoom(null)} />}
    </div>
  );
}

function EmptyState({ library, onPick }: { library: any[] | null; onPick: (q: string) => void }) {
  const docs = library ?? [];
  const ready = docs.filter((d) => d.status === "indexed");
  const suggestions = [
    ...ready.slice(0, 2).map((d) => `Summarize the key points of “${prettyName(d.filename)}”`),
    "What do the charts in my documents show?",
  ];
  return (
    <div className="empty">
      <h2 className="empty-title">What do you want to find out?</h2>
      <p className="empty-sub">Answers come only from your documents, with the page each one comes from.</p>
      <div className="empty-suggest">
        {suggestions.map((s) => (
          <button key={s} type="button" onClick={() => onPick(s)}>{s}</button>
        ))}
      </div>
      {library && (
        <section className="library" aria-label="Your library">
          <h3>Your library <span>{ready.length} of {docs.length} ready to search</span></h3>
          {docs.length === 0 ? (
            <p className="lib-none">No documents yet. Ask an admin to upload the files you need.</p>
          ) : (
            <ul>
              {docs.slice(0, 8).map((d) => (
                <li key={d.id} className={d.status !== "indexed" ? "not-ready" : undefined}>
                  <Icon name="doc" size={15} />
                  <span className="lib-name">{prettyName(d.filename)}</span>
                  <span className="lib-meta">
                    {d.status !== "indexed" ? (d.status === "failed" ? "failed" : "indexing") : d.page_count ? `${d.page_count} pages` : ""}
                  </span>
                </li>
              ))}
            </ul>
          )}
          {docs.length > 8 && <p className="lib-more">and {docs.length - 8} more</p>}
        </section>
      )}
    </div>
  );
}

function Pending({ streaming, count }: { streaming: string; count: number }) {
  if (!streaming) {
    return (
      <p className="searching" role="status">
        <span className="scan" aria-hidden="true" />
        Searching {count || "your"} {count === 1 ? "document" : "documents"}…
      </p>
    );
  }
  return (
    <div className="answer">
      <div className="prose" aria-live="polite">
        <Markdown text={streaming} cite={(n, k) => <span key={k} className="cite-ref pending">{n}</span>} />
        <span className="caret" aria-hidden="true" />
      </div>
    </div>
  );
}

function Answer({ m, active, onSource, onZoom }: {
  m: Msg; active: Citation | null; onSource: (c: Citation) => void; onZoom: (z: Zoom) => void;
}) {
  const cites = m.citations || [];
  const byMarker = new Map(cites.map((c) => [c.marker, c]));
  const cite = (n: number, key: string) => {
    const c = byMarker.get(n);
    if (!c || c.revoked) {
      return <span key={key} className="cite-ref off" title="This source isn't available">{n}</span>;
    }
    return (
      <button key={key} type="button" className={`cite-ref ${active === c ? "on" : ""}`}
        onClick={() => onSource(c)}
        aria-label={`Source ${n}: ${prettyName(c.file_name)}${c.page_number ? `, page ${c.page_number}` : ""}`}>
        {n}
      </button>
    );
  };
  const figures = Array.from(new Map(
    cites.filter((c) => !c.revoked && VISUAL.has(c.chunk_type ?? ""))
      .map((c) => [figurePath(c), c] as const)
      .filter(([p]) => !!p),
  ).entries()).map(([path, c]) => ({
    path: path as string,
    alt: `Figure from ${prettyName(c.file_name)}${c.page_number ? `, page ${c.page_number}` : ""}`,
  }));

  return (
    <div className="answer">
      {m.content && <div className="prose"><Markdown text={m.content} cite={cite} /></div>}
      {m.stopped && (
        <p className="answer-flag">{m.content ? "Stopped. This answer is incomplete." : "Stopped before an answer was written."}</p>
      )}
      {m.insufficient && <p className="answer-flag">No passage in your documents supports an answer to this.</p>}
      {figures.length > 0 && (
        <div className="figures">
          {figures.map((f) => (
            <AuthImage key={f.path} path={f.path} alt={f.alt} className="figure-thumb" onClick={() => onZoom(f)} />
          ))}
        </div>
      )}
      {cites.length > 0 && (
        <div className="sources">
          <h3 className="sources-label">Sources</h3>
          <ol className="source-list">
            {cites.map((c) => (
              <li key={c.marker}>
                {c.revoked ? (
                  <span className="source off"><span className="source-num">{c.marker}</span>No longer available to you</span>
                ) : (
                  <button type="button" className={`source ${active === c ? "on" : ""}`} onClick={() => onSource(c)}>
                    <span className="source-num">{c.marker}</span>
                    <Icon name={kindIcon(c.chunk_type)} size={15} />
                    <span className="source-name">{prettyName(c.file_name)}</span>
                    {c.page_number ? <span className="source-page">p. {c.page_number}</span> : null}
                  </button>
                )}
              </li>
            ))}
          </ol>
        </div>
      )}
      {m.message_id && (
        <div className="answer-actions">
          <CopyButton text={m.content} />
          <Feedback messageId={m.message_id} initial={m.feedback} />
        </div>
      )}
    </div>
  );
}

function SourcePage({ c, onClose, onZoom }: { c: Citation; onClose: () => void; onZoom: (z: Zoom) => void }) {
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [c, onClose]);
  const visual = VISUAL.has(c.chunk_type ?? "");
  const fig = figurePath(c);
  const alt = `Figure from ${prettyName(c.file_name)}${c.page_number ? `, page ${c.page_number}` : ""}`;

  return (
    <aside className="source-pane" aria-label={`Source ${c.marker}`}>
      <header className="source-head">
        <div className="source-head-text">
          <p className="source-eyebrow">Source {c.marker}</p>
          <h2 className="source-title">{prettyName(c.file_name)}</h2>
        </div>
        <button ref={closeRef} className="icon-btn" onClick={onClose} aria-label="Close source"><Icon name="close" /></button>
      </header>
      <div className="source-body">
        <div className="sheet">
          <div className="sheet-tab">
            <span>{c.file_name}</span>
            {c.page_number ? <span>page {c.page_number}</span> : null}
          </div>
          {c.section_title && <p className="sheet-section">{c.section_title}</p>}
          {visual ? (
            fig ? <AuthImage path={fig} alt={alt} className="sheet-figure" onClick={() => onZoom({ path: fig, alt })} />
              : <p className="sheet-missing">The image of this figure isn't available.</p>
          ) : c.chunk_type === "table" ? (
            <div className="sheet-text"><Markdown text={c.content || ""} cite={() => null} /></div>
          ) : (
            <div className="sheet-text">
              {(c.content || "This source has no text.").split(/\n\s*\n/).filter((p) => p.trim()).map((p, i) => (
                <p key={i}><mark>{p.trim()}</mark></p>
              ))}
            </div>
          )}
        </div>
        {visual && c.content && (
          <section className="generated">
            <h3>Description of the figure</h3>
            <div className="prose generated-text"><Markdown text={c.content} cite={() => null} /></div>
            <p className="generated-note">Written by the AI when the document was added — not text from the document.</p>
          </section>
        )}
        <p className="source-foot">
          {visual ? "The answer was based on this figure." : "The answer was based on this passage."}
        </p>
      </div>
    </aside>
  );
}

function CopyButton({ text }: { text: string }) {
  const [done, setDone] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(text.replace(/\*\*/g, ""));
      setDone(true);
      setTimeout(() => setDone(false), 1600);
    } catch { /* clipboard blocked: nothing to do */ }
  }
  return (
    <button type="button" className="act" onClick={copy}>
      <Icon name={done ? "check" : "copy"} size={16} />{done ? "Copied" : "Copy"}
    </button>
  );
}

/** Helpful / not helpful (+ optional reason), one rating per user per answer. */
function Feedback({ messageId, initial }: { messageId: string; initial?: string | null }) {
  const [rating, setRating] = useState<string | null>(initial ?? null);
  const [asking, setAsking] = useState(false);
  const [reason, setReason] = useState("");
  const [saved, setSaved] = useState(false);
  const [err, setErr] = useState("");

  async function send(r: "up" | "down", why?: string) {
    setErr("");
    try {
      await api.sendFeedback(messageId, r, why);
      setRating(r); setAsking(false); setSaved(true);
    } catch (e: any) { setErr(e.message); }
  }

  return (
    <div className="feedback">
      <button type="button" className={`act icon-only ${rating === "up" ? "on" : ""}`} aria-pressed={rating === "up"}
        onClick={() => send("up")} aria-label="Helpful" title="Helpful"><Icon name="up" size={16} /></button>
      <button type="button" className={`act icon-only ${rating === "down" ? "on" : ""}`} aria-pressed={rating === "down"}
        onClick={() => { setAsking((a) => !a); setSaved(false); }} aria-label="Not helpful" title="Not helpful">
        <Icon name="down" size={16} />
      </button>
      {asking && (
        <form className="fb-form" onSubmit={(e) => { e.preventDefault(); send("down", reason.trim() || undefined); }}>
          <input autoFocus value={reason} onChange={(e) => setReason(e.target.value)}
            placeholder="What was wrong? (optional)" aria-label="What was wrong" />
          <button type="submit" className="primary small">Send</button>
        </form>
      )}
      {saved && !asking && <span className="fb-note" role="status">Feedback saved</span>}
      {err && <span className="fb-note err">{err}</span>}
    </div>
  );
}
