import { useEffect, useMemo, useState } from "react";
import { Home, MessageSquare, Boxes, FolderOpen, Workflow, Brain, Activity, Settings, Sparkles, Command } from "lucide-react";
import { Provider, useApp } from "./store";
import { api, Conv, updateApi } from "./api";
import HomePage from "./pages/HomePage";
import Assistant from "./pages/Assistant";
import Models from "./pages/Models";
import MemoryPage from "./pages/MemoryPage";
import WorkspacePage from "./pages/WorkspacePage";
import SettingsPage from "./pages/SettingsPage";
import ActivityPage from "./pages/ActivityPage";
import AgentsPage from "./pages/AgentsPage";
import Intro from "./components/Intro";
import CommandPalette, { Cmd } from "./components/CommandPalette";

const SECTIONS: Record<string, string> = { home: "Hoved", workspace: "Arbeid", activity: "System" };
let introShown = false;
const NAV = [
  { id: "home", label: "Home", icon: Home },
  { id: "assistant", label: "Assistant", icon: MessageSquare },
  { id: "models", label: "Models", icon: Boxes },
  { id: "workspace", label: "Workspace", icon: FolderOpen },
  { id: "automations", label: "Agenter", icon: Workflow },
  { id: "memory", label: "Memory", icon: Brain },
  { id: "activity", label: "Activity", icon: Activity },
  { id: "settings", label: "Settings", icon: Settings },
] as const;
type Page = (typeof NAV)[number]["id"];

function Shell() {
  const [page, setPage] = useState<Page>(() => (localStorage.getItem("nexus.page") as Page) || "home");
  const [palette, setPalette] = useState(false);
  const [openConv, setOpenConv] = useState<number | null>(null);
  const [convs, setConvs] = useState<Conv[]>([]);
  const [newVer, setNewVer] = useState<string | null>(null);
  useEffect(() => { updateApi.check().then((u) => u.available && setNewVer(u.latest)).catch(() => {}); }, []);
  const { health, model, models, setModel, pulls, prefs } = useApp();
  const online = !!health?.ollama_online;
    const nav = (p: Page) => { setPage(p); localStorage.setItem("nexus.page", p); };
  const pulling = Object.entries(pulls).filter(([, p]) => !p.done && !p.error);

  useEffect(() => {
    const h = (e: KeyboardEvent) => { if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setPalette((v) => !v); } };
    window.addEventListener("keydown", h); return () => window.removeEventListener("keydown", h);
  }, []);
  useEffect(() => { if (palette) api.conversations().then(setConvs).catch(() => {}); }, [palette]);

  const cmds: Cmd[] = useMemo(() => [
    ...NAV.map((n) => ({ id: "p" + n.id, label: n.label, hint: "Gå til", run: () => nav(n.id) })),
    { id: "new", label: "Ny samtale", hint: "Assistant", run: () => { setOpenConv(-1); nav("assistant"); } },
    ...(models?.models ?? []).map((m) => ({ id: "m" + m.name, label: m.name, hint: m.name === model ? "Valgt modell" : "Bytt modell", run: () => setModel(m.name) })),
    ...convs.map((c) => ({ id: "c" + c.id, label: c.title, hint: "Samtale", run: () => { setOpenConv(c.id); nav("assistant"); } })),
  ], [models, convs, model]); // eslint-disable-line

  return (
    <div className="flex h-full gap-3 p-3">
      <nav className="glass relative flex w-[76px] flex-col items-center gap-1 rounded-[28px] py-4 md:w-60 md:items-stretch md:px-3">
        <div className="mb-4 flex items-center gap-3 px-1 md:px-2">
          <img src="/logo.png" alt="" className="h-10 w-10 flex-none object-contain" />
          <div className="hidden md:block"><div className="text-[15px] font-semibold tracking-wide">{prefs.agent_name}</div>
            <div className="text-[11px] text-white/45">personlig agent</div></div>
        </div>
        <div className="relative flex flex-col gap-1">
          {NAV.map(({ id, label, icon: Icon }) => (
            <div key={id} className="contents">
              {SECTIONS[id] && <div className={`nav-label hidden px-4 pb-1 md:block ${id === "home" ? "" : "pt-3"}`}>{SECTIONS[id]}</div>}
              <button onClick={() => nav(id)} title={label}
                className={`nav-item relative flex h-11 items-center gap-3 rounded-2xl px-4 text-sm transition-all duration-200 ${page === id ? "on" : ""}`}>
                <Icon size={18} strokeWidth={page === id ? 2.2 : 1.8} /><span className="hidden md:inline">{label}</span>
                {id === "models" && pulling.length > 0 && <span className="absolute right-3 top-3.5 h-2 w-2 animate-pulse rounded-full bg-nx-blue" />}
              </button></div>))}
        </div>
        <button onClick={() => setPalette(true)} className="mx-1 mt-4 hidden items-center justify-between rounded-2xl glass-soft px-3 py-2 text-xs text-white/50 transition hover:bg-white/10 md:flex">
          <span className="flex items-center gap-2"><Command size={13} />Søk / kommando</span><span className="kbd">Ctrl K</span></button>
        {newVer && <button onClick={() => nav("settings")} className="mt-auto hidden rounded-2xl bg-nx-blue/20 px-3 py-2 text-left text-xs text-nx-blue md:block">Ny versjon {newVer} er klar. Trykk for å laste ned.</button>}
        <div className={`${newVer ? "mt-2" : "mt-auto"} hidden rounded-2xl glass-soft p-3 text-xs md:block`}>
          {pulling.length > 0 ? (<>
            <div className="text-white/70">Laster ned {pulling[0][0]}</div>
            <div className="mt-2 h-1 overflow-hidden rounded-full bg-white/10"><div className="h-full rounded-full bg-nx-blue transition-all"
              style={{ width: `${pulling[0][1].total ? ((pulling[0][1].completed || 0) / pulling[0][1].total) * 100 : 8}%` }} /></div></>) : (<>
            <div className="flex items-center gap-2"><span className={`h-2 w-2 rounded-full ${online ? "bg-emerald-400 shadow-[0_0_10px_#34d399]" : "bg-rose-400"}`} />
              {online ? "Ollama online" : "Ollama offline"}</div>
            <div className="mt-1 truncate text-white/45">{model || "ingen modell valgt"}</div></>)}
        </div>
      </nav>
      <main className="min-w-0 flex-1">
        <div key={page} className="h-full animate-rise">
          {page === "home" && <HomePage go={(p) => nav(p as Page)} />}
          {page === "assistant" && <Assistant openId={openConv} onOpened={() => setOpenConv(null)} goModels={() => nav("models")} />}
          {page === "models" && <Models />}
          {page === "workspace" && <WorkspacePage goSettings={() => nav("settings")} />}
          {page === "automations" && <AgentsPage />}
          {page === "memory" && <MemoryPage />}
          {page === "activity" && <ActivityPage />}
          {page === "settings" && <SettingsPage />}
        </div>
      </main>
      <CommandPalette open={palette} onClose={() => setPalette(false)} cmds={cmds} />
    </div>
  );
}

export default function App() {
  return (<Provider><div className="aurora"><i /><i /><i /></div><Shell /><IntroGate /></Provider>);
}

function IntroGate() {
  const { prefs } = useApp();
  const [show] = useState(() => { if (introShown || localStorage.getItem("nexus.prefs") && JSON.parse(localStorage.getItem("nexus.prefs")!).intro === "off") return false; introShown = true; return true; });
  return show ? <Intro name={prefs.agent_name} /> : null;
}
