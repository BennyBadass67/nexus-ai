import { useEffect, useState } from "react";
import { Check, X, Ban, Play, Loader2 } from "lucide-react";
import { api, Activity } from "../api";

const ST: Record<string, { c: string; l: string }> = { ok: { c: "text-emerald-300", l: "utført" }, error: { c: "text-rose-300", l: "feil" }, denied: { c: "text-amber-300", l: "avslått" }, stopped: { c: "text-amber-300", l: "stoppet" },
  start: { c: "text-nx-blue", l: "startet" }, done: { c: "text-emerald-300", l: "ferdig" }, max_steps: { c: "text-amber-300", l: "maks steg" } };

export default function ActivityPage() {
  const [rows, setRows] = useState<Activity[] | null>(null);
  useEffect(() => { const f = () => api.activity(150).then(setRows).catch(() => setRows([])); f(); const t = setInterval(f, 3000); return () => clearInterval(t); }, []);
  return (
    <div className="glass flex h-full flex-col overflow-hidden rounded-[28px] p-6">
      <h1 className="text-xl font-semibold">Activity</h1>
      <p className="mb-4 text-sm text-white/50">Alt agenten har gjort på PC-en din, med tidspunkt og utfall. Lagret lokalt.</p>
      <div className="flex-1 space-y-1.5 overflow-auto pr-1">
        {rows === null && <Loader2 className="animate-spin text-white/40" />}
        {rows?.length === 0 && <div className="glass-soft rounded-2xl p-5 text-sm text-white/55">Ingenting ennå. Slå på agent-modus (skiftenøkkelen) i Assistant og be den gjøre noe.</div>}
        {rows?.map((r) => {
          const st = ST[r.status] ?? { c: "text-white/50", l: r.status };
          const I = r.kind === "run" ? Play : r.status === "ok" ? Check : r.status === "denied" || r.status === "stopped" ? Ban : r.status === "error" ? X : Check;
          return (
            <div key={r.id} className="glass-soft rounded-xl px-4 py-2.5 text-sm">
              <div className="flex items-center gap-3"><I size={14} className={st.c} />
                <span className="min-w-0 flex-1 truncate">{r.kind === "run" ? (r.detail || "Kjøring") : r.detail}</span>
                <span className={`text-xs ${st.c}`}>{st.l}</span>
                <span className="w-16 text-right text-xs tabular-nums text-white/35">{new Date(r.ts * 1000).toLocaleTimeString("nb-NO", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}</span></div>
              {r.result && r.kind === "tool" && <div className="mt-1 truncate pl-7 text-xs text-white/40" title={r.result}>{r.result.replace(/\s+/g, " ")}</div>}
            </div>);
        })}
      </div>
    </div>
  );
}
