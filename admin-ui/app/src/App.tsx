import { useEffect, useState, type FormEvent } from "react";
import { AdminApp } from "./Admin";
import { api, AUTH_EXPIRED, clearTokens, getToken } from "./api";
import { ChatApp } from "./Chat";
import { ConfirmHost } from "./ui";

export default function App() {
  const [token, setTok] = useState<string | null>(getToken());
  const [me, setMe] = useState<any>(null);
  const [notice, setNotice] = useState("");
  const [mode, setMode] = useState<"chat" | "admin">("chat");

  // A session that can't be refreshed ends here, with a clear reason, instead
  // of leaving the UI half-working ("No conversations yet", "stream failed").
  useEffect(() => {
    const onExpired = () => {
      setTok(null); setMe(null); setMode("chat");
      setNotice("Your session has expired. Sign in to continue.");
    };
    window.addEventListener(AUTH_EXPIRED, onExpired);
    return () => window.removeEventListener(AUTH_EXPIRED, onExpired);
  }, []);

  useEffect(() => {
    if (!token) { setMe(null); return; }
    api.me().then(setMe).catch(() => { clearTokens(); setTok(null); });
  }, [token]);

  async function logout() {
    await api.logout();
    setTok(null); setMe(null); setMode("chat"); setNotice("");
  }

  let screen;
  if (!token) {
    screen = <Login notice={notice} onLogin={(t) => { setNotice(""); setTok(t); }} />;
  } else if (!me) {
    screen = <div className="boot" role="status"><span className="mark" aria-hidden="true">R</span></div>;
  } else if (mode === "admin" && me.role === "admin") {
    screen = <AdminApp email={me.email} onExit={() => setMode("chat")} onLogout={logout} />;
  } else {
    screen = <ChatApp email={me.email} isAdmin={me.role === "admin"} onAdmin={() => setMode("admin")} onLogout={logout} />;
  }
  return <>{screen}<ConfirmHost /></>;
}

function Login({ onLogin, notice }: { onLogin: (t: string) => void; notice: string }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => { document.title = "Sign in · Recherche"; }, []);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true); setError("");
    try { const r = await api.login(email.trim(), password); onLogin(r.access_token); }
    catch (err: any) { setError(err.message || "Sign-in failed."); }
    finally { setBusy(false); }
  }

  return (
    <div className="login">
      <form onSubmit={submit} aria-labelledby="signin-title">
        <div className="brand"><span className="mark" aria-hidden="true">R</span>Recherche</div>
        <h1 id="signin-title">Sign in</h1>
        <p className="login-sub">Ask questions about your organization's documents. Every answer shows the page it came from.</p>
        {notice && !error && <p className="login-notice" role="status">{notice}</p>}
        <label htmlFor="email">Work email</label>
        <input id="email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)}
          autoComplete="username" autoFocus />
        <label htmlFor="pw">Password</label>
        <input id="pw" type="password" required value={password} onChange={(e) => setPassword(e.target.value)}
          autoComplete="current-password" />
        {error && <p className="login-error" role="alert">{error}</p>}
        <button className="primary" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
      </form>
    </div>
  );
}
