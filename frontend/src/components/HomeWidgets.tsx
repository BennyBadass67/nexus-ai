import { useEffect, useState } from "react";
import { Cpu, MemoryStick, StickyNote, Check, Plus } from "lucide-react";
import { GraduationCap } from "lucide-react";
import { Deck, extrasApi, Note, studyApi, SysMon } from "../api";

const Bar = ({ pct, label, sub }: { pct: number | null; label: string; sub?: string }) => (
  <div>
    <div className="flex items-baseline justify-between text-xs"><span className="font-medium">{label}</span><span className="tabular-nums text-white/60">{pct == null ? "–" : pct + " %"}{sub ? ` · ${sub}` : ""}</span></div>
    <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-white/15"><div className={`h-full rounded-full transition-all duration-700 ${pct != null && pct > 85 ? "bg-rose-600" : "sysbar"}`} style={{ width: `${pct ?? 0}%` }} /></div>
  </div>);

export function SysMonCard() {
  const [s, setS] = useState<SysMon | null>(null);
  useEffect(() => { let on = true; const f = () => extrasApi.sysmon().then((x) => on && setS(x)).catch(() => {}); f(); const t = setInterval(f, 3000); return () => { on = false; clearInterval(t); }; }, []);
  return (
    <div className="glass animate-rise rounded-[26px] p-5">
      <div className="flex items-center gap-2 text-sm font-semibold"><Cpu size={15} />Systemmonitor <span className="ml-auto h-2 w-2 animate-pulse rounded-full bg-emerald-500" /></div>
      <div className="mt-4 space-y-3.5">
        <Bar pct={s?.cpu_pct ?? null} label="Prosessor" />
        <Bar pct={s?.ram_pct ?? null} label="Minne" sub={s?.ram_total_gb ? `${s.ram_used_gb} av ${s.ram_total_gb} GB` : undefined} />
      </div>
      <div className="mt-4 flex items-center gap-2 text-xs text-white/65"><MemoryStick size={13} />
        {s?.loaded == null ? "Ollama svarer ikke" : s.loaded.length === 0 ? "Ingen modell er lastet i minnet akkurat nå" : `I minnet: ${s.loaded.map((m) => `${m.name} (${m.size_gb} GB${m.vram_gb ? `, ${m.vram_gb} på GPU` : ""})`).join(", ")}`}</div>
    </div>);
}

export function NotesCard({ go }: { go: () => void }) {
  const [n, setN] = useState<Note[]>([]); const [t, setT] = useState("");
  const load = () => extrasApi.notes().then(setN).catch(() => {});
  useEffect(() => { load(); }, []);
  const open = n.filter((x) => !x.done);
  const add = () => { if (t.trim()) extrasApi.addNote(t.trim()).then(() => { setT(""); load(); }).catch(() => {}); };
  return (
    <div className="glass animate-rise rounded-[26px] p-5">
      <div className="flex items-center gap-2 text-sm font-semibold"><StickyNote size={15} />Notater<button className="ml-auto text-xs font-normal text-white/60 hover:underline" onClick={go}>Se alle ({open.length})</button></div>
      <div className="mt-3 space-y-1.5">
        {open.slice(0, 3).map((x) => (
          <div key={x.id} className="flex items-center gap-2.5 text-sm">
            <button title="Ferdig" onClick={() => extrasApi.patchNote(x.id, { done: true }).then(load)} className="grid h-5 w-5 flex-none place-items-center rounded-full border border-white/45 transition hover:border-emerald-600 hover:bg-emerald-600 hover:text-white"><Check size={11} strokeWidth={3} className="opacity-0 hover:opacity-100" /></button>
            <span className="truncate">{x.text}</span></div>))}
        {open.length === 0 && <div className="text-xs text-white/60">Ingen åpne notater.</div>}
      </div>
      <div className="mt-3 flex gap-2"><input value={t} onChange={(e) => setT(e.target.value)} onKeyDown={(e) => e.key === "Enter" && add()} maxLength={500} placeholder="Nytt notat…" className="min-w-0 flex-1 rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm outline-none focus:border-nx-blue/60" />
        <button className="btn-primary !px-3" onClick={add} disabled={!t.trim()} title="Legg til"><Plus size={15} /></button></div>
    </div>);
}

export function StudyCard({ go }: { go: () => void }) {
  const [d, setD] = useState<Deck[] | null>(null);
  useEffect(() => { studyApi.decks().then(setD).catch(() => setD([])); }, []);
  if (!d) return null;
  const due = d.reduce((a, x) => a + x.due, 0);
  return (
    <div className="glass animate-rise rounded-[26px] p-5">
      <div className="flex items-center gap-2 text-sm font-semibold"><GraduationCap size={15} />Studie<button className="ml-auto text-xs font-normal text-white/60 hover:underline" onClick={go}>Åpne</button></div>
      {d.length === 0 ? <div className="mt-3 text-xs text-white/60">Lim inn pensum og få øvingskort laget lokalt.</div> :
        <div className="mt-3 flex items-end gap-3"><div className="text-3xl font-semibold tabular-nums">{due}</div><div className="pb-1 text-xs text-white/65">kort å øve på i dag, fordelt på {d.length} {d.length === 1 ? "stokk" : "stokker"}</div></div>}
      <button className="btn mt-3" onClick={go}>{due ? "Øv nå" : "Lag kort"}</button>
    </div>);
}
