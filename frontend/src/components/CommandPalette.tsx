import { useEffect, useMemo, useRef, useState } from "react";
import { Search, CornerDownLeft } from "lucide-react";

export type Cmd = { id: string; label: string; hint?: string; run: () => void };

export default function CommandPalette({ open, onClose, cmds, remote }: { open: boolean; onClose: () => void; cmds: Cmd[]; remote?: (q: string) => Promise<Cmd[]> }) {
  const [q, setQ] = useState(""); const [sel, setSel] = useState(0);
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => { if (open) { setQ(""); setSel(0); setTimeout(() => ref.current?.focus(), 30); } }, [open]);
  const [hits, setHits] = useState<Cmd[]>([]);
  useEffect(() => {
    if (!remote || q.trim().length < 2) { setHits([]); return; }
    let on = true; const t = setTimeout(() => remote(q.trim()).then((r) => on && setHits(r)).catch(() => on && setHits([])), 180);
    return () => { on = false; clearTimeout(t); };
  }, [q]); // eslint-disable-line
  const list = useMemo(() => {
    const local = cmds.filter((c) => (c.label + " " + (c.hint || "")).toLowerCase().includes(q.toLowerCase()));
    const ids = new Set(local.map((c) => c.id));
    return [...local.slice(0, 6), ...hits.filter((h) => !ids.has(h.id))].slice(0, 12);
  }, [q, cmds, hits]);
  if (!open) return null;
  const go = (c?: Cmd) => { if (c) { onClose(); c.run(); } };
  return (
    <div className="fixed inset-0 z-50 grid place-items-start justify-center bg-black/50 pt-[16vh] backdrop-blur-sm animate-fade" onMouseDown={onClose}>
      <div className="glass w-[min(560px,92vw)] animate-pop overflow-hidden rounded-3xl" onMouseDown={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-3 border-b border-white/10 px-5 py-4"><Search size={18} className="text-white/40" />
          <input ref={ref} value={q} onChange={(e) => { setQ(e.target.value); setSel(0); }} placeholder="Gå til, søk samtaler, bytt modell…"
            onKeyDown={(e) => {
              if (e.key === "Escape") onClose();
              if (e.key === "ArrowDown") { e.preventDefault(); setSel((s) => Math.min(s + 1, list.length - 1)); }
              if (e.key === "ArrowUp") { e.preventDefault(); setSel((s) => Math.max(s - 1, 0)); }
              if (e.key === "Enter") go(list[sel]);
            }} className="flex-1 bg-transparent text-[15px] outline-none placeholder:text-white/30" /><span className="kbd">Esc</span></div>
        <div className="max-h-[50vh] overflow-auto p-2">
          {list.length === 0 && <div className="p-6 text-center text-sm text-white/40">Ingen treff</div>}
          {list.map((c, i) => (
            <button key={c.id} onMouseEnter={() => setSel(i)} onClick={() => go(c)}
              className={`flex w-full items-center justify-between rounded-xl px-3.5 py-2.5 text-left text-sm transition ${i === sel ? "bg-white/12" : ""}`}>
              <span>{c.label}</span>
              <span className="flex items-center gap-2 text-xs text-white/40">{c.hint}{i === sel && <CornerDownLeft size={12} />}</span>
            </button>))}
        </div>
      </div>
    </div>
  );
}
