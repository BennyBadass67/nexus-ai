import { useEffect, useState } from "react";
import { Check, Plus, Trash2, StickyNote, FileText, Bot } from "lucide-react";
import { extrasApi, Note, Tpl } from "../api";

export default function NotesPage() {
  const [tab, setTab] = useState<"notes" | "tpl">("notes");
  const [notes, setNotes] = useState<Note[]>([]); const [tpls, setTpls] = useState<Tpl[]>([]);
  const [text, setText] = useState(""); const [due, setDue] = useState(""); const [tt, setTt] = useState(""); const [tb, setTb] = useState(""); const [err, setErr] = useState("");
  const load = () => { extrasApi.notes().then(setNotes).catch((e) => setErr(String(e))); extrasApi.templates().then(setTpls).catch(() => {}); };
  useEffect(load, []);
  const add = async () => { if (!text.trim()) return; try { await extrasApi.addNote(text.trim(), due); setText(""); setDue(""); load(); } catch (e) { setErr(String(e).replace(/^Error: \d+ /, "")); } };
  const addT = async () => { if (!tt.trim() || !tb.trim()) return; try { await extrasApi.addTemplate(tt.trim(), tb.trim()); setTt(""); setTb(""); load(); } catch (e) { setErr(String(e).replace(/^Error: \d+ /, "")); } };
  const open = notes.filter((n) => !n.done), done = notes.filter((n) => n.done);
  const field = "rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm outline-none focus:border-nx-blue/60";
  return (
    <div className="glass flex h-full flex-col overflow-hidden rounded-[28px] p-6">
      <div className="flex items-center gap-3">
        <div><h1 className="text-xl font-semibold">Notater</h1><p className="text-sm text-white/55">Oppgaver og lapper. Agenten kan legge til og lese dem når du ber den om det.</p></div>
        <div className="ml-auto flex gap-1 rounded-2xl glass-soft p-1 text-sm">
          {([["notes", "Notater", StickyNote], ["tpl", "Maler", FileText]] as const).map(([id, l, I]) => (
            <button key={id} onClick={() => setTab(id)} className={`flex items-center gap-1.5 rounded-xl px-3 py-1.5 transition ${tab === id ? "bg-white/15 font-medium" : "text-white/60"}`}><I size={14} />{l}</button>))}
        </div>
      </div>
      {err && <div className="mt-2 text-sm text-rose-300">{err}</div>}
      {tab === "notes" ? (
        <div className="mt-4 flex min-h-0 flex-1 flex-col">
          <div className="flex flex-wrap gap-2">
            <input className={`${field} min-w-[200px] flex-1`} placeholder="Nytt notat eller oppgave…" value={text} maxLength={500} onChange={(e) => setText(e.target.value)} onKeyDown={(e) => e.key === "Enter" && add()} />
            <input className={`${field} w-40`} type="date" value={due} onChange={(e) => setDue(e.target.value)} title="Frist (valgfri)" />
            <button className="btn-primary flex items-center gap-1.5" disabled={!text.trim()} onClick={add}><Plus size={15} />Legg til</button>
          </div>
          <div className="mt-4 min-h-0 flex-1 space-y-2 overflow-auto pr-1">
            {notes.length === 0 && <div className="py-16 text-center text-sm text-white/55">Ingen notater ennå. Skriv ett over, eller si til agenten: «noter at jeg må ringe tannlegen».</div>}
            {[...open, ...done].map((n) => (
              <div key={n.id} className="note-row group flex animate-rise items-center gap-3 rounded-2xl glass-soft px-4 py-3">
                <button onClick={() => extrasApi.patchNote(n.id, { done: !n.done }).then(load)} title={n.done ? "Åpne igjen" : "Ferdig"}
                  className={`grid h-6 w-6 flex-none place-items-center rounded-full border transition ${n.done ? "border-emerald-600 bg-emerald-600 text-white" : "border-white/40 hover:border-nx-blue"}`}>{n.done && <Check size={13} strokeWidth={3} />}</button>
                <div className={`min-w-0 flex-1 text-sm ${n.done ? "line-through opacity-60" : ""}`}>{n.text}
                  {n.due && <span className="ml-2 rounded-full bg-white/12 px-2 py-0.5 text-[11px]">frist {n.due}</span>}
                  {n.source === "agent" && <span className="ml-2 inline-flex items-center gap-1 text-[11px] text-white/55"><Bot size={11} />lagt til av agenten</span>}</div>
                <button onClick={() => extrasApi.delNote(n.id).then(load)} title="Slett" className="rounded-lg p-1.5 text-white/50 opacity-0 transition hover:bg-white/10 hover:text-white group-hover:opacity-100"><Trash2 size={14} /></button>
              </div>))}
          </div>
        </div>
      ) : (
        <div className="mt-4 flex min-h-0 flex-1 flex-col">
          <div className="grid gap-2 md:grid-cols-[200px_1fr_auto]">
            <input className={field} placeholder="Navn, f.eks. Oppsummer" value={tt} maxLength={60} onChange={(e) => setTt(e.target.value)} />
            <input className={field} placeholder="Teksten som settes inn i chatten" value={tb} maxLength={4000} onChange={(e) => setTb(e.target.value)} onKeyDown={(e) => e.key === "Enter" && addT()} />
            <button className="btn-primary flex items-center gap-1.5" disabled={!tt.trim() || !tb.trim()} onClick={addT}><Plus size={15} />Lagre mal</button>
          </div>
          <div className="mt-4 min-h-0 flex-1 space-y-2 overflow-auto pr-1">
            {tpls.length === 0 && <div className="py-16 text-center text-sm text-white/55">Ingen maler ennå. Lag en over, så dukker den opp i chatten med ett klikk.</div>}
            {tpls.map((t) => (
              <div key={t.id} className="group flex animate-rise items-start gap-3 rounded-2xl glass-soft px-4 py-3">
                <div className="min-w-0 flex-1"><div className="text-sm font-medium">{t.title}</div><div className="mt-0.5 line-clamp-2 text-xs text-white/60">{t.body}</div></div>
                <button onClick={() => extrasApi.delTemplate(t.id).then(load)} title="Slett" className="rounded-lg p-1.5 text-white/50 opacity-0 transition hover:bg-white/10 hover:text-white group-hover:opacity-100"><Trash2 size={14} /></button>
              </div>))}
          </div>
        </div>)}
    </div>
  );
}
