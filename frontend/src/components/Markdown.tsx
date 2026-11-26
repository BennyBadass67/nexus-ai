import { ReactNode, useState } from "react";
import { Check, Copy } from "lucide-react";

function inline(t: string, key: string): ReactNode[] {
  const out: ReactNode[] = [];
  const re = /(`[^`]+`)|(\*\*[^*]+\*\*)|(\*[^*\s][^*]*\*)|(\[[^\]]+\]\(https?:\/\/[^)\s]+\))/g;
  let last = 0, m: RegExpExecArray | null, i = 0;
  while ((m = re.exec(t))) {
    if (m.index > last) out.push(t.slice(last, m.index));
    const s = m[0];
    if (m[1]) out.push(<code key={key + i}>{s.slice(1, -1)}</code>);
    else if (m[2]) out.push(<strong key={key + i}>{s.slice(2, -2)}</strong>);
    else if (m[3]) out.push(<em key={key + i}>{s.slice(1, -1)}</em>);
    else { const mm = /\[([^\]]+)\]\(([^)]+)\)/.exec(s)!; out.push(<a key={key + i} href={mm[2]} target="_blank" rel="noreferrer">{mm[1]}</a>); }
    last = m.index + s.length; i++;
  }
  if (last < t.length) out.push(t.slice(last));
  return out;
}

export function CodeBlock({ code, lang }: { code: string; lang: string }) {
  const [ok, setOk] = useState(false);
  return (
    <div className="my-3 overflow-hidden rounded-xl border border-white/10 bg-black/40">
      <div className="flex items-center justify-between border-b border-white/8 bg-white/5 px-3 py-1.5 text-[11px] text-white/50">
        <span>{lang || "kode"}</span>
        <button className="flex items-center gap-1 transition hover:text-white" onClick={() => { navigator.clipboard.writeText(code); setOk(true); setTimeout(() => setOk(false), 1500); }}>
          {ok ? <><Check size={12} />Kopiert</> : <><Copy size={12} />Kopier</>}</button>
      </div>
      <pre className="overflow-x-auto p-3 text-[13px] leading-relaxed"><code className="!bg-transparent !p-0">{code}</code></pre>
    </div>
  );
}

export default function Markdown({ text }: { text: string }) {
  const lines = text.split("\n");
  const blocks: ReactNode[] = [];
  let i = 0, k = 0;
  while (i < lines.length) {
    const l = lines[i];
    const fence = /^```(\w*)/.exec(l);
    if (fence) {
      const buf: string[] = []; i++;
      while (i < lines.length && !lines[i].startsWith("```")) buf.push(lines[i++]);
      i++; blocks.push(<CodeBlock key={k++} code={buf.join("\n")} lang={fence[1]} />); continue;
    }
    const h = /^(#{1,3})\s+(.*)/.exec(l);
    if (h) { const T = (`h${h[1].length}`) as "h1"; blocks.push(<T key={k++}>{inline(h[2], "h" + k)}</T>); i++; continue; }
    if (/^\s*[-*]\s+/.test(l)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) items.push(lines[i++].replace(/^\s*[-*]\s+/, ""));
      blocks.push(<ul key={k++}>{items.map((t, j) => <li key={j}>{inline(t, `u${k}${j}`)}</li>)}</ul>); continue;
    }
    if (/^\s*\d+[.)]\s+/.test(l)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*\d+[.)]\s+/.test(lines[i])) items.push(lines[i++].replace(/^\s*\d+[.)]\s+/, ""));
      blocks.push(<ol key={k++}>{items.map((t, j) => <li key={j}>{inline(t, `o${k}${j}`)}</li>)}</ol>); continue;
    }
    if (!l.trim()) { i++; continue; }
    const buf: string[] = [];
    while (i < lines.length && lines[i].trim() && !/^(```|#{1,3}\s|\s*[-*]\s+|\s*\d+[.)]\s+)/.test(lines[i])) buf.push(lines[i++]);
    blocks.push(<p key={k++}>{buf.flatMap((t, j) => [j ? <br key={"b" + j} /> : null, ...inline(t, `p${k}${j}`)])}</p>);
  }
  return <div className="md">{blocks}</div>;
}
