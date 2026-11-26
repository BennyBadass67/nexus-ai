import { useCallback, useEffect, useState } from "react";
import { Brain, Pin, PinOff, Trash2, Plus, Search, Bot, User, Loader2 } from "lucide-react";
import { memApi, Mem, MemList } from "../api";

const KINDS: { id: Mem["kind"]; label: string }[] = [
  { id: "fact", label: "Fakta" }, { id: "preference", label: "Preferanse" }, { id: "decision", label: "Beslutning" }, { id: "project", label: "Prosjekt" }];

export default function MemoryPage() {
  const [d, setD] = useState<MemList | null>(null);
  const [q, setQ] = useState("");
  const [text, setText] = useState("");
  const [kind, setKind] = useState<Mem["kind"]>("fact");
  const [err, setErr] = useState("");
  const [edit, setEdit] = useState<{ id: number; v: string } | null>(null);
  const [filter, setFilter] = useState<"all" | Mem["kind"]>("all");
  const load = useCallback(() => memApi.list(q).then(setD).catch((e) => setErr(String(e))), [q]);
  useEffect(() => { const t = setTimeout(load, 200); return () => clearTimeout(t); }, [load]);
  const guard = (p: Promise<unknown>) => p.then(load).catch((e) => setErr(String(e).replace(/^Error: \d+ /, "")));
  const add = () => { if (!text.trim()) return; setErr(""); guard(memApi.add(text.trim(), kind).then(() => setText(""))); };
  const items = (d?.items ?? []).filter((m) => filter === "all" || m.kind === filter);
  return (
    <div className="glass flex h-full flex-col overflow-hidden rounded-[28px] p-6">
      <div className="flex flex-wrap items-center gap-3">
        <div><h1 className="text-xl font-semibold">Memory</h1>
          <p className="text-sm text-white/50">Det agenten husker om deg. Lagret lokalt. Du kan se, endre og slette alt.</p></div>
        <label className="ml-auto flex cursor-pointer items-center gap-2 text-sm text-white/70">
          <input type="checkbox" checked={d?.enabled ?? true} onChange={(e) => guard(memApi.enable(e.target.checked))} className="accent-[rgb(var(--accent))]" />
          Bruk minnet i samtaler</label>
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        <input value={text} onChange={(e) => setText(e.target.value)} onKeyDown={(e) => e.key === "Enter" && add()} maxLength={500} placeholder="Noe agenten skal huske, f.eks. «Jeg bor i Oslo»"
          className="min-w-[240px] flex-1 rounded-2xl glass-soft px-4 py-2.5 text-sm outline-none placeholder:text-white/30" />
        <select value={kind} onChange={(e) => setKind(e.target.value as Mem["kind"])} className="rounded-2xl glass-soft px-3 py-2.5 text-sm outline-none">
          {KINDS.map((k) => <option key={k.id} value={k.id} className="bg-[#0b1220]">{k.label}</option>)}</select>
        <button onClick={add} disabled={!text.trim()} className="flex items-center gap-2 rounded-2xl bg-nx-blue px-4 py-2.5 text-sm font-medium text-[#04101f] disabled:opacity-40"><Plus size={15} />Legg til</button>
      </div>
      {err && <div className="mt-2 text-sm text-rose-300">{err}</div>}
      <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
        <div className="flex items-center gap-2 rounded-full glass-soft px-3 py-1.5"><Search size={12} className="text-white/40" />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Søk" className="w-32 bg-transparent outline-none placeholder:text-white/30" /></div>
        {[{ id: "all", label: "Alle" }, ...KINDS].map((k) => (
          <button key={k.id} onClick={() => setFilter(k.id as typeof filter)} className={`rounded-full px-3 py-1.5 transition ${filter === k.id ? "bg-white/15 text-white" : "glass-soft text-white/55 hover:text-white"}`}>{k.label}</button>))}
        <span className="ml-auto text-white/40">{d ? `${d.items.length} av ${d.limit} · ${d.context_chars} tegn sendes til modellen` : ""}</span>
        {d && d.items.length > 0 && <button onClick={() => { if (confirm("Slette ALLE minner? Dette kan ikke angres.")) guard(memApi.clear()); }} className="text-rose-300/80 hover:text-rose-300">Slett alle</button>}
      </div>
      <div className="mt-3 flex-1 space-y-1.5 overflow-auto pr-1">
        {!d && <Loader2 className="animate-spin text-white/40" />}
        {d && items.length === 0 && <div className="glass-soft grid place-items-center gap-2 rounded-2xl p-8 text-center text-sm text-white/55"><Brain size={22} className="text-nx-blue" />
          {d.items.length === 0 ? "Ingen minner ennå. Legg til ett over, eller si «husk at …» til agenten i agent-modus." : "Ingen treff."}</div>}
        {items.map((m) => (
          <div key={m.id} className="glass-soft group flex items-center gap-3 rounded-xl px-4 py-2.5 text-sm">
            <span title={m.source === "agent" ? "Lagret av agenten" : "Lagt inn av deg"} className="text-white/35">{m.source === "agent" ? <Bot size={14} /> : <User size={14} />}</span>
            {edit?.id === m.id ? (
              <input autoFocus value={edit.v} maxLength={500} onChange={(e) => setEdit({ id: m.id, v: e.target.value })}
                onKeyDown={(e) => { if (e.key === "Enter" && edit.v.trim()) guard(memApi.patch(m.id, { content: edit.v.trim() }).then(() => setEdit(null))); if (e.key === "Escape") setEdit(null); }}
                onBlur={() => setEdit(null)} className="flex-1 bg-transparent outline-none" />
            ) : <span className="flex-1 cursor-text" onClick={() => setEdit({ id: m.id, v: m.content })}>{m.content}</span>}
            <select value={m.kind} onChange={(e) => guard(memApi.patch(m.id, { kind: e.target.value as Mem["kind"] }))} className="rounded-lg bg-transparent text-xs text-white/50 outline-none">
              {KINDS.map((k) => <option key={k.id} value={k.id} className="bg-[#0b1220]">{k.label}</option>)}</select>
            <button title={m.pinned ? "Løsne" : "Fest (kommer alltid med)"} onClick={() => guard(memApi.patch(m.id, { pinned: !m.pinned }))} className={m.pinned ? "text-nx-blue" : "text-white/30 hover:text-white"}>{m.pinned ? <Pin size={14} /> : <PinOff size={14} />}</button>
            <button title="Slett" onClick={() => guard(memApi.del(m.id))} className="text-white/30 hover:text-rose-300"><Trash2 size={14} /></button>
          </div>))}
      </div>
    </div>
  );
}
