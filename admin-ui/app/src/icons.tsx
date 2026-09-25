// Inline stroke icons (24-unit grid, currentColor). Local SVG keeps the app
// air-gap safe — no icon font or CDN.

const PATHS: Record<string, JSX.Element> = {
  plus: <path d="M12 5v14M5 12h14" />,
  send: <path d="M12 19V5M5.5 11.5 12 5l6.5 6.5" />,
  stop: <rect x="7" y="7" width="10" height="10" rx="1.5" fill="currentColor" stroke="none" />,
  copy: <><rect x="9" y="9" width="11" height="11" rx="2" /><path d="M15 9V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h3" /></>,
  check: <path d="m5 12.5 4.5 4.5L19 7.5" />,
  up: <path d="M7 11v9H4.5A1.5 1.5 0 0 1 3 18.5v-6A1.5 1.5 0 0 1 4.5 11H7Zm0 0 3.6-6.3a1.6 1.6 0 0 1 3 .9L13 10h5.2a2 2 0 0 1 2 2.3l-1 6.1A2 2 0 0 1 17.2 20H7" />,
  down: <path d="M17 13V4h2.5A1.5 1.5 0 0 1 21 5.5v6a1.5 1.5 0 0 1-1.5 1.5H17Zm0 0-3.6 6.3a1.6 1.6 0 0 1-3-.9L11 14H5.8a2 2 0 0 1-2-2.3l1-6.1A2 2 0 0 1 6.8 4H17" />,
  search: <><circle cx="11" cy="11" r="6.5" /><path d="m20 20-4.2-4.2" /></>,
  menu: <path d="M4 7h16M4 12h16M4 17h16" />,
  close: <path d="M6.5 6.5 17.5 17.5M17.5 6.5 6.5 17.5" />,
  doc: <><path d="M14 3.5H7.5a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2h9a2 2 0 0 0 2-2V8Z" /><path d="M14 3.5V8h4.5" /></>,
  image: <><rect x="3.5" y="5" width="17" height="14" rx="2" /><circle cx="9" cy="10" r="1.6" /><path d="m20.5 15.5-4.5-4.5-8.5 8" /></>,
  table: <><rect x="3.5" y="4.5" width="17" height="15" rx="2" /><path d="M3.5 10h17M3.5 15h17M10 10v9.5" /></>,
  shield: <path d="M12 3.5 19 6v5.5c0 4.3-2.9 7.4-7 9-4.1-1.6-7-4.7-7-9V6Z" />,
  out: <><path d="M14 4.5h3.5a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H14" /><path d="M10 16.5 5.5 12 10 7.5M5.5 12H15" /></>,
  back: <path d="M14.5 6 8.5 12l6 6" />,
  refresh: <><path d="M19.5 12a7.5 7.5 0 1 1-2.2-5.3" /><path d="M19.5 4.5v4.2h-4.2" /></>,
  upload: <><path d="M12 15V4.5M7.5 9 12 4.5 16.5 9" /><path d="M4.5 15v3a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2v-3" /></>,
  expand: <path d="M14 4.5h5.5V10M10 19.5H4.5V14M19.5 4.5 13 11M4.5 19.5 11 13" />,
  alert: <><path d="M12 4 21 19.5H3Z" /><path d="M12 10v4M12 16.8v.2" /></>,
  trash: <><path d="M4.5 6.5h15M9 6.5V5a1.5 1.5 0 0 1 1.5-1.5h3A1.5 1.5 0 0 1 15 5v1.5" /><path d="M6.5 6.5 7.3 19a1.5 1.5 0 0 0 1.5 1.4h6.4a1.5 1.5 0 0 0 1.5-1.4l.8-12.5" /></>,
};

export function Icon({ name, size = 18, label }: { name: string; size?: number; label?: string }) {
  return (
    <svg className="icon" width={size} height={size} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round"
      role={label ? "img" : undefined} aria-label={label} aria-hidden={label ? undefined : true}>
      {PATHS[name]}
    </svg>
  );
}
