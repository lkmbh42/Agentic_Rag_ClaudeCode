// Admin console: library, access, and insight into how the assistant is doing.

import { Fragment, useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { api, type IngestJob } from "./api";
import { Icon } from "./icons";
import { confirmAction, Notice, PageHeader, useData, when } from "./ui";

type View = "ops" | "gaps" | "documents" | "collections" | "users" | "departments" | "permissions" | "audit";

const NAV: { group: string; items: [View, string][] }[] = [
  { group: "Einblick", items: [["ops", "Live-Betrieb"], ["gaps", "Wissenslücken"]] },
  { group: "Bibliothek", items: [["documents", "Dokumente"], ["collections", "Sammlungen"]] },
  { group: "Zugriff", items: [["users", "Benutzer"], ["departments", "Abteilungen"], ["permissions", "Berechtigungen"]] },
  { group: "Protokoll", items: [["audit", "Audit-Protokoll"]] },
];

export function AdminApp({ email, onExit, onLogout }: { email: string; onExit: () => void; onLogout: () => void }) {
  const [view, setView] = useState<View>("ops");
  const [navOpen, setNavOpen] = useState(false);
  useEffect(() => { document.title = "Recherche · Admin"; return () => { document.title = "Recherche"; }; }, []);
  const go = (v: View) => { setView(v); setNavOpen(false); };

  return (
    <div className="admin">
      <aside className={`admin-nav ${navOpen ? "open" : ""}`} aria-label="Admin-Bereiche">
        <div className="brand"><span className="mark" aria-hidden="true">R</span>Recherche <span className="brand-tag">Admin</span></div>
        <button className="ghost back" onClick={onExit}><Icon name="back" size={16} />Zurück zu den Fragen</button>
        {NAV.map((g) => (
          <section key={g.group}>
            <h2 className="nav-label">{g.group}</h2>
            {g.items.map(([v, label]) => (
              <button key={v} className={`nav-item ${view === v ? "active" : ""}`}
                aria-current={view === v ? "page" : undefined} onClick={() => go(v)}>{label}</button>
            ))}
          </section>
        ))}
        <div className="spacer" />
        <div className="who"><span className="avatar" aria-hidden="true">{(email[0] || "?").toUpperCase()}</span><span className="who-mail">{email}</span></div>
        <button className="ghost" onClick={onLogout}><Icon name="out" size={16} />Abmelden</button>
      </aside>
      {navOpen && <div className="scrim" onClick={() => setNavOpen(false)} />}
      <main className="admin-main">
        <button className="icon-btn only-narrow admin-menu" onClick={() => setNavOpen(true)} aria-label="Admin-Bereiche anzeigen">
          <Icon name="menu" />
        </button>
        {view === "ops" && <Operations />}
        {view === "gaps" && <KnowledgeGaps />}
        {view === "documents" && <Documents />}
        {view === "collections" && <Collections />}
        {view === "users" && <Users />}
        {view === "departments" && <Departments />}
        {view === "permissions" && <Permissions />}
        {view === "audit" && <Audit />}
      </main>
    </div>
  );
}

// --------------------------------------------------------------- operations --
function Operations() {
  const { data, error, reload } = useData(() => api.metrics());
  const m: any = data;
  const groups: [string, [string, any][]][] = m ? [
    ["Antworten", [
      ["Antwortzeit (Median)", `${m.latency_ms.p50} ms`],
      ["95. Perzentil", `${m.latency_ms.p95} ms`],
      ["99. Perzentil", `${m.latency_ms.p99} ms`],
      ["Aus dem Cache", `${(m.cache_hit_rate * 100).toFixed(1)}%`],
    ]],
    ["Bibliothek", [
      ["Dokumente", m.counts.documents],
      ["Sammlungen", m.counts.collections],
      ["Wartet auf Indexierung", m.indexing_backlog],
      ["Aufträge in Warteschlange", m.queue_depth],
    ]],
    ["Qualität", [
      ["Bewertete Antworten", m.eval.scored],
      ["Treue zur Quelle", m.eval.avg_faithfulness ?? "—"],
      ["Zitatgenauigkeit", m.eval.avg_citation_accuracy ?? "—"],
      ["Benutzer", m.counts.users],
    ]],
  ] : [];
  return (
    <>
      <PageHeader title="Live-Betrieb" intro="Wie schnell der Assistent antwortet und was noch indexiert werden muss.">
        <button onClick={reload}><Icon name="refresh" size={16} />Aktualisieren</button>
      </PageHeader>
      {error && <Notice kind="error">{error}</Notice>}
      {!m ? <p className="muted">Wird geladen…</p> : groups.map(([g, cards]) => (
        <section key={g} className="stat-group">
          <h2 className="section-label">{g}</h2>
          <div className="cards">
            {cards.map(([label, val]) => (
              <div className="card" key={label}><div className="big">{val}</div><div className="label">{label}</div></div>
            ))}
          </div>
        </section>
      ))}
    </>
  );
}

// ------------------------------------------------------------ knowledge gaps --
const GAP_KIND: Record<string, [string, string]> = {
  no_evidence: ["Kein Beleg gefunden", "bad"],
  declined: ["Nicht in Dokumenten", "warn"],
  negative_feedback: ["Nicht hilfreich", "bad"],
};

function KnowledgeGaps() {
  const [days, setDays] = useState(30);
  const [open, setOpen] = useState<number | null>(null);
  const { data, error, reload } = useData(() => api.knowledgeGaps(days), [days]);
  const r: any = data;
  return (
    <>
      <PageHeader title="Wissenslücken"
        intro="Fragen, die der Assistent schlecht beantwortet hat – die häufigsten zuerst. Jede weist auf ein fehlendes oder unklares Dokument hin: fügen Sie es hinzu und fragen Sie erneut.">
        <select value={days} aria-label="Zeitraum" onChange={(e) => { setOpen(null); setDays(Number(e.target.value)); }}>
          {[7, 30, 90, 365].map((d) => <option key={d} value={d}>Letzte {d} Tage</option>)}
        </select>
        <button onClick={reload}><Icon name="refresh" size={16} />Aktualisieren</button>
      </PageHeader>
      {error && <Notice kind="error">{error}</Notice>}
      {!r ? <p className="muted">Wird geladen…</p> : (
        <>
          <div className="cards">
            {([
              ["Gestellte Fragen", r.total_questions],
              ["Unbeantwortet/schwach", r.gap_questions],
              ["Lückenquote", `${(r.gap_rate * 100).toFixed(1)}%`],
              ["Nicht hilfreich bewertet", r.negative_feedback],
            ] as [string, any][]).map(([label, val]) => (
              <div className="card" key={label}><div className="big">{val}</div><div className="label">{label}</div></div>
            ))}
          </div>
          {r.items.length === 0 ? (
            <Notice kind="ok">Keine Wissenslücken in diesem Zeitraum. Jede Frage fand belegende Dokumente.</Notice>
          ) : (
            <div className="table-wrap">
              <table className="gaps">
                <thead><tr><th>Frage</th><th className="num">Gefragt</th><th className="num">Personen</th><th>Grund</th><th>Zuletzt</th></tr></thead>
                <tbody>
                  {r.items.map((g: any, i: number) => (
                    <Fragment key={i}>
                      <tr className={`gap-row ${open === i ? "open" : ""}`} onClick={() => setOpen(open === i ? null : i)}
                        tabIndex={0} aria-expanded={open === i}
                        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setOpen(open === i ? null : i); } }}>
                        <td className="gap-q">{g.question}</td>
                        <td className="num">{g.count}</td>
                        <td className="num">{g.users}</td>
                        <td><span className="badges">{g.kinds.map((k: string) => (
                          <span key={k} className={`badge ${GAP_KIND[k]?.[1] ?? ""}`}>{GAP_KIND[k]?.[0] ?? k}</span>
                        ))}</span></td>
                        <td className="muted nowrap">{when(g.last_asked)}</td>
                      </tr>
                      {open === i && (
                        <tr className="gap-detail">
                          <td colSpan={5}>
                            <p className="detail-label">Letzte Antwort</p>
                            <p className="detail-text">{g.sample_answer || "(leere Antwort)"}</p>
                            {g.feedback_reasons.length > 0 && (
                              <>
                                <p className="detail-label">Was Nutzer bemängelt haben</p>
                                <ul className="detail-list">{g.feedback_reasons.map((x: string, j: number) => <li key={j}>{x}</li>)}</ul>
                              </>
                            )}
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </>
  );
}

// ---------------------------------------------------------------- documents --
const IN_FLIGHT = new Set(["pending", "processing"]);
const STAGE_LABEL: Record<string, string> = {
  queued: "In Warteschlange", parsing: "Seiten werden gelesen", captioning: "Bilder werden beschrieben",
  indexing: "Wird indexiert", indexed: "Bereit", failed: "Fehlgeschlagen", pending: "In Warteschlange", processing: "Wird verarbeitet",
};

function Documents() {
  const { data, error, reload } = useData(() => api.documents());
  const colls = useData(() => api.collections());
  const [coll, setColl] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const [tick, setTick] = useState(0);
  const fileRef = useRef<HTMLInputElement>(null);
  const collName = useMemo(() => new Map((colls.data ?? []).map((c: any) => [c.id, c.name])), [colls.data]);
  const working = (data ?? []).some((d: any) => IN_FLIGHT.has(d.status));

  // Keep the list live while anything is indexing (no manual refresh needed).
  useEffect(() => {
    if (!working) return;
    const t = setInterval(() => { reload(); setTick((x) => x + 1); }, 5000);
    return () => clearInterval(t);
  }, [working]);

  async function upload(e: FormEvent) {
    e.preventDefault();
    if (!coll || !file) { setMsg({ kind: "error", text: "Wählen Sie zuerst eine Sammlung und eine Datei." }); return; }
    setBusy(true); setMsg(null);
    try {
      const r: any = await api.uploadDocument(coll, file);
      setMsg(r.duplicate
        ? { kind: "ok", text: `„${file.name}" ist bereits in der Bibliothek – es wurde nichts hinzugefügt.` }
        : { kind: "ok", text: `„${file.name}" wurde hochgeladen und ist durchsuchbar, sobald die Indexierung abgeschlossen ist.` });
      setFile(null);
      if (fileRef.current) fileRef.current.value = "";
      reload();
    } catch (err: any) { setMsg({ kind: "error", text: err.message }); }
    finally { setBusy(false); }
  }

  async function reingest(d: any) {
    const ok = await confirmAction({
      title: `„${d.filename}" neu einlesen?`,
      body: "Die Seiten werden erneut gelesen und die Bilder neu beschrieben. Auf diesem Server kann das bis zu einer Stunde dauern; das Dokument ist bis zum Abschluss nicht durchsuchbar.",
      confirmLabel: "Neu einlesen",
    });
    if (!ok) return;
    try { await api.reindexDocument(d.id); reload(); }
    catch (err: any) { setMsg({ kind: "error", text: err.message }); }
  }

  async function remove(d: any) {
    const ok = await confirmAction({
      title: `„${d.filename}" löschen?`,
      body: "Die Datei und alles daraus Indexierte werden entfernt. Frühere Antworten, die es zitiert haben, verlieren diese Quelle. Das kann nicht rückgängig gemacht werden.",
      confirmLabel: "Dokument löschen", danger: true,
    });
    if (!ok) return;
    try { await api.deleteDocument(d.id); reload(); }
    catch (err: any) { setMsg({ kind: "error", text: err.message }); }
  }

  return (
    <>
      <PageHeader title="Dokumente" intro="Alles, was der Assistent durchsuchen kann. Uploads werden automatisch indexiert; Bilder dauern am längsten.">
        <button onClick={reload}><Icon name="refresh" size={16} />Aktualisieren</button>
      </PageHeader>
      <form className="upload" onSubmit={upload}>
        <select value={coll} onChange={(e) => setColl(e.target.value)} aria-label="Collection">
          <option value="">Sammlung wählen</option>
          {colls.data?.map((c: any) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        <label className="file-pick">
          <input ref={fileRef} type="file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          <Icon name="doc" size={16} />
          <span>{file ? file.name : "Datei wählen"}</span>
        </label>
        <button className="primary" disabled={busy}><Icon name="upload" size={16} />{busy ? "Wird hochgeladen…" : "Hochladen"}</button>
      </form>
      {msg && <Notice kind={msg.kind}>{msg.text}</Notice>}
      {error && <Notice kind="error">{error}</Notice>}
      <div className="table-wrap">
        <table>
          <thead><tr><th>Datei</th><th>Sammlung</th><th>Status</th><th className="num">Seiten</th><th><span className="sr-only">Aktionen</span></th></tr></thead>
          <tbody>
            {data?.length === 0 && <tr><td colSpan={5} className="muted">Noch keine Dokumente. Laden Sie oben das erste hoch.</td></tr>}
            {data?.map((d: any) => (
              <tr key={d.id}>
                <td className="strong">{d.filename}</td>
                <td className="muted">{collName.get(d.collection_id) ?? "—"}</td>
                <td><IngestCell doc={d} tick={tick} /></td>
                <td className="num">{d.page_count ?? "—"}</td>
                <td className="row-actions">
                  <button onClick={() => reingest(d)} disabled={IN_FLIGHT.has(d.status)}
                    title={IN_FLIGHT.has(d.status) ? "Wird bereits indexiert" : undefined}>Neu einlesen</button>
                  <button className="danger" onClick={() => remove(d)}>Löschen</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function IngestCell({ doc, tick }: { doc: any; tick: number }) {
  const [job, setJob] = useState<IngestJob | null | undefined>(undefined);
  useEffect(() => {
    let live = true;
    api.ingestStatus(doc.id).then((j) => { if (live) setJob(j); }).catch(() => { if (live) setJob(null); });
    return () => { live = false; };
  }, [doc.id, doc.status, tick]);
  // The document's own status is authoritative once settled; the job adds the
  // live stage while it runs.
  const stage = IN_FLIGHT.has(doc.status) ? (job?.status ?? doc.status) : doc.status;
  const cls = stage === "indexed" ? "ok" : stage === "failed" ? "bad" : "busy";
  const why = stage === "failed" ? (doc.error || job?.error) : null;
  return (
    <span className="ingest">
      <span className={`badge ${cls}`}>{STAGE_LABEL[stage] ?? stage}</span>
      {job?.attempt && IN_FLIGHT.has(doc.status) ? <span className="muted"> · Versuch {job.attempt + 1}</span> : null}
      {why && <span className="fail-reason" title={why}>{why}</span>}
    </span>
  );
}

// -------------------------------------------------------------- collections --
function Collections() {
  const { data, error, reload } = useData(() => api.collections());
  const depts = useData(() => api.departments());
  const [name, setName] = useState("");
  const [dept, setDept] = useState("");
  const [msg, setMsg] = useState("");
  const deptName = useMemo(() => new Map((depts.data ?? []).map((d: any) => [d.id, d.name])), [depts.data]);
  async function create(e: FormEvent) {
    e.preventDefault();
    setMsg("");
    try { await api.createCollection({ name: name.trim(), department_id: dept || null }); setName(""); reload(); }
    catch (err: any) { setMsg(err.message); }
  }
  return (
    <>
      <PageHeader title="Sammlungen" intro="Gruppen von Dokumenten. Eine Sammlung gehört zu einer Abteilung, deren Mitglieder sie durchsuchen können." />
      <form className="toolbar" onSubmit={create}>
        <input required placeholder="Name der Sammlung" aria-label="Name der Sammlung" value={name} onChange={(e) => setName(e.target.value)} />
        <select value={dept} onChange={(e) => setDept(e.target.value)} aria-label="Department">
          <option value="">Keine Abteilung (nur Admins)</option>
          {depts.data?.map((d: any) => <option key={d.id} value={d.id}>{d.name}</option>)}
        </select>
        <button className="primary"><Icon name="plus" size={16} />Sammlung erstellen</button>
      </form>
      {msg && <Notice kind="error">{msg}</Notice>}
      {error && <Notice kind="error">{error}</Notice>}
      <div className="table-wrap">
        <table>
          <thead><tr><th>Name</th><th>Abteilung</th></tr></thead>
          <tbody>
            {data?.map((c: any) => (
              <tr key={c.id}><td className="strong">{c.name}</td><td className="muted">{c.department_id ? deptName.get(c.department_id) ?? "—" : "Keine Abteilung"}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

// -------------------------------------------------------------------- users --
function Users() {
  const { data, error, reload } = useData(() => api.users());
  const depts = useData(() => api.departments());
  const [email, setEmail] = useState("");
  const [pw, setPw] = useState("");
  const [role, setRole] = useState("user");
  const [dept, setDept] = useState("");
  const [msg, setMsg] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const [temp, setTemp] = useState<{ email: string; pw: string } | null>(null);
  const deptName = useMemo(() => new Map((depts.data ?? []).map((d: any) => [d.id, d.name])), [depts.data]);

  async function create(e: FormEvent) {
    e.preventDefault();
    setMsg(null);
    try {
      await api.createUser({ email: email.trim(), password: pw, role, department_id: dept || null });
      setMsg({ kind: "ok", text: `${email.trim()} kann sich jetzt anmelden.` });
      setEmail(""); setPw(""); reload();
    } catch (err: any) { setMsg({ kind: "error", text: err.message }); }
  }
  async function toggle(u: any) {
    if (u.is_active && !(await confirmAction({
      title: `${u.email} sperren?`, body: "Die Person wird abgemeldet und kann sich erst nach Reaktivierung wieder anmelden.",
      confirmLabel: "Sperren", danger: true,
    }))) return;
    try { await api.updateUser(u.id, { is_active: !u.is_active }); reload(); }
    catch (err: any) { setMsg({ kind: "error", text: err.message }); }
  }
  async function revoke(u: any) {
    if (!(await confirmAction({
      title: `${u.email} überall abmelden?`, body: "Alle aktiven Sitzungen werden beendet. Die Person kann sich sofort wieder anmelden.",
      confirmLabel: "Überall abmelden",
    }))) return;
    try { await api.revokeSessions(u.id); setMsg({ kind: "ok", text: `${u.email} wurde überall abgemeldet.` }); }
    catch (err: any) { setMsg({ kind: "error", text: err.message }); }
  }
  async function reset(u: any) {
    if (!(await confirmAction({
      title: `Passwort von ${u.email} zurücksetzen?`, body: "Das aktuelle Passwort wird ungültig. Sie erhalten ein temporäres zum Weitergeben.",
      confirmLabel: "Passwort zurücksetzen", danger: true,
    }))) return;
    try { const r = await api.resetCredential(u.id); setTemp({ email: u.email, pw: r.temporary_password }); }
    catch (err: any) { setMsg({ kind: "error", text: err.message }); }
  }

  return (
    <>
      <PageHeader title="Benutzer" intro="Personen, die sich anmelden können. Ihre Abteilung bestimmt, welche Sammlungen sie durchsuchen können." />
      <form className="toolbar" onSubmit={create}>
        <input required type="email" placeholder="E-Mail" aria-label="E-Mail" autoComplete="off" value={email} onChange={(e) => setEmail(e.target.value)} />
        <input required type="password" placeholder="Anfangspasswort" aria-label="Anfangspasswort" autoComplete="new-password" value={pw} onChange={(e) => setPw(e.target.value)} />
        <select value={role} onChange={(e) => setRole(e.target.value)} aria-label="Role">
          <option value="user">Mitarbeiter/in</option><option value="admin">Admin</option>
        </select>
        <select value={dept} onChange={(e) => setDept(e.target.value)} aria-label="Department">
          <option value="">Keine Abteilung</option>
          {depts.data?.map((d: any) => <option key={d.id} value={d.id}>{d.name}</option>)}
        </select>
        <button className="primary"><Icon name="plus" size={16} />Benutzer hinzufügen</button>
      </form>
      {temp && (
        <div className="secret" role="status">
          <p>Temporäres Passwort für <strong>{temp.email}</strong>. Es wird nur einmal angezeigt.</p>
          <code>{temp.pw}</code>
          <button onClick={() => navigator.clipboard?.writeText(temp.pw)}><Icon name="copy" size={16} />Kopieren</button>
          <button className="ghost" onClick={() => setTemp(null)}>Fertig</button>
        </div>
      )}
      {msg && <Notice kind={msg.kind}>{msg.text}</Notice>}
      {error && <Notice kind="error">{error}</Notice>}
      <div className="table-wrap">
        <table>
          <thead><tr><th>E-Mail</th><th>Rolle</th><th>Abteilung</th><th>Status</th><th><span className="sr-only">Aktionen</span></th></tr></thead>
          <tbody>
            {data?.map((u: any) => (
              <tr key={u.id}>
                <td className="strong">{u.email}</td>
                <td>{u.role === "admin" ? "Admin" : "Mitarbeiter/in"}</td>
                <td className="muted">{u.department_id ? deptName.get(u.department_id) ?? "—" : "—"}</td>
                <td><span className={`badge ${u.is_active ? "ok" : "bad"}`}>{u.is_active ? "Aktiv" : "Gesperrt"}</span></td>
                <td className="row-actions">
                  <button onClick={() => toggle(u)}>{u.is_active ? "Sperren" : "Reaktivieren"}</button>
                  <button onClick={() => revoke(u)}>Überall abmelden</button>
                  <button onClick={() => reset(u)}>Passwort zurücksetzen</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

// -------------------------------------------------------------- departments --
function Departments() {
  const { data, error, reload } = useData(() => api.departments());
  const [name, setName] = useState("");
  const [msg, setMsg] = useState("");
  async function create(e: FormEvent) {
    e.preventDefault();
    setMsg("");
    try { await api.createDepartment(name.trim()); setName(""); reload(); }
    catch (err: any) { setMsg(err.message); }
  }
  return (
    <>
      <PageHeader title="Abteilungen" intro="Teams. Mitglieder einer Abteilung können die Sammlungen ihrer Abteilung durchsuchen." />
      <form className="toolbar" onSubmit={create}>
        <input required placeholder="Name der Abteilung" aria-label="Name der Abteilung" value={name} onChange={(e) => setName(e.target.value)} />
        <button className="primary"><Icon name="plus" size={16} />Abteilung erstellen</button>
      </form>
      {msg && <Notice kind="error">{msg}</Notice>}
      {error && <Notice kind="error">{error}</Notice>}
      <div className="table-wrap">
        <table>
          <thead><tr><th>Name</th></tr></thead>
          <tbody>{data?.map((d: any) => <tr key={d.id}><td className="strong">{d.name}</td></tr>)}</tbody>
        </table>
      </div>
    </>
  );
}

// -------------------------------------------------------------- permissions --
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

  const names = useMemo(() => {
    const m = new Map<string, string>();
    users.data?.forEach((u: any) => m.set(u.id, u.email));
    depts.data?.forEach((d: any) => m.set(d.id, d.name));
    colls.data?.forEach((c: any) => m.set(c.id, c.name));
    return m;
  }, [users.data, depts.data, colls.data]);
  const principals = principalType === "user" ? users.data : depts.data;

  async function grant(e: FormEvent) {
    e.preventDefault();
    setMsg("");
    try {
      await api.grantPermission({
        principal_type: principalType, principal_id: principalId,
        resource_type: "collection", resource_id: resourceId, access_level: level,
      });
      reload();
    } catch (err: any) { setMsg(err.message); }
  }
  async function change(p: any, lvl: string) {
    setMsg("");
    try { await api.editPermission(p.id, lvl); reload(); } catch (err: any) { setMsg(err.message); }
  }
  async function revoke(p: any) {
    const who = names.get(p.principal_id) ?? "Diese Entität";
    if (!(await confirmAction({
      title: "Diesen Zugriff entfernen?",
      body: `${who} verliert den Zugriff (${p.access_level}) auf ${names.get(p.resource_id) ?? "die Sammlung"}. Darauf beruhende zwischengespeicherte Antworten werden gelöscht.`,
      confirmLabel: "Zugriff entfernen", danger: true,
    }))) return;
    try { await api.revokePermission(p.id); reload(); } catch (err: any) { setMsg(err.message); }
  }

  return (
    <>
      <PageHeader title="Berechtigungen" intro="Geben Sie einer Person oder Abteilung Zugriff auf eine Sammlung außerhalb der eigenen Abteilung." />
      <form className="toolbar" onSubmit={grant}>
        <select value={principalType} aria-label="Gewähren an" onChange={(e) => { setPT(e.target.value); setPID(""); }}>
          <option value="user">Eine Person</option><option value="department">Eine Abteilung</option>
        </select>
        <select required value={principalId} aria-label={principalType === "user" ? "Person" : "Department"} onChange={(e) => setPID(e.target.value)}>
          <option value="">{principalType === "user" ? "Person wählen" : "Abteilung wählen"}</option>
          {principals?.map((p: any) => <option key={p.id} value={p.id}>{p.email ?? p.name}</option>)}
        </select>
        <select required value={resourceId} aria-label="Sammlung" onChange={(e) => setRID(e.target.value)}>
          <option value="">Sammlung wählen</option>
          {colls.data?.map((c: any) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        <select value={level} aria-label="Zugriffsstufe" onChange={(e) => setLevel(e.target.value)}>
          <option value="read">Darf durchsuchen</option><option value="write">Darf hochladen</option><option value="admin">Darf verwalten</option>
        </select>
        <button className="primary"><Icon name="plus" size={16} />Zugriff gewähren</button>
      </form>
      {msg && <Notice kind="error">{msg}</Notice>}
      {error && <Notice kind="error">{error}</Notice>}
      <div className="table-wrap">
        <table>
          <thead><tr><th>Wer</th><th>Sammlung</th><th>Zugriff</th><th><span className="sr-only">Aktionen</span></th></tr></thead>
          <tbody>
            {data?.length === 0 && <tr><td colSpan={4} className="muted">Kein zusätzlicher Zugriff gewährt. Alle durchsuchen die Sammlungen ihrer eigenen Abteilung.</td></tr>}
            {data?.map((p: any) => (
              <tr key={p.id}>
                <td className="strong">{names.get(p.principal_id) ?? "Unbekannt"} <span className="muted">· {p.principal_type === "user" ? "Person" : "Abteilung"}</span></td>
                <td>{names.get(p.resource_id) ?? "Unbekannte Sammlung"}</td>
                <td>
                  <select value={p.access_level} aria-label="Zugriffsstufe" onChange={(e) => change(p, e.target.value)}>
                    <option value="read">Darf durchsuchen</option><option value="write">Darf hochladen</option><option value="admin">Darf verwalten</option>
                  </select>
                </td>
                <td className="row-actions"><button className="danger" onClick={() => revoke(p)}>Entfernen</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

// -------------------------------------------------------------------- audit --
function Audit() {
  const { data, error, reload } = useData(() => api.auditLogs());
  const users = useData(() => api.users());
  const [filter, setFilter] = useState("");
  const email = useMemo(() => new Map((users.data ?? []).map((u: any) => [u.id, u.email])), [users.data]);
  const human = (a: string) => a.toLowerCase().replace(/_/g, " ");
  const rows = (data ?? []).filter((a: any) => !filter || human(a.action).includes(filter));
  const actions = Array.from(new Set((data ?? []).map((a: any) => human(a.action)))).sort();

  function summary(a: any): string {
    const d = a.detail || {};
    if (d.query) return `„${d.query}"${d.insufficient ? " — kein Beleg gefunden" : ""}`;
    const keys = Object.keys(d).filter((k) => !/(_id|sha256|request_id)$/.test(k));
    return keys.slice(0, 3).map((k) => `${k.replace(/_/g, " ")}: ${typeof d[k] === "object" ? JSON.stringify(d[k]) : d[k]}`).join(" · ");
  }

  return (
    <>
      <PageHeader title="Audit-Protokoll" intro="Wer hat was getan – und wann. Die 200 neuesten Ereignisse.">
        <select value={filter} aria-label="Nach Aktion filtern" onChange={(e) => setFilter(e.target.value)}>
          <option value="">Alle Aktionen</option>
          {actions.map((a) => <option key={a} value={a}>{a}</option>)}
        </select>
        <button onClick={reload}><Icon name="refresh" size={16} />Aktualisieren</button>
      </PageHeader>
      {error && <Notice kind="error">{error}</Notice>}
      <div className="table-wrap">
        <table>
          <thead><tr><th>Wann</th><th>Aktion</th><th>Wer</th><th>Details</th></tr></thead>
          <tbody>
            {rows.map((a: any) => (
              <tr key={a.id}>
                <td className="nowrap muted" title={new Date(a.created_at).toLocaleString()}>{when(a.created_at)}</td>
                <td className="nowrap"><span className="badge">{human(a.action)}</span></td>
                <td className="muted">{a.user_id ? email.get(a.user_id) ?? "Gelöschter Benutzer" : "System"}</td>
                <td className="audit-detail">
                  {summary(a)}
                  {a.detail && (
                    <details><summary>Rohdaten</summary><pre>{JSON.stringify(a.detail, null, 2)}</pre></details>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
