import { useEffect, useState } from "react";
import { MessageSquare, Cpu, Database, ArrowRight, Download, Zap } from "lucide-react";
import { api, Conv } from "../api";
import { useApp } from "../store";

const greet = () => { const h = new Date().getHours(); return h < 5 ? "God natt" : h < 10 ? "God morgen" : h < 18 ? "God dag" : "God kveld"; };
const ago = (t: number) => { const m = Math.round((Date.now() / 1000 - t) / 60); return m < 1 ? "nå" : m < 60 ? `${m} min` : m < 1440 ? `${Math.round(m / 60)} t` : `${Math.round(m / 1440)} d`; };

export default function HomePage({ go }: { go: (p: string) => void }) {
  const { health, models, model, pulls, pull } = useApp();
  const [recent, setRecent] = useState<Conv[] | null>(null);
  useEffect(() => { api.conversations().then((c) => setRecent(c.slice(0, 5))).catch(() => setRecent([])); }, []);
  const stat = (Icon: typeof Cpu, label: string, value: string, sub: string, delay: number) => (
    <div className="glass animate-rise rounded-[24px] p-5" style={{ animationDelay: `${delay}ms` }}>
      <div className="flex items-center justify-between"><span className="text-xs text-white/50">{label}</span>
        <div className="grid h-8 w-8 place-items-center rounded-xl bg-nx-blue/15"><Icon size={15} className="text-nx-blue" /></div></div>
      <div className="mt-3 text-[28px] font-semibold leading-none tracking-tight">{value}</div>
      <div className="mt-1.5 truncate text-xs text-white/40">{sub}</div>
    </div>);
  const none = models?.online && models.models.length === 0;
  const rec = "qwen2.5:3b";
  return (
    <div className="h-full space-y-3 overflow-auto pr-1">
      <div className="glass relative overflow-hidden rounded-[28px] p-8">
        <div className="pointer-events-none absolute -right-10 -top-16 h-64 w-64 rounded-full bg-nx-blue/25 blur-3xl" />
        <div className="text-sm text-white/50">{greet()}, Benjamin</div>
        <h1 className="mt-1 max-w-xl text-[34px] font-semibold leading-[1.1] tracking-tight">Hva skal vi gjøre i dag?</h1>
        <div className="mt-6 flex gap-2.5">
          <button className="btn-primary flex items-center gap-2" onClick={() => go("assistant")}>Åpne Assistant <ArrowRight size={15} /></button>
          <button className="btn-ghost" onClick={() => go("models")}>Modeller</button></div>
      </div>
      {none && (
        <div className="glass animate-rise rounded-[24px] p-5 ring-1 ring-nx-blue/30">
          <div className="flex items-center gap-4"><div className="grid h-11 w-11 flex-none place-items-center rounded-2xl bg-nx-blue/20"><Zap size={20} className="text-nx-blue" /></div>
            <div className="flex-1"><div className="font-medium">Last ned din første modell</div>
              <div className="text-sm text-white/55">{rec} (ca. 1,9 GB) passer fint for PC-en din. Du kan velge andre under Modeller.</div></div>
            <button className="btn-primary flex items-center gap-2" disabled={!!pulls[rec]} onClick={() => { pull(rec); go("models"); }}><Download size={15} />Last ned</button></div></div>)}
      {models && !models.online && (
        <div className="glass animate-rise rounded-[24px] p-5 text-sm text-rose-200 ring-1 ring-rose-400/30">Ollama kjører ikke. Start den, så er NEXUS klar.</div>)}
      <div className="grid gap-3 md:grid-cols-3">
        {stat(Cpu, "Ollama", health?.ollama_online ? "Online" : "Offline", health?.ollama_version ? "versjon " + health.ollama_version : "ikke tilkoblet", 60)}
        {stat(Database, "Modeller", String(models?.models.length ?? 0), model ? "Valgt: " + model : "ingen valgt", 120)}
        {stat(MessageSquare, "Samtaler", String(health?.conversations ?? 0), "lagret lokalt på PC-en", 180)}
      </div>
      <div className="glass animate-rise rounded-[24px] p-5" style={{ animationDelay: "240ms" }}>
        <div className="mb-2 text-sm font-medium">Siste samtaler</div>
        {recent === null && <div className="space-y-2">{[0, 1, 2].map((i) => <div key={i} className="skeleton h-9" />)}</div>}
        {recent?.length === 0 && <div className="py-3 text-sm text-white/40">Ingen samtaler ennå. Start en i Assistant.</div>}
        {recent?.map((c) => (
          <button key={c.id} onClick={() => go("assistant")} className="flex w-full items-center justify-between rounded-xl px-3 py-2.5 text-left text-sm transition hover:bg-white/8">
            <span className="truncate">{c.title}</span><span className="ml-4 flex-none text-xs text-white/35">{c.model} · {ago(c.updated_at)}</span></button>))}
      </div>
    </div>
  );
}
