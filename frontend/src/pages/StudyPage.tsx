import { useEffect, useRef, useState } from "react";
import { GraduationCap, PenLine, Sparkles, Trash2, Loader2, Copy, Check, RotateCcw, Layers } from "lucide-react";
import { Card, Deck, studyApi } from "../api";
import { useApp } from "../store";

const ACTIONS: [string, string][] = [["summarize", "Oppsummer"], ["bullets", "Punkter"], ["fix", "Rett feil"], ["simplify", "Forenkle"], ["formal", "Formell tone"], ["to_en", "Til engelsk"], ["to_no", "Til norsk"], ["explain", "Forklar"], ["questions", "Lag spørsmål"]];
const GRADES: [number, string, string][] = [[0, "Igjen", "10 min"], [1, "Vanskelig", ""], [2, "Bra", ""], [3, "Lett", ""]];
const clean = (e: unknown) => String(e).replace(/^Error: /, "").replace(/^\d+ /, "").replace(/^\{"detail":"(.*)"\}$/, "$1");

function Cards({ model }: { model: string }) {
  const [decks, setDecks] = useState<Deck[]>([]);
  const [text, setText] = useState(""); const [title, setTitle] = useState(""); const [n, setN] = useState(8);
  const [busy, setBusy] = useState(false); const [err, setErr] = useState(""); const [ok, setOk] = useState("");
  const [study, setStudy] = useState<{ deck: Deck; queue: Card[]; i: number; flip: boolean; done: number } | null>(null);
  const load = () => studyApi.decks().then(setDecks).catch((e) => setErr(clean(e)));
  useEffect(() => { load(); }, []);
  const gen = async () => {
    setBusy(true); setErr(""); setOk("");
    try { const r = await studyApi.generate({ model, text, title, n }); setOk(`${r.added} kort lagt i stokken.`); setText(""); setTitle(""); load(); }
    catch (e) { setErr(clean(e)); } finally { setBusy(false); }
  };
  const start = async (d: Deck) => {
    const q = await studyApi.cards(d.id, true);
    if (!q.length) { setOk(`Ingen kort å øve på i «${d.title}» nå. Kom tilbake senere.`); return; }
    setOk(""); setStudy({ deck: d, queue: q, i: 0, flip: false, done: 0 });
  };
  const grade = async (g: number) => {
    if (!study) return; const c = study.queue[study.i];
    await studyApi.review(c.id, g).catch(() => {});
    const q = g === 0 ? [...study.queue, c] : study.queue;
    const i = study.i + 1;
    if (i >= q.length) { setStudy(null); load(); setOk("Ferdig for nå. Bra jobba!"); }
    else setStudy({ ...study, queue: q, i, flip: false, done: study.done + (g === 0 ? 0 : 1) });
  };
  const field = "rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm outline-none focus:border-nx-blue/60";
  if (study) {
    const c = study.queue[study.i];
    return (
      <div className="mx-auto mt-6 flex w-full max-w-xl flex-col items-center">
        <div className="mb-3 flex w-full items-center text-sm text-white/65"><span>{study.deck.title}</span><span className="ml-auto">{study.i + 1} / {study.queue.length}</span></div>
        <div className="mb-4 h-1.5 w-full overflow-hidden rounded-full bg-white/10"><div className="sysbar h-full transition-all" style={{ width: `${(study.i / study.queue.length) * 100}%` }} /></div>
        <button onClick={() => setStudy({ ...study, flip: true })} className="glass-soft flex min-h-[220px] w-full animate-pop flex-col items-center justify-center rounded-3xl p-8 text-center" key={c.id + "-" + study.i}>
          <div className="text-[11px] uppercase tracking-wider text-white/55">{study.flip ? "Svar" : "Spørsmål"}</div>
          <div className="mt-3 text-lg font-medium">{study.flip ? c.back : c.front}</div>
          {!study.flip && <div className="mt-5 text-xs text-white/55">Trykk for å se svaret</div>}
        </button>
        {study.flip && <div className="mt-4 grid w-full animate-rise grid-cols-4 gap-2">{GRADES.map(([g, l, s]) => <button key={g} onClick={() => grade(g)} className="glass-soft rounded-2xl px-2 py-3 text-sm font-medium transition hover:bg-white/15">{l}{s && <div className="text-[10px] font-normal text-white/55">{s}</div>}</button>)}</div>}
        <button onClick={() => { setStudy(null); load(); }} className="mt-5 text-xs text-white/60 underline">Avslutt økten</button>
      </div>
    );
  }
  return (
    <div className="mt-4 grid min-h-0 flex-1 gap-4 overflow-auto md:grid-cols-[1fr_1fr]">
      <div className="glass-soft rounded-3xl p-4">
        <div className="flex items-center gap-2 text-sm font-medium"><Sparkles size={15} />Lag kort fra tekst</div>
        <p className="mt-1 text-xs text-white/60">Lim inn pensum eller notater. Modellen lager spørsmål og svar som bare bygger på teksten.</p>
        <input className={`${field} mt-3 w-full`} placeholder="Navn på stokken (valgfritt)" value={title} maxLength={100} onChange={(e) => setTitle(e.target.value)} />
        <textarea className={`${field} mt-2 h-40 w-full resize-none`} placeholder="Lim inn tekst her…" value={text} onChange={(e) => setText(e.target.value)} />
        <div className="mt-2 flex items-center gap-3 text-sm">
          <label className="text-white/70">Antall kort</label>
          <input type="range" min={3} max={20} value={n} onChange={(e) => setN(+e.target.value)} /><span className="w-6 tabular-nums">{n}</span>
          <button className="btn-primary ml-auto flex items-center gap-1.5" disabled={busy || text.trim().length < 40 || !model} onClick={gen}>{busy ? <Loader2 size={15} className="animate-spin" /> : <Sparkles size={15} />}{busy ? "Lager…" : "Lag kort"}</button>
        </div>
        {!model && <div className="mt-2 text-xs text-white/65">Velg eller last ned en modell først.</div>}
        {err && <div className="mt-2 text-sm text-rose-300">{err}</div>}
        {ok && <div className="mt-2 text-sm text-emerald-300">{ok}</div>}
      </div>
      <div className="space-y-2">
        {decks.length === 0 && <div className="glass-soft rounded-3xl p-8 text-center text-sm text-white/60">Ingen stokker ennå. Lag den første til venstre.</div>}
        {decks.map((d) => (
          <div key={d.id} className="glass-soft group flex animate-rise items-center gap-3 rounded-2xl px-4 py-3">
            <Layers size={18} className="flex-none text-white/60" />
            <div className="min-w-0 flex-1"><div className="truncate font-medium">{d.title}</div>
              <div className="text-xs text-white/60">{d.total} kort · {d.due} å øve på · {d.learned} lært</div></div>
            <button className="btn-primary" disabled={!d.due} onClick={() => start(d)}>Øv ({d.due})</button>
            <button title="Slett stokken" onClick={() => confirm(`Slette «${d.title}» og alle kortene?`) && studyApi.delDeck(d.id).then(load)} className="rounded-lg p-1.5 text-white/50 opacity-0 hover:bg-white/10 group-hover:opacity-100"><Trash2 size={14} /></button>
          </div>))}
      </div>
    </div>
  );
}

function Write({ model }: { model: string }) {
  const [src, setSrc] = useState(""); const [out, setOut] = useState(""); const [act, setAct] = useState("");
  const [busy, setBusy] = useState(false); const [err, setErr] = useState(""); const [copied, setCopied] = useState(false);
  const ctl = useRef<AbortController | null>(null);
  const run = async (a: string) => {
    ctl.current?.abort(); const c = new AbortController(); ctl.current = c;
    setAct(a); setOut(""); setErr(""); setBusy(true);
    try { await studyApi.transform(model, a, src, (t) => setOut((o) => o + t), c.signal); }
    catch (e) { if (!c.signal.aborted) setErr(clean(e)); } finally { if (ctl.current === c) setBusy(false); }
  };
  return (
    <div className="mt-4 grid min-h-0 flex-1 gap-4 md:grid-cols-2">
      <div className="flex min-h-0 flex-col">
        <textarea className="min-h-0 flex-1 resize-none rounded-2xl border border-white/10 bg-white/5 p-3 text-sm outline-none focus:border-nx-blue/60" placeholder="Lim inn teksten du vil jobbe med…" value={src} maxLength={12000} onChange={(e) => setSrc(e.target.value)} />
        <div className="mt-3 flex flex-wrap gap-1.5">{ACTIONS.map(([id, l]) => <button key={id} disabled={!src.trim() || !model || busy} onClick={() => run(id)} className={`rounded-full px-3 py-1.5 text-sm transition disabled:opacity-40 ${act === id ? "bg-white/20 font-medium" : "glass-soft hover:bg-white/15"}`}>{l}</button>)}</div>
      </div>
      <div className="glass-soft relative min-h-[200px] overflow-auto rounded-2xl p-4 text-sm">
        {!out && !busy && !err && <div className="grid h-full place-items-center text-center text-white/55">Resultatet vises her.</div>}
        {busy && !out && <div className="flex items-center gap-2 text-white/65"><Loader2 size={14} className="animate-spin" />Tenker…</div>}
        <div className="whitespace-pre-wrap">{out}</div>
        {err && <div className="text-rose-300">{err}</div>}
        {out && !busy && <div className="mt-3 flex gap-2">
          <button className="btn flex items-center gap-1.5" onClick={() => { navigator.clipboard?.writeText(out); setCopied(true); setTimeout(() => setCopied(false), 1500); }}>{copied ? <Check size={14} /> : <Copy size={14} />}{copied ? "Kopiert" : "Kopier"}</button>
          <button className="btn flex items-center gap-1.5" onClick={() => { setSrc(out); setOut(""); }}><RotateCcw size={14} />Bruk som ny tekst</button></div>}
      </div>
    </div>
  );
}

export default function StudyPage() {
  const { model } = useApp();
  const [tab, setTab] = useState<"cards" | "write">("cards");
  return (
    <div className="glass flex h-full flex-col overflow-hidden rounded-[28px] p-6">
      <div className="flex items-center gap-3">
        <div><h1 className="text-xl font-semibold">Studie</h1><p className="text-sm text-white/55">Lag øvingskort av pensum og jobb med tekster. Alt kjører lokalt{model ? ` med ${model}` : ""}.</p></div>
        <div className="ml-auto flex gap-1 rounded-2xl glass-soft p-1 text-sm">
          {([["cards", "Kort", GraduationCap], ["write", "Skriveverktøy", PenLine]] as const).map(([id, l, I]) => (
            <button key={id} onClick={() => setTab(id)} className={`flex items-center gap-1.5 rounded-xl px-3 py-1.5 transition ${tab === id ? "bg-white/15 font-medium" : "text-white/60"}`}><I size={14} />{l}</button>))}
        </div>
      </div>
      {tab === "cards" ? <Cards model={model} /> : <Write model={model} />}
    </div>
  );
}
