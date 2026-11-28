import { useEffect, useRef, useState } from "react";
import { GraduationCap, PenLine, Sparkles, Trash2, Loader2, Copy, Check, RotateCcw, Layers, Swords, CalendarDays, Flame } from "lucide-react";
import { Card, Deck, studyApi, schoolApi, StudyStats } from "../api";
import { useApp } from "../store";

const ACTIONS: [string, string][] = [["summarize", "Oppsummer"], ["bullets", "Punkter"], ["fix", "Rett feil"], ["simplify", "Forenkle"], ["formal", "Formell tone"], ["to_en", "Til engelsk"], ["to_no", "Til norsk"], ["explain", "Forklar"], ["questions", "Lag spørsmål"]];
const GRADES: [number, string, string][] = [[0, "Igjen", "10 min"], [1, "Vanskelig", ""], [2, "Bra", ""], [3, "Lett", ""]];
const clean = (e: unknown) => String(e).replace(/^Error: /, "").replace(/^\d+ /, "").replace(/^\{"detail":"(.*)"\}$/, "$1");

function Cards({ model }: { model: string }) {
  const [decks, setDecks] = useState<Deck[]>([]);
  const [text, setText] = useState(""); const [title, setTitle] = useState(""); const [n, setN] = useState(8);
  const [busy, setBusy] = useState(false); const [err, setErr] = useState(""); const [ok, setOk] = useState("");
  const [qopen, setQopen] = useState(false); const [qtitle, setQtitle] = useState(""); const [qtext, setQtext] = useState(""); const [qbusy, setQbusy] = useState(false);
  const quick = async () => {
    setQbusy(true); setErr(""); setOk("");
    try { const r = await studyApi.quick({ title: qtitle, text: qtext }); setOk(`${r.added} kort lagt i stokken.`); setQtext(""); setQtitle(""); load(); }
    catch (e) { setErr(clean(e)); } finally { setQbusy(false); }
  };
  const [quiz, setQuiz] = useState<{ deck: Deck; qs: { card_id: number; question: string; options: string[]; answer: number }[]; i: number; pick: number | null; right: number } | null>(null);
  const startQuiz = async (d: Deck) => {
    try { const qs = await studyApi.quiz(d.id); setErr(""); setOk(""); setQuiz({ deck: d, qs, i: 0, pick: null, right: 0 }); } catch (e) { setErr(clean(e)); }
  };
  const [expl, setExpl] = useState(""); const [explBusy, setExplBusy] = useState(false);
  const explain = async () => {
    if (!quiz || quiz.pick === null) return; const q = quiz.qs[quiz.i];
    setExpl(""); setExplBusy(true);
    const prompt = `Du er en vennlig lærer. Forklar på norsk, i 2-3 korte setninger, hvorfor riktig svar på spørsmålet er riktig, og hvorfor det valgte svaret ikke stemmer.\nSpørsmål: ${q.question}\nRiktig svar: ${q.options[q.answer]}\nEleven valgte: ${q.options[quiz.pick]}`;
    try { await studyApi.complete(model, prompt, (t) => setExpl((e) => e + t)); } catch (e) { setExpl("Kunne ikke hente forklaring: " + clean(e)); }
    setExplBusy(false);
  };
  const startWeak = async () => {
    try { const qs = await studyApi.weak(10); setErr(""); setOk(""); setQuiz({ deck: { id: 0, title: "Svake kort (alle stokker)" } as Deck, qs, i: 0, pick: null, right: 0 }); } catch (e) { setErr(clean(e)); }
  };
  const answer = (k: number) => {
    if (!quiz || quiz.pick !== null) return; const q = quiz.qs[quiz.i]; const good = k === q.answer;
    studyApi.review(q.card_id, good ? 2 : 0).catch(() => {});
    setQuiz({ ...quiz, pick: k, right: quiz.right + (good ? 1 : 0) });
  };
  const nextQ = () => {
    if (!quiz) return; setExpl("");
    if (quiz.i + 1 >= quiz.qs.length) { setOk(`Quiz ferdig: ${quiz.right} av ${quiz.qs.length} riktige.`); setQuiz(null); load(); }
    else setQuiz({ ...quiz, i: quiz.i + 1, pick: null });
  };
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
  if (quiz) {
    const q = quiz.qs[quiz.i];
    return (
      <div className="mx-auto mt-6 flex w-full max-w-xl flex-col">
        <div className="mb-3 flex items-center text-sm text-white/65"><span>Quiz: {quiz.deck.title}</span><span className="ml-auto">{quiz.i + 1} / {quiz.qs.length} · {quiz.right} riktige</span></div>
        <div className="mb-4 h-1.5 w-full overflow-hidden rounded-full bg-white/10"><div className="sysbar h-full transition-all" style={{ width: `${(quiz.i / quiz.qs.length) * 100}%` }} /></div>
        <div key={quiz.i} className="glass-soft animate-pop rounded-3xl p-6 text-lg font-medium">{q.question}</div>
        <div className="mt-3 grid gap-2">
          {q.options.map((o, k) => {
            const st = quiz.pick === null ? "" : k === q.answer ? "ring-2 ring-emerald-500" : k === quiz.pick ? "ring-2 ring-rose-500" : "opacity-60";
            return <button key={k} onClick={() => answer(k)} className={`glass-soft animate-rise rounded-2xl px-4 py-3 text-left text-sm transition hover:bg-white/15 ${st}`} style={{ animationDelay: k * 50 + "ms" }}>{o}{quiz.pick !== null && k === q.answer && <span className="ml-2 text-xs">✓ riktig</span>}{quiz.pick === k && k !== q.answer && <span className="ml-2 text-xs">✗ feil</span>}</button>;
          })}
        </div>
        {quiz.pick !== null && quiz.pick !== q.answer && (
          <div className="mt-4">
            {!expl && !explBusy && <button className="btn-ghost" onClick={explain}><Sparkles size={14} /> Forklar hvorfor</button>}
            {(expl || explBusy) && <div className="glass-soft animate-rise rounded-2xl p-4 text-sm leading-relaxed">{expl || "Tenker…"}</div>}
          </div>)}
        {quiz.pick !== null && <button className="btn-primary mt-4 self-end" onClick={nextQ}>{quiz.i + 1 >= quiz.qs.length ? "Se resultat" : "Neste"}</button>}
        <button onClick={() => { setQuiz(null); load(); }} className="mt-4 self-center text-xs text-white/60 underline">Avslutt quiz</button>
      </div>
    );
  }
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
        <button className="mt-3 text-xs text-white/60 underline" onClick={() => setQopen(!qopen)}>{qopen ? "Skjul hurtigkort" : "Har du fasit? Lim inn ferdige par uten modell"}</button>
        {qopen && (
          <div className="animate-rise mt-2 border-t border-white/10 pt-3">
            <div className="text-xs text-white/60">Én linje per kort, f.eks. «hovedstaden i Norge = Oslo». Virker også med - | eller ;</div>
            <input className={`${field} mt-2 w-full`} placeholder="Navn på stokken (valgfritt)" value={qtitle} maxLength={100} onChange={(e) => setQtitle(e.target.value)} />
            <textarea className={`${field} mt-2 h-28 w-full resize-none`} placeholder={"hovedstaden i Norge = Oslo\n4 x 4 = 16"} value={qtext} onChange={(e) => setQtext(e.target.value)} />
            <button className="btn-primary mt-2 flex items-center gap-1.5" disabled={qbusy || !qtext.trim()} onClick={quick}>{qbusy ? <Loader2 size={15} className="animate-spin" /> : <Layers size={15} />}{qbusy ? "Lager…" : "Lag hurtigkort"}</button>
          </div>)}
      </div>
      <div className="space-y-2">
        {decks.length === 0 && <div className="glass-soft rounded-3xl p-8 text-center text-sm text-white/60">Ingen stokker ennå. Lag den første til venstre.</div>}
        {decks.reduce((a, d) => a + d.total, 0) >= 4 && (
          <div className="glass-soft flex animate-rise items-center gap-3 rounded-2xl px-4 py-3">
            <Flame size={18} className="flex-none" />
            <div className="min-w-0 flex-1"><div className="font-medium">Tren svake kort</div><div className="text-xs text-white/70">10 spørsmål på tvers av alle stokker, med de du sliter mest med først.</div></div>
            <button className="btn-primary" onClick={startWeak}>Start</button>
          </div>)}
        {decks.map((d) => (
          <div key={d.id} className="glass-soft group flex animate-rise items-center gap-3 rounded-2xl px-4 py-3">
            <Layers size={18} className="flex-none text-white/60" />
            <div className="min-w-0 flex-1"><div className="truncate font-medium">{d.title}</div>
              <div className="text-xs text-white/60">{d.total} kort · {d.due} å øve på · {d.learned} lært</div></div>
            <button className="glass-soft rounded-xl px-3 py-1.5 text-sm disabled:opacity-40" disabled={d.total < 3} title={d.total < 3 ? "Trenger minst 3 kort" : "Flervalgsquiz"} onClick={() => startQuiz(d)}>Quiz</button>
            <button className="btn-primary" disabled={!d.due} onClick={() => start(d)}>Øv ({d.due})</button>
            <button title="Slett stokken" onClick={() => confirm(`Slette «${d.title}» og alle kortene?`) && studyApi.delDeck(d.id).then(load)} className="rounded-lg p-1.5 text-white/50 opacity-0 hover:bg-white/10 group-hover:opacity-100"><Trash2 size={14} /></button>
          </div>))}
      </div>
    </div>
  );
}

function StatsStrip() {
  const [s, setS] = useState<StudyStats | null>(null);
  useEffect(() => { schoolApi.stats().then(setS).catch(() => {}); }, []);
  if (!s) return null;
  const mx = Math.max(1, ...s.last7.map((x) => x.n));
  return (
    <div className="glass-soft mb-3 flex animate-rise flex-wrap items-center gap-x-6 gap-y-2 rounded-2xl px-4 py-3 text-sm">
      <div className="flex items-center gap-2"><Flame size={16} /><b className="text-lg tabular-nums">{s.streak}</b><span className="text-white/70">{s.streak === 1 ? "dag på rad" : "dager på rad"}</span></div>
      <div><b className="tabular-nums">{s.today}</b> <span className="text-white/70">repetisjoner i dag</span></div>
      {s.good_pct_7d != null && <div><b className="tabular-nums">{s.good_pct_7d} %</b> <span className="text-white/70">riktig siste 7 dager</span></div>}
      <div className="ml-auto flex h-8 items-end gap-1" title="Repetisjoner siste 7 dager">{s.last7.map((x) => <div key={x.day} title={`${x.day}: ${x.n}`} className="sysbar w-2.5 rounded-sm transition-all duration-700" style={{ height: Math.max(3, (x.n / mx) * 30) + "px", opacity: x.n ? 1 : 0.25 }} />)}</div>
    </div>);
}

function Plan() {
  const [topics, setTopics] = useState(""); const [exam, setExam] = useState(""); const [subj, setSubj] = useState("");
  const [items, setItems] = useState<{ due: string; text: string }[] | null>(null); const [err, setErr] = useState(""); const [ok, setOk] = useState("");
  const list = () => topics.split("\n").map((t) => t.trim()).filter(Boolean);
  const go = async (commit: boolean) => {
    setErr(""); setOk("");
    try { const r = await schoolApi.plan({ topics: list(), exam_date: exam, subject: subj, commit }); setItems(r.items); if (commit) setOk(`${r.added} oppgaver lagt til under Notater og på I dag-kortet.`); }
    catch (e) { setErr(clean(e)); setItems(null); }
  };
  const field = "rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm outline-none focus:border-nx-blue/60";
  return (
    <div className="mt-4 grid min-h-0 flex-1 gap-4 overflow-auto md:grid-cols-2">
      <div className="glass-soft rounded-3xl p-4">
        <div className="flex items-center gap-2 text-sm font-medium"><CalendarDays size={15} />Lag studieplan</div>
        <p className="mt-1 text-xs text-white/60">Skriv ett emne per linje og når prøven er. Planen fordeler emnene over dagene, legger inn repetisjon etter to dager og en samlet repetisjon dagen før.</p>
        <input className={`${field} mt-3 w-full`} placeholder="Fag (valgfritt), f.eks. Matte" maxLength={60} value={subj} onChange={(e) => setSubj(e.target.value)} />
        <textarea className={`${field} mt-2 h-32 w-full resize-none`} placeholder={"Brøk\nLikninger\nGeometri"} value={topics} onChange={(e) => setTopics(e.target.value)} />
        <label className="mt-2 flex items-center gap-3 text-sm text-white/70">Prøvedato<input type="date" className={field} value={exam} onChange={(e) => setExam(e.target.value)} /></label>
        <div className="mt-3 flex gap-2"><button className="btn" disabled={!list().length || !exam} onClick={() => go(false)}>Forhåndsvis</button>
          <button className="btn-primary" disabled={!list().length || !exam} onClick={() => go(true)}>Legg i oppgaver</button></div>
        {err && <div className="mt-2 text-sm text-rose-300">{err}</div>}
        {ok && <div className="mt-2 text-sm text-emerald-300">{ok}</div>}
      </div>
      <div className="space-y-1.5">
        {!items && <div className="glass-soft rounded-3xl p-8 text-center text-sm text-white/60">Planen vises her.</div>}
        {items?.map((it, i) => <div key={i} className="glass-soft flex animate-rise items-center gap-3 rounded-xl px-3 py-2 text-sm" style={{ animationDelay: Math.min(i, 12) * 30 + "ms" }}><span className="w-20 flex-none text-xs tabular-nums text-white/65">{it.due}</span><span>{it.text}</span></div>)}
      </div>
    </div>);
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

type Side = { text: string; ms: number; state: "idle" | "wait" | "run" | "done" | "err" };
const idle: Side = { text: "", ms: 0, state: "idle" };
function Duel() {
  const { models, model } = useApp();
  const names = models?.models.map((m) => m.name) ?? [];
  const [a, setA] = useState(model); const [b, setB] = useState(names.find((n) => n !== model) ?? model);
  const [q, setQ] = useState(""); const [L, setL] = useState<Side>(idle); const [R, setR] = useState<Side>(idle);
  const [busy, setBusy] = useState(false); const ctl = useRef<AbortController | null>(null);
  const go = async () => {
    const c = new AbortController(); ctl.current = c; setBusy(true); setL({ ...idle, state: "wait" }); setR({ ...idle, state: "wait" });
    for (const [m, set] of [[a, setL], [b, setR]] as const) {
      const t0 = performance.now(); set({ text: "", ms: 0, state: "run" });
      try {
        await studyApi.complete(m, q, (t) => set((s) => ({ ...s, text: s.text + t, ms: performance.now() - t0 })), c.signal);
        set((s) => ({ ...s, ms: performance.now() - t0, state: s.text.includes("[Feil:") ? "err" : "done" }));
      } catch { set((s) => ({ ...s, state: "err" })); if (c.signal.aborted) break; }
    }
    setBusy(false);
  };
  const rate = (s: Side) => (s.state === "done" && s.ms > 0 ? s.text.length / 4 / (s.ms / 1000) : 0);
  const fast = rate(L) && rate(R) ? (rate(L) >= rate(R) ? "L" : "R") : "";
  const sel = "rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm outline-none";
  const col = (name: string, s: Side, w: boolean) => (
    <div className={`glass-soft flex min-h-[220px] flex-col rounded-2xl p-4 transition ${w ? "ring-2 ring-emerald-500/60" : ""}`}>
      <div className="flex items-center gap-2 text-sm font-medium"><span className="truncate">{name}</span>
        {w && <span style={{ background: "#065f46", color: "#fff" }} className="animate-pop rounded-full px-2 py-0.5 text-[11px] font-normal">raskest</span>}
        {s.state === "run" && <Loader2 size={13} className="ml-auto animate-spin" />}</div>
      <div className="mt-2 min-h-0 flex-1 overflow-auto whitespace-pre-wrap text-sm">{s.state === "wait" ? <span className="text-white/60">Venter på tur…</span> : s.text}</div>
      {s.state === "done" && <div className="mt-2 text-xs text-white/65">{(s.ms / 1000).toFixed(1)} s · ca. {rate(s).toFixed(1)} tegn-tokens/s</div>}
    </div>);
  return (
    <div className="mt-4 flex min-h-0 flex-1 flex-col gap-3 overflow-auto">
      <p className="text-xs text-white/60">Samme spørsmål til to modeller, én om gangen (8 GB RAM tåler ikke to samtidig). Tiden inkluderer lasting av modellen første gang.</p>
      <div className="flex flex-wrap items-center gap-2">
        <select className={sel} value={a} onChange={(e) => setA(e.target.value)}>{names.map((n) => <option key={n}>{n}</option>)}</select>
        <span className="text-sm text-white/60">mot</span>
        <select className={sel} value={b} onChange={(e) => setB(e.target.value)}>{names.map((n) => <option key={n}>{n}</option>)}</select>
      </div>
      <div className="flex gap-2"><input className="flex-1 rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm outline-none focus:border-nx-blue/60" placeholder="Spørsmål til begge modellene…" value={q} maxLength={1000} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && q.trim() && !busy && go()} />
        {busy ? <button className="btn" onClick={() => ctl.current?.abort()}>Stopp</button> : <button className="btn-primary" disabled={!q.trim() || !a || !b} onClick={go}>Start duell</button>}</div>
      <div className="grid gap-3 md:grid-cols-2">{col(a, L, fast === "L")}{col(b, R, fast === "R")}</div>
    </div>);
}

export default function StudyPage() {
  const { model } = useApp();
  const [tab, setTab] = useState<"cards" | "plan" | "write" | "duel">("cards");
  return (
    <div className="glass flex h-full flex-col overflow-hidden rounded-[28px] p-6">
      <div className="flex items-center gap-3">
        <div><h1 className="text-xl font-semibold">Studie</h1><p className="text-sm text-white/55">Lag øvingskort av pensum og jobb med tekster. Alt kjører lokalt{model ? ` med ${model}` : ""}.</p></div>
        <div className="ml-auto flex gap-1 rounded-2xl glass-soft p-1 text-sm">
          {([["cards", "Kort", GraduationCap], ["plan", "Studieplan", CalendarDays], ["write", "Skriveverktøy", PenLine], ["duel", "Modellduell", Swords]] as const).map(([id, l, I]) => (
            <button key={id} onClick={() => setTab(id)} className={`flex items-center gap-1.5 rounded-xl px-3 py-1.5 transition ${tab === id ? "bg-white/15 font-medium" : "text-white/60"}`}><I size={14} />{l}</button>))}
        </div>
      </div>
      {tab === "cards" ? <><StatsStrip /><Cards model={model} /></> : tab === "plan" ? <Plan /> : tab === "write" ? <Write model={model} /> : <Duel />}
    </div>
  );
}
