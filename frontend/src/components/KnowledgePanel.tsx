import { useEffect, useState } from "react";
import { Database, Loader2, Search, Trash2, FileText, Sparkles } from "lucide-react";
import { extrasApi, KHit, studyApi } from "../api";
import { useApp } from "../store";

export default function KnowledgePanel() {
  const { model } = useApp();
  const [ans, setAns] = useState<{ text: string; srcs: string[]; busy: boolean } | null>(null);
  const ask = async () => { if (q.trim().length < 2 || !model) return; setAns({ text: "", srcs: [], busy: true }); try { const s = await studyApi.ask(model, q.trim(), (t) => setAns((a) => a && { ...a, text: a.text + t })); setAns((a) => a && { ...a, srcs: s, busy: false }); } catch (e) { setAns({ text: "Feilet: " + String(e).replace(/^Error: /, "").replace(/^\{"detail":"(.*)"\}$/, "$1"), srcs: [], busy: false }); } };
  const [st, setSt] = useState<{ files: number; chunks: number } | null>(null);
  const [busy, setBusy] = useState(false); const [msg, setMsg] = useState(""); const [q, setQ] = useState(""); const [hits, setHits] = useState<KHit[] | null>(null);
  useEffect(() => { extrasApi.kStatus().then(setSt).catch(() => {}); }, []);
  const index = async () => { setBusy(true); setMsg(""); try { const r = await extrasApi.kIndex(); setSt({ files: r.files, chunks: r.chunks }); setMsg(`Ferdig: ${r.added} nye, ${r.updated} oppdatert, ${r.removed} fjernet${r.skipped ? `, ${r.skipped} hoppet over (for store eller ikke tekst)` : ""}.`); } catch (e) { setMsg("Feilet: " + String(e).replace(/^Error: \d+ /, "")); } finally { setBusy(false); } };
  const search = async () => { if (q.trim().length < 2) return; try { setHits(await extrasApi.kSearch(q.trim())); } catch (e) { setMsg(String(e)); } };
  return (
    <div className="mt-4 flex min-h-0 flex-1 flex-col">
      <div className="flex flex-wrap items-center gap-3 rounded-2xl glass-soft p-4">
        <span className="grid h-10 w-10 place-items-center rounded-full bg-white/15"><Database size={18} /></span>
        <div className="min-w-0 flex-1"><div className="text-sm font-medium">Kunnskapsbase (lokal)</div>
          <div className="text-xs text-white/60">{st ? `${st.files} filer, ${st.chunks} utdrag indeksert` : "…"}. Teksten forlater aldri PC-en. Agenten bruker den via «search_knowledge».</div></div>
        <button className="btn-primary flex items-center gap-2" disabled={busy} onClick={index}>{busy ? <Loader2 size={14} className="animate-spin" /> : <Database size={14} />}{busy ? "Indekserer…" : st?.files ? "Oppdater indeks" : "Indekser mappene"}</button>
        {!!st?.files && <button className="btn" title="Tøm indeksen" onClick={() => extrasApi.kClear().then(() => { setSt({ files: 0, chunks: 0 }); setHits(null); })}><Trash2 size={14} /></button>}
      </div>
      {msg && <div className="mt-2 text-xs text-white/70">{msg}</div>}
      <div className="mt-3 flex gap-2">
        <input className="flex-1 rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm outline-none focus:border-nx-blue/60" placeholder="Søk i dokumentene dine…" value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && search()} />
        <button className="btn-primary flex items-center gap-1.5" onClick={search} disabled={q.trim().length < 2}><Search size={14} />Søk</button>
        <button className="btn flex items-center gap-1.5" onClick={ask} disabled={q.trim().length < 2 || !model || ans?.busy} title="La modellen svare ut fra dokumentene">{ans?.busy ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}Spør</button>
      </div>
      {ans && <div className="mt-3 animate-rise rounded-2xl glass-soft p-4"><div className="mb-1 flex items-center gap-1.5 text-xs text-white/65"><Sparkles size={12} />Svar fra dokumentene dine ({model})</div>
        <p className="whitespace-pre-wrap text-sm leading-relaxed">{ans.text || "Tenker…"}</p>
        {ans.srcs.length > 0 && !ans.busy && <div className="mt-2 flex flex-wrap gap-1.5">{ans.srcs.map((s, i) => <span key={s} className="rounded-full bg-white/12 px-2 py-0.5 text-[11px]">[{i + 1}] {s.split(/[\\/]/).pop()}</span>)}</div>}</div>}
      <div className="mt-3 min-h-0 flex-1 space-y-2 overflow-auto pr-1">
        {hits && hits.length === 0 && <div className="py-12 text-center text-sm text-white/55">Ingen treff. Prøv andre ord, eller oppdater indeksen.</div>}
        {hits?.map((h, i) => (
          <div key={i} className="animate-rise rounded-2xl glass-soft p-3" style={{ animationDelay: `${i * 40}ms` }}>
            <div className="flex items-center gap-2 text-xs text-white/65"><FileText size={12} /><span className="truncate">{h.path}</span><span className="ml-auto flex-none rounded-full bg-white/12 px-2 py-0.5">{h.score}</span></div>
            <p className="mt-1.5 whitespace-pre-wrap text-sm leading-relaxed">{h.text}</p>
          </div>))}
        {!hits && <div className="py-12 text-center text-sm text-white/55">Indekser mappene dine, og søk her eller spør agenten om innholdet.</div>}
      </div>
    </div>
  );
}
