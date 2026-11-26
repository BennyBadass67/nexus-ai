import { createContext, useCallback, useContext, useEffect, useRef, useState, ReactNode } from "react";
import { api, Prefs, Health, ModelsResp, Pull, streamPull } from "./api";

const DEF: Prefs = { agent_name: "NEXUS", user_name: "Benjamin", persona: "", theme: "dark", accent: "#5aa9ff", aurora: "on", perf: "light", reply_lang: "auto" };
function applyPrefs(p: Prefs) {
  const h = document.documentElement; const v = parseInt(p.accent.slice(1), 16);
  const rgb = [(v >> 16) & 255, (v >> 8) & 255, v & 255];
  const hi = rgb.map((x) => Math.round(x + (255 - x) * 0.55));
  const sh = [rgb[2], rgb[0], rgb[1]].map((x) => Math.round(x * 0.55 + 70));
  h.style.setProperty("--accent", rgb.join(" ")); h.style.setProperty("--accent-hi", hi.join(" ")); h.style.setProperty("--accent2", sh.join(" "));
  h.classList.toggle("midnight", p.theme === "midnight"); h.classList.toggle("light", p.theme === "light");
  h.classList.toggle("noaurora", p.aurora === "off" || p.perf === "light"); h.classList.toggle("perf", p.perf === "light");
}
type Ctx = {
  prefs: Prefs; setPrefs: (p: Partial<Prefs>) => void;
  health: Health | null; models: ModelsResp | null; model: string;
  setModel: (m: string) => void; refresh: () => Promise<void>;
  pulls: Record<string, Pull>; pull: (name: string) => void; cancelPull: (name: string) => void;
};
const C = createContext<Ctx>(null as unknown as Ctx);
export const useApp = () => useContext(C);

export function Provider({ children }: { children: ReactNode }) {
  const [prefs, setPrefsState] = useState<Prefs>(() => { try { return { ...DEF, ...JSON.parse(localStorage.getItem("nexus.prefs") || "{}") }; } catch { return DEF; } });
  useEffect(() => { applyPrefs(prefs); localStorage.setItem("nexus.prefs", JSON.stringify(prefs)); }, [prefs]);
  useEffect(() => { api.prefs().then((p) => setPrefsState((c) => ({ ...c, ...p }))).catch(() => {}); }, []);
  const setPrefs = (p: Partial<Prefs>) => { setPrefsState((c) => ({ ...c, ...p })); api.savePrefs(p).catch(() => {}); };
  const [health, setHealth] = useState<Health | null>(null);
  const [models, setModels] = useState<ModelsResp | null>(null);
  const [model, setModelState] = useState(localStorage.getItem("nexus.model") || "");

  const refresh = useCallback(() => {
    api.health().then(setHealth).catch(() => setHealth(null));
    return api.models().then((m) => {
      setModels(m);
      setModelState((cur) => (cur && m.models.some((x) => x.name === cur) ? cur : m.models[0]?.name || ""));
    }).catch(() => setModels({ online: false, models: [], error: "Backend svarer ikke" }));
  }, []);

  useEffect(() => { refresh(); const t = setInterval(refresh, 10000); return () => clearInterval(t); }, [refresh]);
  const [pulls, setPulls] = useState<Record<string, Pull>>({});
  const aborts = useRef<Record<string, AbortController>>({});
  const pull = (name: string) => {
    if (aborts.current[name]) return;
    const ac = new AbortController(); aborts.current[name] = ac;
    setPulls((p) => ({ ...p, [name]: { status: "starter…" } }));
    streamPull(name, (u) => setPulls((p) => ({ ...p, [name]: { ...p[name], ...u } })), ac.signal)
      .catch((e) => { if (e.name !== "AbortError") setPulls((p) => ({ ...p, [name]: { status: "", error: String(e.message || e) } })); else setPulls((p) => { const { [name]: _, ...rest } = p; return rest; }); })
      .finally(() => { delete aborts.current[name]; refresh(); api.benchAuto().catch(() => {});
        setTimeout(() => setPulls((p) => (p[name]?.done ? (({ [name]: _, ...r }) => r)(p) : p)), 3000); });
  };
  const cancelPull = (name: string) => aborts.current[name]?.abort();
  const setModel = (m: string) => { localStorage.setItem("nexus.model", m); setModelState(m); };
  return <C.Provider value={{ prefs, setPrefs, health, models, model, setModel, refresh, pulls, pull, cancelPull }}>{children}</C.Provider>;
}
