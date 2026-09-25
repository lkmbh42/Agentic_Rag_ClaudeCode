// Shared UI: confirmation dialog, authenticated images, lightbox, data hook.

import { useEffect, useRef, useState, type ReactNode } from "react";
import { api, ApiError } from "./api";
import { Icon } from "./icons";

// ---------------------------------------------------------------- confirm ---
type ConfirmReq = {
  title: string;
  body?: ReactNode;
  confirmLabel: string;
  danger?: boolean;
  resolve: (ok: boolean) => void;
};
let showConfirm: ((r: ConfirmReq) => void) | null = null;

/** Ask before a consequential action. Resolves true only on explicit confirm. */
export function confirmAction(o: Omit<ConfirmReq, "resolve">): Promise<boolean> {
  return new Promise((resolve) => {
    if (showConfirm) showConfirm({ ...o, resolve });
    else resolve(window.confirm(o.title));
  });
}

export function ConfirmHost() {
  const [req, setReq] = useState<ConfirmReq | null>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  useEffect(() => { showConfirm = setReq; return () => { showConfirm = null; }; }, []);
  useEffect(() => { if (req) cancelRef.current?.focus(); }, [req]);
  if (!req) return null;
  const done = (ok: boolean) => { req.resolve(ok); setReq(null); };
  return (
    <div className="modal-backdrop" onMouseDown={() => done(false)}
      onKeyDown={(e) => { if (e.key === "Escape") done(false); }}>
      <div className="modal" role="alertdialog" aria-modal="true" aria-labelledby="confirm-title"
        onMouseDown={(e) => e.stopPropagation()}>
        <h2 id="confirm-title">{req.title}</h2>
        {req.body && <div className="modal-body">{req.body}</div>}
        <div className="modal-actions">
          <button ref={cancelRef} type="button" onClick={() => done(false)}>Abbrechen</button>
          <button type="button" className={req.danger ? "danger-solid" : "primary"}
            onClick={() => done(true)}>{req.confirmLabel}</button>
        </div>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ images ---
/** <img> fetched through the JWT-authenticated API (a plain src can't carry the
 *  bearer token). Missing/forbidden images render nothing. */
export function AuthImage({ path, alt, className, onClick }:
  { path: string; alt: string; className?: string; onClick?: () => void }) {
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let revoke: string | null = null;
    let live = true;
    setUrl(null); setFailed(false);
    api.fetchImage(path).then((u) => {
      if (!live) { if (u) URL.revokeObjectURL(u); return; }
      if (u) { revoke = u; setUrl(u); } else setFailed(true);
    });
    return () => { live = false; if (revoke) URL.revokeObjectURL(revoke); };
  }, [path]);
  if (failed) return null;
  if (!url) return <span className={`img-loading ${className ?? ""}`} aria-label="Bild wird geladen" />;
  const img = <img className={className} src={url} alt={alt} />;
  return onClick
    ? <button type="button" className="img-button" onClick={onClick} aria-label={`Vergrößern: ${alt}`}>{img}</button>
    : img;
}

/** Full-screen view of one figure. Closes on Escape, the close button, or a
 *  click outside the image. */
export function Lightbox({ path, alt, onClose }: { path: string; alt: string; onClose: () => void }) {
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="lightbox" onClick={onClose} role="dialog" aria-modal="true" aria-label={alt}>
      <button ref={closeRef} className="icon-btn lightbox-close" onClick={onClose} aria-label="Schließen">
        <Icon name="close" />
      </button>
      <div className="lightbox-stage" onClick={(e) => e.stopPropagation()}>
        <AuthImage path={path} className="lightbox-img" alt={alt} />
      </div>
    </div>
  );
}

// -------------------------------------------------------------------- data ---
export function useData<T>(loader: () => Promise<T>, deps: any[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let live = true;
    loader()
      .then((d) => { if (live) { setData(d); setError(""); } })
      .catch((e: ApiError) => { if (live) setError(e.message); });
    return () => { live = false; };
  }, [tick, ...deps]);
  return { data, error, reload: () => setTick((t) => t + 1) };
}

export function Notice({ kind = "info", children }: { kind?: "info" | "error" | "ok"; children: ReactNode }) {
  return (
    <div className={`notice ${kind}`} role={kind === "error" ? "alert" : "status"}>
      {kind === "error" && <Icon name="alert" size={16} />}
      <span>{children}</span>
    </div>
  );
}

export function PageHeader({ title, intro, children }: { title: string; intro?: string; children?: ReactNode }) {
  return (
    <header className="page-header">
      <div>
        <h1>{title}</h1>
        {intro && <p className="page-intro">{intro}</p>}
      </div>
      {children && <div className="page-actions">{children}</div>}
    </header>
  );
}

/** "3 min ago" / "yesterday" / a date — for lists where recency matters. */
export function when(iso: string): string {
  const d = new Date(iso);
  const s = (Date.now() - d.getTime()) / 1000;
  if (s < 60) return "gerade eben";
  if (s < 3600) return `vor ${Math.floor(s / 60)} Min.`;
  if (s < 86400) return `vor ${Math.floor(s / 3600)} Std.`;
  if (s < 172800) return "gestern";
  return d.toLocaleDateString("de-DE", { day: "numeric", month: "short", year: d.getFullYear() === new Date().getFullYear() ? undefined : "numeric" });
}
