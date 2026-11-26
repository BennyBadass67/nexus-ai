import { useEffect, useState } from "react";
import { Check, Download, Search, Trash2, X, ChevronLeft, Gauge, Cpu, MemoryStick, MonitorCog } from "lucide-react";
import { api, fmtSize, LibModel, LibTag, HW, Topic, Bench } from "../api";
import Dot, { LABEL } from "../components/Dot";
import { useApp } from "../store";


function PullBar({ name }: { name: string }) {
  const { pulls, cancelPull } = useApp();
  const p = pulls[name];
  if (!p) return null;
  const pct = p.total ? Math.round(((p.completed || 0) / p.total) * 100) : null;
  return (
    <div className="mt-2">
      <div className="flex items-center justify-between text-xs text-white/60">
        <span className="truncate">{p.error ? <span className="text-rose-300">{p.error}</span> : p.done ? "Ferdig" : `${p.status}${pct !== null ? " " + pct + "%" : ""}`}</span>
        {!p.done && !p.error && <button title="Avbryt" onClick={() => cancelPull(name)}><X size={14} /></button>}
      </div>
      {!p.error && <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-white/10">
        <div className="h-full rounded-full bg-nx-blue transition-all" style={{ width: `${p.done ? 100 : pct ?? 5}%` }} /></div>}
    </div>
  );
}

function Installed() {
  const { models, model, setModel, refresh } = useApp();
  const [confirm, setConfirm] = useState("");
  const [checked, setChecked] = useState<Date | null>(null);
  const [busy, setBusy] = useState(false);
  const live = () => { setBusy(true); Promise.resolve(refresh()).finally(() => { setChecked(new Date()); setBusy(false); }); };
  useEffect(() => { live(); const t = setInterval(live, 4000); window.addEventListener("focus", live); return () => { clearInterval(t); window.removeEventListener("focus", live); }; }, []); // eslint-disable-line
  const stamp = <div className="mb-3 flex items-center gap-3 text-xs text-white/45"><span>{checked ? `Spurt Ollama på denne PC-en kl. ${checked.toLocaleTimeString("nb-NO")}` : "Spør Ollama…"}</span>
    <button className="rounded-lg glass-soft px-2 py-1 hover:text-white" disabled={busy} onClick={live}>Oppdater nå</button></div>;
  if (models && !models.online) return <div>{stamp}<div className="rounded-2xl bg-rose-500/10 p-4 text-sm text-rose-200">Ollama svarer ikke. Start Ollama (se etter lama-ikonet i systemfeltet) og trykk Oppdater.</div></div>;
  if (!models?.models.length) return <div>{stamp}<div className="rounded-2xl glass-soft p-4 text-sm">Ingen modeller installert ennå. Gå til «Last ned» og velg en. Anbefalt for din PC: qwen2.5:3b.</div></div>;
  return (<div>{stamp}
    <div className="grid gap-3 md:grid-cols-2">
      {models.models.map((m) => (
        <div key={m.name} onClick={() => setModel(m.name)}
          className={`cursor-pointer animate-pop rounded-2xl p-4 transition ${m.name === model ? "bg-nx-blue/20 ring-1 ring-nx-blue/60" : "glass-soft hover:bg-white/10"}`}>
          <div className="flex items-center justify-between"><span className="font-medium">{m.name}</span>
            {m.name === model ? <Check size={16} className="text-nx-blue" /> : null}</div>
          <div className="mt-1 text-xs text-white/50">{[m.params, m.quant, fmtSize(m.size)].filter(Boolean).join(" · ")}</div>
          <div className="mt-2 flex justify-end">
            {confirm === m.name
              ? <span className="flex items-center gap-2 text-xs">Slette?
                  <button className="text-rose-300" onClick={async (e) => { e.stopPropagation(); await api.deleteModel(m.name); setConfirm(""); refresh(); }}>Ja, slett</button>
                  <button onClick={(e) => { e.stopPropagation(); setConfirm(""); }}>Nei</button></span>
              : <button title="Slett modell" className="text-white/40 hover:text-rose-300" onClick={(e) => { e.stopPropagation(); setConfirm(m.name); }}><Trash2 size={14} /></button>}
          </div>
        </div>
      ))}
    </div></div>
  );
}

function Recommended({ goBrowse }: { goBrowse: () => void }) {
  const { models, pulls, pull, setModel } = useApp();
  const [data, setData] = useState<{ ok: boolean; error?: string; hardware: HW; topics: Topic[]; calibrated?: boolean; measured_models?: string[] } | null>(null);
  const [bench, setBench] = useState<Record<string, Bench>>({});
  const [running, setRunning] = useState("");
  const [berr, setBerr] = useState("");
  const have = new Set(models?.models.map((m) => m.name) ?? []);
  const load = () => api.recommendations().then(setData).catch((e) => setData({ ok: false, error: String(e), hardware: null as unknown as HW, topics: [] }));
  useEffect(() => { load(); api.benchmarks().then(setBench).catch(() => {}); }, []);
  const hw = data?.hardware;
  const runBench = async (m: string) => { setRunning(m); setBerr(""); try { const r = await api.benchmark(m); setBench((b) => ({ ...b, [m]: r })); load(); } catch (e: any) { setBerr(String(e.message || e)); } setRunning(""); };
  const installed = models?.models ?? [];
  const measureAll = async () => { setRunning("alle"); setBerr(""); try { await api.benchAuto(); setBench(await api.benchmarks()); await load(); } catch (e: any) { setBerr(String(e.message || e)); } setRunning(""); };
  return (
    <div className="space-y-5">
      <div className="glass-soft rounded-3xl p-5">
        <div className="mb-3 flex items-center justify-between"><div className="text-sm font-medium">Din PC</div>
          <div className="flex items-center gap-4 text-[11px] text-white/50">{(["green", "yellow", "red"] as const).map((l) => <span key={l} className="flex items-center gap-1.5"><Dot level={l} size={8} />{LABEL[l]}</span>)}</div></div>
        {!hw ? <div className="grid grid-cols-3 gap-3">{[0, 1, 2].map((i) => <div key={i} className="skeleton h-16" />)}</div> : (
          <div className="grid gap-3 md:grid-cols-3">
            {([[Cpu, "Prosessor", hw.cpu.replace(/\(R\)|\(TM\)/g, "").replace(/ with .*/, ""), `${hw.cores} tråder`], [MemoryStick, "Minne", `${hw.ram_gb} GB RAM`, "systemminne"],
              [MonitorCog, "Grafikk", hw.gpu || "Ingen dedikert GPU", hw.vram_gb ? `${hw.vram_gb} GB VRAM` : "kjører på prosessoren"]] as const).map(([I, a, b, c]) => (
              <div key={a} className="rounded-2xl bg-white/5 p-4"><I size={16} className="text-nx-blue" /><div className="mt-2 text-[11px] text-white/45">{a}</div>
                <div className="truncate text-sm font-medium" title={b}>{b}</div><div className="text-xs text-white/40">{c}</div></div>))}
          </div>)}
        <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-white/8 pt-4">
          <Gauge size={16} className="text-nx-blue" /><span className="text-sm">Hastighetstest</span>
          {installed.length === 0 ? <span className="text-xs text-white/45">Last ned en modell først, så kan jeg måle hvor rask PC-en din faktisk er.</span> :
            installed.slice(0, 4).map((m) => (
              <button key={m.name} disabled={!!running} onClick={() => runBench(m.name)} className="btn-ghost flex items-center gap-2 !py-1.5 text-xs">
                {running === m.name ? "Måler…" : m.name}{bench[m.name] && running !== m.name && <span className="rounded-md bg-nx-blue/20 px-1.5 text-nx-ice">{bench[m.name].tps} tok/s</span>}</button>))}
          {installed.length > 0 && <button disabled={!!running} onClick={measureAll} className="btn-primary !py-1.5 text-xs">{running === "alle" ? "Måler…" : "Mål installerte modeller"}</button>}
          {berr && <span className="text-xs text-rose-300">{berr}</span>}
          <div className="w-full text-xs text-white/45">{data?.calibrated ? `Fargene bygger på ${data.measured_models?.length} faktisk måling(er) av tokens/sek på denne PC-en. Andre modeller er estimert ut fra målingene.` : "Ikke målt ennå: fargene er et første anslag fra minne og GPU. Mål en modell for å få ekte tall."}</div>
        </div>
      </div>
      {data && !data.ok && <div className="rounded-2xl bg-amber-500/10 p-3 text-sm text-amber-200">Kunne ikke hente anbefalinger fra ollama.com ({data.error}). Du kan fortsatt søke under «Last ned».</div>}
      {!data && <div className="grid gap-3 md:grid-cols-2">{[0, 1, 2, 3].map((i) => <div key={i} className="skeleton h-36" />)}</div>}
      <div className="grid gap-3 md:grid-cols-2">
        {data?.topics.map((t, i) => (
          <div key={t.id} className="animate-rise glass-soft rounded-3xl p-5" style={{ animationDelay: `${i * 50}ms` }}>
            <div className="text-[15px] font-semibold">{t.title}</div><div className="text-xs text-white/50">{t.desc}</div>
            {t.model ? (<div className="mt-4">
              <div className="flex items-center justify-between gap-3"><div className="flex min-w-0 items-center gap-2.5"><Dot level={t.model.level} reason={t.model.reason} size={11} />
                <div className="min-w-0"><div className="truncate font-medium">{t.model.tag}</div><div className="text-xs text-white/65">{t.model.size_gb} GB · {t.model.reason}</div></div></div>
                {have.has(t.model.tag) ? <button className="btn-ghost !py-1.5 text-emerald-300" onClick={() => setModel(t.model!.tag)}>Bruk</button>
                  : <button className="btn-primary flex items-center gap-1.5 !py-1.5" disabled={!!pulls[t.model.tag]} onClick={() => pull(t.model!.tag)}><Download size={14} />Last ned</button>}</div>
              <PullBar name={t.model.tag} /></div>) : <div className="mt-4 text-sm text-white/45">Ingen modell i denne kategorien passer PC-en din godt.</div>}
          </div>))}
      </div>
      <button className="text-sm text-nx-blue hover:underline" onClick={goBrowse}>Se alle modeller i Ollama-biblioteket →</button>
    </div>
  );
}

function Browse() {
  const { models, pulls, pull } = useApp();
  const [q, setQ] = useState("");
  const [res, setRes] = useState<LibModel[] | null>(null);
  const [err, setErr] = useState("");
  const [open, setOpen] = useState<LibModel | null>(null);
  const [tags, setTags] = useState<LibTag[] | null>(null);
  const [manual, setManual] = useState("");
  const [cats, setCats] = useState<{ id: string; label: string; count: number }[]>([]);
  const [cat, setCat] = useState("alle");
  const [fitsCount, setFitsCount] = useState(0);
  const [limit, setLimit] = useState(24);
  const have = new Set(models?.models.map((m) => m.name) ?? []);
  const shown = (res ?? []).filter((m) => cat === "alle" || (cat === "passer" ? m.fits : m.categories?.includes(cat)));
  const CAPL: Record<string, string> = { vision: "bilder", tools: "verktøy", thinking: "tenker", embedding: "embedding", audio: "lyd" };
  const pullsTxt = (n?: number) => (!n ? "" : n >= 1e6 ? (n / 1e6).toFixed(1) + "M" : Math.round(n / 1e3) + "K") + " nedlastinger";

  useEffect(() => {
    const t = setTimeout(() => { setErr(""); setRes(null); setLimit(24);
      api.library(q).then((r) => { if (r.ok) { setRes(r.models); setCats(r.categories ?? []); setFitsCount(r.fits_count ?? 0); } else setErr(r.error || "Feil"); }).catch((e) => setErr(String(e))); }, 350);
    return () => clearTimeout(t);
  }, [q]);
  useEffect(() => { setTags(null); if (open) api.tags(open.name).then((r) => setTags(r.ok ? r.tags : [])).catch(() => setTags([])); }, [open]);

  const row = (name: string, extra: string, t?: LibTag) => (
    <div key={name} className="rounded-2xl glass-soft p-3">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0"><div className="truncate text-sm font-medium">{name}</div>
          <div className="text-xs text-white/50">{extra}</div></div>
        {t && <span className="flex items-center gap-1.5 text-xs text-white/55"><Dot level={t.level} reason={t.reason} />{t.level === "green" ? "passer" : t.level === "yellow" ? "tregt" : t.level === "red" ? "for tung" : ""}</span>}
        {have.has(name) || have.has(name + ":latest")
          ? <span className="text-xs text-emerald-300">installert</span>
          : <button className="btn-primary flex items-center gap-1.5 !py-1.5" disabled={!!pulls[name]} onClick={() => pull(name)}><Download size={14} />Last ned</button>}
      </div>
      <PullBar name={name} />
    </div>
  );

  if (open) return (
    <div className="space-y-3">
      <button className="btn-ghost flex items-center gap-1" onClick={() => setOpen(null)}><ChevronLeft size={14} />Tilbake</button>
      <div><div className="text-lg font-semibold">{open.name}</div><div className="text-sm text-white/60">{open.description}</div></div>
      {!tags && <div className="text-sm text-white/50">Henter versjoner…</div>}
      {tags?.length === 0 && <div className="text-sm text-white/50">Fant ingen versjoner. Prøv å skrive navnet manuelt under.</div>}
      <div className="grid gap-2 md:grid-cols-2">{tags?.map((t) => row(t.tag, `${t.size_gb} GB`, t))}</div>
    </div>
  );

  return (
    <div className="space-y-4">
      <div className="relative"><Search size={16} className="absolute left-3.5 top-3 text-white/40" />
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Søk i Ollama-biblioteket (f.eks. qwen, llama, gemma, phi)…"
          className="w-full rounded-2xl border border-white/10 bg-white/5 py-2.5 pl-10 pr-4 text-sm outline-none focus:border-nx-blue/60" /></div>
      {res && (<div className="flex flex-wrap items-center gap-1.5 text-xs">
        {[{ id: "alle", label: "Alle", count: res.length }, { id: "passer", label: "Passer PC-en min", count: fitsCount }, ...cats].map((c) => (
          <button key={c.id} onClick={() => { setCat(c.id); setLimit(24); }}
            className={`rounded-full px-3 py-1.5 transition ${cat === c.id ? "bg-nx-blue/30 text-white ring-1 ring-nx-blue/60" : "glass-soft text-white/60 hover:text-white"}`}>{c.label} <span className="text-white/40">{c.count}</span></button>))}
        <span className="ml-auto text-white/40">{shown.length} modeller · hentet live fra ollama.com</span></div>)}
      {res && <p className="text-[11px] text-white/35">Kategoriene er utledet fra Ollama sine egenskaper og beskrivelser. Beskrivelsene er Ollama sin egen tekst. Søkefeltet søker i hele registeret på navn og beskrivelse.</p>}
      {err && <div className="rounded-2xl bg-amber-500/10 p-3 text-sm text-amber-200">{err}. Du kan fortsatt skrive modellnavnet manuelt under.</div>}
      {!res && !err && <div className="grid gap-2 md:grid-cols-2">{[0,1,2,3,4,5].map((i) => <div key={i} className="skeleton h-24" />)}</div>}
      <div className="grid gap-2 md:grid-cols-2">
        {shown.slice(0, limit).map((m) => (
          <button key={m.name} onClick={() => setOpen(m)} className="rounded-2xl glass-soft p-4 text-left transition hover:bg-white/10">
            <div className="flex items-center justify-between"><span className="font-medium">{m.name}</span>
              <span className="text-xs text-white/40">{pullsTxt(m.pulls || m.downloads)}</span></div>
            <div className="mt-1 line-clamp-2 text-xs text-white/60">{m.description}</div>
            {!!m.categories?.length && <div className="mt-1 text-[11px] text-nx-ice/80">Bra til: {m.categories.map((c) => cats.find((x) => x.id === c)?.label ?? c).join(" · ")}</div>}
            <div className="mt-2 flex flex-wrap gap-1.5">{(m.size_ratings ?? m.sizes.map((l) => ({ label: l, level: "unknown" as const, reason: "", est_gb: null }))).map((r) => <span key={r.label} className="flex items-center gap-1.5 rounded-md bg-white/10 px-1.5 py-0.5 text-[11px]"><Dot level={r.level} reason={r.reason} size={7} />{r.label}</span>)}{m.capabilities.map((s) => <span key={s} className="rounded-md bg-nx-blue/15 px-1.5 py-0.5 text-[11px] text-nx-ice">{CAPL[s] ?? s}</span>)}</div>
          </button>
        ))}
      </div>
      {res && shown.length > limit && <button className="btn-ghost mx-auto block" onClick={() => setLimit((l) => l + 24)}>Vis flere ({shown.length - limit} igjen)</button>}
      {res && shown.length === 0 && <div className="text-sm text-white/50">Ingen treff.</div>}
      <div className="rounded-2xl glass-soft p-4">
        <div className="mb-2 text-sm font-medium">Kjenner du navnet? Skriv det inn</div>
        <div className="flex gap-2">
          <input value={manual} onChange={(e) => setManual(e.target.value.trim())} placeholder="f.eks. llama3.2:3b"
            className="flex-1 rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm outline-none" />
          <button className="btn-primary" disabled={!manual || !!pulls[manual]} onClick={() => pull(manual)}>Last ned</button></div>
        <PullBar name={manual} />
      </div>
    </div>
  );
}

export default function Models() {
  const { refresh, pulls } = useApp();
  const [tab, setTab] = useState<"rec" | "installed" | "browse">("rec");
  const active = Object.keys(pulls).filter((k) => !pulls[k].done && !pulls[k].error).length;
  return (
    <div className="glass h-full overflow-auto rounded-[28px] p-7">
      <div className="mb-4 flex items-center justify-between">
        <div><h1 className="text-xl font-semibold">Models</h1>
          <p className="text-sm text-white/50">Gratis lokale modeller. Kjører på din PC, ingenting sendes ut. Vil du heller bruke gratis skymodeller, slår du dem på under Settings, Sky-KI.</p></div>
        <div className="flex gap-1 rounded-xl glass-soft p-1 text-sm">
          {(["rec", "installed", "browse"] as const).map((t) => (
            <button key={t} onClick={() => { setTab(t); if (t === "installed") refresh(); }}
              className={`rounded-lg px-3 py-1.5 ${tab === t ? "bg-white/15" : "text-white/60"}`}>
              {t === "rec" ? "Anbefalt" : t === "installed" ? "Installert" : "Alle modeller"}{t === "browse" && active ? ` (${active})` : ""}</button>))}
        </div>
      </div>
      {tab === "rec" ? <Recommended goBrowse={() => setTab("browse")} /> : tab === "installed" ? <Installed /> : <Browse />}
    </div>
  );
}
