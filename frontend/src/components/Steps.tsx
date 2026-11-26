import { Check, X, ShieldAlert, Loader2, Wrench, FolderOpen, Globe, FileText, Trash2, Monitor, MousePointerClick, Keyboard } from "lucide-react";
import { api, Step } from "../api";

const ICON: Record<string, typeof Wrench> = { read_file: FileText, list_dir: FolderOpen, search_files: FolderOpen, web_search: Globe, fetch_url: Globe, open_url: Globe, write_file: FileText, delete_path: Trash2, screen_look: Monitor, focus_window: Monitor, mouse_click: MousePointerClick, scroll: MousePointerClick, type_text: Keyboard, press_key: Keyboard };

export default function Steps({ steps, runId, onChange }: { steps: Step[]; runId: string | null; onChange: (id: string, s: Partial<Step>) => void }) {
  const decide = async (st: Step, allow: boolean) => {
    onChange(st.call_id, { status: allow ? "running" : "denied" });
    try { if (runId) await api.approve(runId, st.call_id, allow); } catch { onChange(st.call_id, { status: "error", result: "Godkjenningen kom ikke frem (kjøringen er stoppet)." }); }
  };
  return (
    <div className="mb-2 space-y-1.5">
      {steps.map((st) => {
        const I = ICON[st.tool] || Wrench; const risky = st.risk === "write" || st.risk === "delete";
        return (
          <div key={st.call_id} className={`animate-pop rounded-xl px-3 py-2 text-[13px] ${st.status === "waiting" ? "bg-amber-400/12 ring-1 ring-amber-300/40" : "glass-soft"}`}>
            <div className="flex items-center gap-2.5">
              <I size={14} className="flex-none text-nx-blue" />
              <span className="min-w-0 flex-1 truncate">{st.describe}</span>
              {st.status === "running" && <Loader2 size={14} className="animate-spin text-white/50" />}
              {st.status === "ok" && <Check size={14} className="text-emerald-300" />}
              {st.status === "error" && <X size={14} className="text-rose-300" />}
              {st.status === "denied" && <span className="text-xs text-white/45">avslått</span>}
            </div>
            {st.status === "waiting" && (
              <div className="mt-2.5 flex items-center gap-2">
                <ShieldAlert size={14} className="flex-none text-amber-300" />
                <span className="flex-1 text-xs text-amber-100/90">{st.risk === "screen" ? "Agenten vil se skjermen din (lokalt). Tillat?" : st.risk === "control" ? "Agenten vil styre mus/tastatur på PC-en. Tillat?" : risky && st.risk === "delete" ? "Agenten vil flytte dette til papirkurven. Tillat?" : "Agenten vil gjøre en endring på PC-en. Tillat?"}</span>
                <button className="btn-ghost !py-1 text-xs" onClick={() => decide(st, false)}>Avslå</button>
                <button className="btn-primary !py-1 text-xs" onClick={() => decide(st, true)}>Tillat</button>
              </div>)}
            {(st.status === "error" || st.status === "ok") && st.result && st.tool !== "current_time" && (
              <details className="mt-1.5 text-xs text-white/45"><summary className="cursor-pointer select-none">Se resultat</summary>
                <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-black/25 p-2 font-mono text-[11px]">{st.result}</pre></details>)}
          </div>);
      })}
    </div>
  );
}
