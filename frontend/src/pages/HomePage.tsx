import CountUp from "../components/CountUp";
import { SysMonCard, NotesCard, StudyCard, TodayCard } from "../components/HomeWidgets";
import { useEffect, useState } from "react";
import { MessageSquare, Cpu, Database, ArrowUpRight, Download, Zap, Brain, Users, Boxes, FolderOpen, Activity, Plus } from "lucide-react";
import { api, Conv, memApi } from "../api";
import { useApp } from "../store";

const greet = () => { const h = new Date().getHours(); return h < 5 ? "God natt" : h < 10 ? "God morgen" : h < 18 ? "God dag" : "God kveld"; };
const ago = (t: number) => { const m = Math.round((Date.now() / 1000 - t) / 60); return m < 1 ? "nå" : m < 60 ? `${m} min` : m < 1440 ? `${Math.round(m / 60)} t` : `${Math.round(m / 1440)} d`; };
const dateStr = () => new Date().toLocaleDateString("nb-NO", { weekday: "long", day: "numeric", month: "long" });

function Ring({ done, total }: { done: number; total: number }) {
  const r = 52, c = 2 * Math.PI * r;
  return (
    <div className="relative grid h-36 w-36 flex-none place-items-center">
      <svg viewBox="0 0 120 120" className="absolute inset-0 -rotate-90">
        <circle cx="60" cy="60" r={r} fill="none" stroke="rgba(255,255,255,.25)" strokeWidth="8" />
        <circle cx="60" cy="60" r={r} fill="none" stroke="#fff" strokeWidth="8" strokeLinecap="round" strokeDasharray={c} strokeDashoffset={c * (1 - done / total)} style={{ transition: "stroke-dashoffset .8s ease" }} />
      </svg>
      <div className="text-center"><div className="text-3xl font-semibold">{done}/{total}</div><div className="text-[11px] opacity-80">klart</div></div>
    </div>);
}

export default function HomePage({ go }: { go: (p: string) => void }) {
  const { health, models, model, pulls, pull, prefs } = useApp();
  const [recent, setRecent] = useState<Conv[] | null>(null);
  const [mems, setMems] = useState<number | null>(null);
  useEffect(() => { api.conversations().then((c) => setRecent(c.slice(0, 5))).catch(() => setRecent([])); memApi.list().then((m) => setMems(m.items.length)).catch(() => setMems(null)); }, []);
  const online = !!health?.ollama_online, nModels = models?.models.length ?? 0;
  const steps = [online, nModels > 0, !!model];
  const done = steps.filter(Boolean).length;
  const stat = (Icon: typeof Cpu, label: string, value: string, sub: string, delay: number, hot = false) => (
    <div className={`${hot ? "stat-hot" : "glass"} animate-rise rounded-[26px] p-5`} style={{ animationDelay: `${delay}ms` }}>
      <div className={`grid h-9 w-9 place-items-center rounded-full ${hot ? "bg-black/20" : "bg-white/60"}`}><Icon size={16} className={hot ? "" : "text-nx-blue"} /></div>
      <div className="mt-5 truncate text-[30px] font-semibold leading-none tracking-tight">{/^\d+$/.test(value) ? <CountUp value={Number(value)} /> : value}</div>
      <div className="mt-2 text-sm font-medium">{label}</div>
      <div className="truncate text-xs text-white/50">{sub}</div>
    </div>);
  const none = models?.online && nModels === 0;
  const rec = "qwen2.5:3b";
  const quick: [typeof Cpu, string, string, string][] = [
    [Plus, "Ny samtale", "Start i Assistant", "assistant"], [Users, "Bygg et team", "Agenter med roller", "automations"], [Boxes, "Finn modeller", "Hele Ollama-biblioteket", "models"],
    [FolderOpen, "Arbeidsområde", "Filer agenten kan bruke", "workspace"], [Brain, "Minner", "Det NEXUS husker", "memory"], [Activity, "Aktivitet", "Logg over alt agenten gjør", "activity"]];
  return (
    <div className="h-full space-y-4 overflow-auto pr-1">
      <div className="flex items-end justify-between gap-4 px-2 pt-1">
        <div><h1 className="text-[34px] font-semibold leading-tight tracking-tight">{greet()}, {prefs.user_name}</h1>
          <p className="text-sm capitalize text-white/50">{dateStr()}</p></div>
        <div className="flex gap-2"><button className="btn-ghost" onClick={() => go("activity")}>Aktivitetslogg</button><button className="btn-primary flex items-center gap-1.5" onClick={() => go("assistant")}><Plus size={14} />Ny samtale</button></div>
      </div>
      <div className="grid gap-4 lg:grid-cols-[1fr_300px]">
        <div className="hero-card animate-rise relative overflow-hidden rounded-[30px] p-7">
          <div className="pointer-events-none absolute -right-16 -top-20 h-72 w-72 rounded-full bg-black/10 blur-3xl" />
          <div className="flex items-center justify-between gap-6">
            <div className="max-w-md">
              <span className="inline-flex items-center gap-2 rounded-full bg-black/25 px-3 py-1 text-xs"><span className={`h-1.5 w-1.5 rounded-full ${online ? "bg-white" : "bg-black/40"}`} />{online ? "Ollama kjører" : "Ollama er offline"}</span>
              <h2 className="mt-4 text-[34px] font-semibold leading-[1.08] tracking-tight">Din lokale AI er <span className="serif-i text-[40px]">{done === 3 ? "klar" : "på vei"}</span> til å jobbe</h2>
              <p className="mt-3 text-sm opacity-85">{done === 3 ? `${model.startsWith("cloud:") ? `Du bruker skymodellen ${model.replace(/^cloud:[^:]+:/, "")}: meldingene sendes til leverandøren.` : `Alt kjører på PC-en din med ${model}. Ingen data forlater maskinen.`}` : "Fullfør oppsettet: Ollama på, minst én modell, og velg en modell."}</p>
              <div className="mt-5 flex flex-wrap gap-2">
                <button className="hero-btn rounded-full bg-white px-5 py-2 text-sm font-medium transition hover:scale-[1.03]" onClick={() => go("assistant")}>Åpne Assistant <ArrowUpRight size={14} className="inline" /></button>
                <button className="rounded-full border border-white/50 px-5 py-2 text-sm transition hover:bg-black/15" onClick={() => go("models")}>+ Modeller</button></div>
            </div>
            <Ring done={done} total={3} />
          </div>
          <div className="mt-6 grid grid-cols-3 gap-4 border-t border-white/25 pt-4 text-sm">
            {[["Ollama", online ? "på" : "av", steps[0]], ["Modeller", String(nModels), steps[1]], ["Valgt", model || "ingen", steps[2]]].map(([l, v, ok]) => (
              <div key={String(l)}><div className="truncate text-xl font-semibold">{v}</div><div className="text-xs opacity-95">{l} {ok ? "✓" : ""}</div></div>))}
          </div>
        </div>
        <div className="glass animate-rise rounded-[30px] p-5" style={{ animationDelay: "60ms" }}>
          <div className="mb-2 flex items-center justify-between"><div className="text-sm font-semibold">Siste samtaler</div><button className="text-xs text-white/50 hover:underline" onClick={() => go("assistant")}>Alle</button></div>
          {recent === null && <div className="space-y-2">{[0, 1, 2].map((i) => <div key={i} className="skeleton h-12" />)}</div>}
          {recent?.length === 0 && <div className="py-6 text-center text-sm text-white/40">Ingen samtaler ennå.<br />Start en i Assistant.</div>}
          <div className="space-y-2">{recent?.slice(0, 4).map((c) => (
            <button key={c.id} onClick={() => go("assistant")} className="glass-soft block w-full rounded-2xl px-3 py-2 text-left transition hover:brightness-105">
              <div className="truncate text-sm font-medium">{c.title}</div><div className="truncate text-[11px] text-white/45">{c.model} · {ago(c.updated_at)}</div></button>))}</div>
        </div>
      </div>
      {none && (
        <div className="glass animate-rise rounded-[26px] p-5">
          <div className="flex items-center gap-4"><div className="grid h-11 w-11 flex-none place-items-center rounded-2xl bg-nx-blue/20"><Zap size={20} className="text-nx-blue" /></div>
            <div className="flex-1"><div className="font-medium">Last ned din første modell</div>
              <div className="text-sm text-white/55">{rec} (ca. 1,9 GB) passer for PC-er som din. Du kan velge andre under Modeller.</div></div>
            <button className="btn-primary flex items-center gap-2" disabled={!!pulls[rec]} onClick={() => { pull(rec); go("models"); }}><Download size={15} />Last ned</button></div></div>)}
      {models && !models.online && <div className="glass animate-rise rounded-[26px] p-5 text-sm text-rose-700">Ollama kjører ikke. Start den, så er NEXUS klar.</div>}
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {stat(Cpu, "Ollama", online ? "Online" : "Offline", health?.ollama_version ? "versjon " + health.ollama_version : "ikke tilkoblet", 80, true)}
        {stat(Database, "Modeller", String(nModels), model ? "Valgt: " + model : "ingen valgt", 140)}
        {stat(MessageSquare, "Samtaler", String(health?.conversations ?? 0), "lagret lokalt på PC-en", 200)}
        {stat(Brain, "Minner", mems === null ? "–" : String(mems), "fakta NEXUS husker om deg", 260)}
      </div>
      <TodayCard go={go} />
      <div className="grid gap-4 md:grid-cols-2"><SysMonCard /><NotesCard go={() => go("notes")} /></div>
      <StudyCard go={() => go("study")} />
      <div className="grid gap-3 pb-2 md:grid-cols-2 xl:grid-cols-3">
        {quick.map(([I, t, d, to], i) => (
          <button key={t} onClick={() => go(to)} className="glass-soft animate-rise flex items-center gap-3 rounded-full py-2.5 pl-2.5 pr-5 text-left transition hover:brightness-105 active:scale-[.98]" style={{ animationDelay: `${300 + i * 40}ms` }}>
            <span className="grid h-10 w-10 flex-none place-items-center rounded-full bg-white/70"><I size={16} className="text-nx-blue" /></span>
            <span className="min-w-0"><span className="block text-sm font-medium">{t}</span><span className="block truncate text-xs text-white/50">{d}</span></span></button>))}
      </div>
    </div>
  );
}
