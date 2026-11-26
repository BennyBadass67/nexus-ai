import { createContext, useCallback, useContext, useEffect, useRef, useState, ReactNode } from "react";
import { api, Health, ModelsResp, Pull, streamPull } from "./api";

type Ctx = {
  health: Health | null; models: ModelsResp | null; model: string;
  setModel: (m: string) => void; refresh: () => void;
  pulls: Record<string, Pull>; pull: (name: string) => void; cancelPull: (name: string) => void;
};
const C = createContext<Ctx>(null as unknown as Ctx);
export const useApp = () => useContext(C);

export function Provider({ children }: { children: ReactNode }) {
  const [health, setHealth] = useState<Health | null>(null);
  const [models, setModels] = useState<ModelsResp | null>(null);
  const [model, setModelState] = useState(localStorage.getItem("nexus.model") || "");

  const refresh = useCallback(() => {
    api.health().then(setHealth).catch(() => setHealth(null));
    api.models().then((m) => {
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
      .finally(() => { delete aborts.current[name]; refresh();
        setTimeout(() => setPulls((p) => (p[name]?.done ? (({ [name]: _, ...r }) => r)(p) : p)), 3000); });
  };
  const cancelPull = (name: string) => aborts.current[name]?.abort();
  const setModel = (m: string) => { localStorage.setItem("nexus.model", m); setModelState(m); };
  return <C.Provider value={{ health, models, model, setModel, refresh, pulls, pull, cancelPull }}>{children}</C.Provider>;
}
