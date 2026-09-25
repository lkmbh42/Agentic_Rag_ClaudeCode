import { useCallback, useEffect, useState, type FormEvent } from "react";
import { AdminApp } from "./Admin";
import { api, AUTH_EXPIRED } from "./api";
import { ChatApp } from "./Chat";
import { ConfirmHost } from "./ui";

type Phase = "booting" | "in" | "out";

export default function App() {
  const [phase, setPhase] = useState<Phase>("booting");
  const [me, setMe] = useState<any>(null);
  const [notice, setNotice] = useState("");
  const [mode, setMode] = useState<"chat" | "admin">("chat");

  const enter = useCallback(async () => {
    const user = await api.me();
    setMe(user); setMode("chat"); setPhase("in");
  }, []);

  // On load the access token is gone (memory-only), so silently resume from the
  // refresh cookie before choosing between the app and the sign-in screen.
  useEffect(() => {
    let live = true;
    api.restore()
      .then((ok) => ok ? enter() : Promise.reject())
      .catch(() => { if (live) setPhase("out"); });
    return () => { live = false; };
  }, [enter]);

  // A session that can't be refreshed ends here with a clear reason, rather than
  // leaving the UI half-working ("No conversations yet", "stream failed").
  useEffect(() => {
    const onExpired = () => {
      setMe(null); setMode("chat"); setPhase("out");
      setNotice("Ihre Sitzung ist abgelaufen. Bitte melden Sie sich erneut an.");
    };
    window.addEventListener(AUTH_EXPIRED, onExpired);
    return () => window.removeEventListener(AUTH_EXPIRED, onExpired);
  }, []);

  async function logout() {
    await api.logout();
    setMe(null); setMode("chat"); setNotice(""); setPhase("out");
  }

  let screen;
  if (phase === "booting") {
    screen = <div className="boot" role="status" aria-label="Wird geladen"><span className="mark" aria-hidden="true">R</span></div>;
  } else if (phase === "out" || !me) {
    screen = <Login notice={notice} onLogin={() => { setNotice(""); enter(); }} />;
  } else if (mode === "admin" && me.role === "admin") {
    screen = <AdminApp email={me.email} onExit={() => setMode("chat")} onLogout={logout} />;
  } else {
    screen = <ChatApp email={me.email} isAdmin={me.role === "admin"} onAdmin={() => setMode("admin")} onLogout={logout} />;
  }
  return <>{screen}<ConfirmHost /></>;
}

function Login({ onLogin, notice }: { onLogin: () => void; notice: string }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => { document.title = "Anmelden · Recherche"; }, []);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true); setError("");
    try { await api.login(email.trim(), password); onLogin(); }
    catch (err: any) { setError(err.message || "Anmeldung fehlgeschlagen."); }
    finally { setBusy(false); }
  }

  return (
    <div className="login">
      <form onSubmit={submit} aria-labelledby="signin-title">
        <div className="brand"><span className="mark" aria-hidden="true">R</span>Recherche</div>
        <h1 id="signin-title">Anmelden</h1>
        <p className="login-sub">Stellen Sie Fragen zu den Dokumenten Ihrer Organisation. Jede Antwort zeigt die Seite, aus der sie stammt.</p>
        {notice && !error && <p className="login-notice" role="status">{notice}</p>}
        <label htmlFor="email">E-Mail-Adresse</label>
        <input id="email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)}
          autoComplete="username" autoFocus />
        <label htmlFor="pw">Passwort</label>
        <input id="pw" type="password" required value={password} onChange={(e) => setPassword(e.target.value)}
          autoComplete="current-password" />
        {error && <p className="login-error" role="alert">{error}</p>}
        <button className="primary" disabled={busy}>{busy ? "Anmeldung läuft…" : "Anmelden"}</button>
      </form>
    </div>
  );
}
