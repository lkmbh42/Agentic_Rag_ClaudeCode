// Minimal, safe Markdown for model answers. Builds React elements only — no
// raw HTML, no dangerouslySetInnerHTML, no links — so text from documents or
// the model can never inject markup. Supports what the generator actually
// writes: paragraphs, **bold**, *italic*, `code`, headings, bullet/numbered
// lists, pipe tables, fenced code, and [n] / [1, 2] citation markers, which are
// handed to `cite` so the chat can make them open the source.

import type { ReactNode } from "react";

export type CiteRenderer = (marker: number, key: string) => ReactNode;

// Also accepts gpt-oss's native "【1†L1-L2】" markers (the backend normalizes
// final answers, but streamed tokens arrive raw).
const INLINE = /(\*\*[^*]+?\*\*|`[^`]+`|\*[^*\s][^*]*?\*|\[\d+(?:\s*,\s*\d+)*\]|【\s*\d+\s*(?:†[^】]*)?】)/g;

function inline(text: string, cite: CiteRenderer, kp: string): ReactNode[] {
  const out: ReactNode[] = [];
  let last = 0;
  let i = 0;
  for (const m of text.matchAll(INLINE)) {
    const tok = m[0];
    const at = m.index ?? 0;
    if (at > last) out.push(text.slice(last, at));
    const k = `${kp}.${i++}`;
    if (tok.startsWith("**")) out.push(<strong key={k}>{inline(tok.slice(2, -2), cite, k)}</strong>);
    else if (tok.startsWith("`")) out.push(<code key={k}>{tok.slice(1, -1)}</code>);
    else if (tok.startsWith("[")) {
      tok.slice(1, -1).split(",").forEach((n, j) => out.push(cite(Number(n.trim()), `${k}.${j}`)));
    } else if (tok.startsWith("【")) out.push(cite(parseInt(tok.slice(1), 10), k));
    else out.push(<em key={k}>{inline(tok.slice(1, -1), cite, k)}</em>);
    last = at + tok.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

function lines(parts: string[], cite: CiteRenderer, kp: string): ReactNode[] {
  return parts.flatMap((l, i) => i === 0
    ? inline(l, cite, `${kp}l${i}`)
    : [<br key={`${kp}br${i}`} />, ...inline(l, cite, `${kp}l${i}`)]);
}

const BULLET = /^(\s*)([-*•]|\d+[.)])\s+/;
const NUMERIC = /^[\s\d.,%€+\-–:/]+$/;
const cells = (row: string) =>
  row.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => c.trim());

export function Markdown({ text, cite }: { text: string; cite: CiteRenderer }) {
  const src = text.replace(/\r/g, "").split("\n");
  const blocks: ReactNode[] = [];
  const para: string[] = [];
  let b = 0;
  const flush = () => {
    if (!para.length) return;
    const k = `p${b++}`;
    blocks.push(<p key={k}>{lines(para, cite, k)}</p>);
    para.length = 0;
  };

  for (let i = 0; i < src.length;) {
    const t = src[i].trim();
    if (!t) { flush(); i++; continue; }

    if (t.startsWith("```")) {                                   // fenced code
      flush();
      const body: string[] = [];
      for (i++; i < src.length && !src[i].trim().startsWith("```"); i++) body.push(src[i]);
      i++;
      blocks.push(<pre key={`c${b++}`}><code>{body.join("\n")}</code></pre>);
      continue;
    }

    const h = /^(#{1,4})\s+(.*)$/.exec(t);                       // heading
    if (h) {
      flush();
      const k = `h${b++}`;
      const level = h[1].length <= 2 ? "h3" : "h4";
      blocks.push(level === "h3" ? <h3 key={k}>{inline(h[2], cite, k)}</h3> : <h4 key={k}>{inline(h[2], cite, k)}</h4>);
      i++;
      continue;
    }

    if (t.startsWith("|") && i + 1 < src.length && /^\|?\s*:?-{2,}/.test(src[i + 1].trim())) {
      flush();                                                   // pipe table
      const head = cells(src[i]);
      const rows: string[][] = [];
      for (i += 2; i < src.length && src[i].trim().startsWith("|"); i++) rows.push(cells(src[i]));
      const k = `t${b++}`;
      blocks.push(
        <div className="md-table" key={k}>
          <table>
            <thead><tr>{head.map((c, j) => <th key={j}>{inline(c, cite, `${k}h${j}`)}</th>)}</tr></thead>
            <tbody>
              {rows.map((r, ri) => (
                <tr key={ri}>{r.map((c, j) => (
                  <td key={j} className={NUMERIC.test(c) && /\d/.test(c) ? "num" : undefined}>
                    {inline(c, cite, `${k}r${ri}c${j}`)}
                  </td>
                ))}</tr>
              ))}
            </tbody>
          </table>
        </div>,
      );
      continue;
    }

    if (BULLET.test(src[i])) {                                   // list
      flush();
      const ordered = /^\s*\d/.test(src[i]);
      const start = ordered ? parseInt(t, 10) : undefined;
      const items: { text: string[]; nested: boolean }[] = [];
      while (i < src.length && src[i].trim()) {
        const m = BULLET.exec(src[i]);
        if (m) {
          items.push({ text: [src[i].slice(m[0].length).trim()], nested: m[1].length >= 2 });
        } else if (/^\s+/.test(src[i]) && items.length) {
          items[items.length - 1].text.push(src[i].trim());      // wrapped item line
        } else break;
        i++;
      }
      const k = `l${b++}`;
      const lis = items.map((it, j) => (
        <li key={j} className={it.nested ? "nested" : undefined}>{lines(it.text, cite, `${k}i${j}`)}</li>
      ));
      blocks.push(ordered ? <ol key={k} start={start}>{lis}</ol> : <ul key={k}>{lis}</ul>);
      continue;
    }

    if (t.startsWith(">")) {                                     // quote
      flush();
      const q: string[] = [];
      for (; i < src.length && src[i].trim().startsWith(">"); i++) q.push(src[i].trim().replace(/^>\s?/, ""));
      const k = `q${b++}`;
      blocks.push(<blockquote key={k}>{lines(q, cite, k)}</blockquote>);
      continue;
    }

    para.push(t);
    i++;
  }
  flush();
  return <>{blocks}</>;
}
