import { createContext, useCallback, useContext, useEffect, useRef, useState, ReactNode } from "react";
import { api, builderApi, DesignerInfo, Prefs, Health, ModelsResp, Pull, streamPull } from "./api";

const DEF: Prefs = { agent_name: "NEXUS", user_name: "Benjamin", persona: "", theme: "glass", accent: "#e8553f", aurora: "on", perf: "light", reply_lang: "auto", intro: "on" };
function applyPrefs(p: Prefs) {
  const h = document.documentElement; const v = parseInt(p.accent.slice(1), 16);
  const rgb = [(v >> 16) & 255, (v >> 8) & 255, v & 255];
  const hi = rgb.map((x) => Math.round(x + (255 - x) * 0.55));
  const sh = p.theme === "glass" ? rgb.map((x) => Math.round(x * 0.72)) : [rgb[2], rgb[0], rgb[1]].map((x) => Math.round(x * 0.55 + 70));
  // Tekstfarge på aksentflater (WCAG AA 4,5:1): hvit hvis aksenten kan mørknes litt og gi nok kontrast, ellers mørk tekst.
  const lum = (c: number[]) => { const f = (v: number) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }; return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]); };
  const cr = (a: number[], b: number[]) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
  let deep = rgb, on = [255, 255, 255], ok = false;
  for (let f = 1; f >= 0.69; f -= 0.03) { const d = rgb.map((x) => Math.round(x * f)); if (cr([255, 255, 255], d) >= 4.6) { deep = d; ok = true; break; } }
  if (!ok) { on = [26, 15, 11]; deep = rgb; }
  h.style.setProperty("--accent-deep", deep.join(" ")); h.style.setProperty("--on-accent", on.join(" "));
  h.style.setProperty("--accent", rgb.join(" ")); h.style.setProperty("--accent-hi", hi.join(" ")); h.style.setProperty("--accent2", sh.join(" "));
  h.classList.toggle("midnight", p.theme === "midnight"); h.classList.toggle("light", p.theme === "light" || p.theme === "glass"); h.classList.toggle("glass", p.theme === "glass");
  h.classList.toggle("noaurora", p.aurora === "off" || p.perf === "light"); h.classList.toggle("perf", p.perf === "light");
}
type Ctx = {
  prefs: Prefs; setPrefs: (p: Partial<Prefs>) => void;
  health: Health | null; models: ModelsResp | null; model: string;
  setModel: (m: string) => void; refresh: () => Promise<void>;
  designer: DesignerInfo | null; pulls: Record<string, Pull>; pull: (name: string) => void; cancelPull: (name: string) => void;
};
const C = createContext<Ctx>(null as unknown as Ctx);
export const useApp = () => useContext(C);

export function Provider({ children }: { children: ReactNode }) {
  const [prefs, setPrefsState] = useState<Prefs>(() => { try { return { ...DEF, ...JSON.parse(localStorage.getItem("nexus.prefs") || "{}") }; } catch { return DEF; } });
  useEffect(() => { applyPrefs(prefs); localStorage.setItem("nexus.prefs", JSON.stringify(prefs)); }, [prefs]);
  useEffect(() => { api.prefs().then((p) => {
    // Engangs: nytt design (v2) blir standard første gang, brukeren kan bytte tilbake i Settings.
    if (!localStorage.getItem("nexus.design2")) { localStorage.setItem("nexus.design2", "1"); const m = { theme: "glass" as const, accent: "#e8553f" }; setPrefsState((c) => ({ ...c, ...p, ...m })); api.savePrefs(m).catch(() => {}); }
    else setPrefsState((c) => ({ ...c, ...p }));
  }).catch(() => {}); }, []);
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
  const [designer, setDesigner] = useState<DesignerInfo | null>(null);
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
  const cancelPull = (name: string) => { if (name === designer?.model) localStorage.setItem("nexus.designer.skip", "1"); aborts.current[name]?.abort(); };
  // Team-assistentens modell (valgt ut fra målt maskinvare) lastes ned automatisk første gang, med synlig fremdrift.
  const online = !!models?.online;
  useEffect(() => { if (online) builderApi.designer().then(setDesigner).catch(() => {}); }, [online, models?.models.length]);
  useEffect(() => {
    if (designer && designer.online && !designer.installed && !pulls[designer.model] && !localStorage.getItem("nexus.designer.skip")) pull(designer.model);
  }, [designer]); // eslint-disable-line
  const setModel = (m: string) => { localStorage.setItem("nexus.model", m); setModelState(m); };
  return <C.Provider value={{ prefs, setPrefs, health, models, model, setModel, refresh, designer, pulls, pull, cancelPull }}>{children}</C.Provider>;
}
