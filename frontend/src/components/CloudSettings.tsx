import { useEffect, useState } from "react";
import { Cloud, ExternalLink, Loader2, ShieldAlert, Check, X } from "lucide-react";
import { CloudProv, cloudApi } from "../api";
import { useApp } from "../store";

const clean = (e: unknown) => String(e).replace(/^Error: /, "").replace(/^\d+ /, "").replace(/^\{"detail":"(.*)"\}$/, "$1");
const field = "w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm outline-none focus:border-nx-blue/60";

function Card({ p, reload }: { p: CloudProv; reload: () => void }) {
  const { refresh } = useApp();
  const [key, setKey] = useState(""); const [acc, setAcc] = useState(p.account_id); const [url, setUrl] = useState(p.base_url); const [cm, setCm] = useState(p.custom_model);
  const [ok, setOk] = useState(false); const [busy, setBusy] = useState(""); const [msg, setMsg] = useState<{ good: boolean; t: string } | null>(null);
  const [open, setOpen] = useState(p.enabled);
  const body = () => ({ ...(key ? { api_key: key } : {}), ...(p.needs_account ? { account_id: acc } : {}), ...(p.custom ? { base_url: url, custom_model: cm } : {}) });
  const run = async (what: string, f: () => Promise<unknown>, done?: string) => {
    setBusy(what); setMsg(null);
    try { await f(); if (done) setMsg({ good: true, t: done }); setKey(""); reload(); refresh(); } catch (e) { setMsg({ good: false, t: clean(e) }); } finally { setBusy(""); }
  };
  const test = () => run("test", async () => {
    await cloudApi.save(p.id, body());
    const r = await cloudApi.test(p.id);
    if (!r.ok) throw new Error(r.error || "Testen feilet");
    setMsg({ good: true, t: `Fungerer. Svar fra ${r.model}: «${r.reply}». ${r.models?.length ?? 0} modeller funnet.` });
  });
  return (
    <div className="rounded-2xl border border-white/10 bg-white/5">
      <button className="flex w-full items-center gap-3 px-4 py-3 text-left" onClick={() => setOpen(!open)}>
        <Cloud size={16} /><span className="font-medium">{p.label}</span>
        {p.id === "cloudflare" && <span className="rounded-full bg-white/15 px-2 py-0.5 text-[11px]">anbefalt</span>}
        <span style={p.enabled ? { background: "#065f46", color: "#fff" } : undefined} className={`ml-auto rounded-full px-2.5 py-0.5 text-xs ${p.enabled ? "" : "bg-white/12"}`}>{p.enabled ? "på" : "av"}</span>
      </button>
      {open && <div className="animate-rise space-y-3 border-t border-white/10 px-4 py-4 text-sm">
        <p className="text-xs text-white/70">{p.free}</p>
        <p className="text-xs text-white/65">{p.key_help} {p.key_url && <a className="inline-flex items-center gap-1 underline" href={p.key_url} target="_blank" rel="noreferrer">Åpne <ExternalLink size={11} /></a>}</p>
        {p.needs_account && <input className={field} placeholder="Account ID (32 tegn)" value={acc} onChange={(e) => setAcc(e.target.value)} />}
        {p.custom && <><input className={field} placeholder="Base-URL, f.eks. https://tjeneste.example/v1" value={url} onChange={(e) => setUrl(e.target.value)} />
          <input className={field} placeholder="Modellnavn" value={cm} onChange={(e) => setCm(e.target.value)} /></>}
        <input className={field} type="password" autoComplete="off" placeholder={p.has_key ? `Nøkkel lagret (${p.key_hint}). Skriv ny for å bytte.` : p.custom ? "API-nøkkel (valgfri)" : "API-nøkkel"} value={key} onChange={(e) => setKey(e.target.value)} />
        {!p.enabled && <label className="flex items-start gap-2 text-xs"><input type="checkbox" className="mt-0.5" checked={ok} onChange={(e) => setOk(e.target.checked)} />
          <span>Jeg forstår at meldingene mine, og filer og minner agenten bruker i samtalen, sendes til {p.label} når jeg velger en skymodell.</span></label>}
        <div className="flex flex-wrap items-center gap-2">
          <button className="btn" disabled={!!busy || (!p.has_key && !key && !p.custom)} onClick={test}>{busy === "test" ? <Loader2 size={14} className="inline animate-spin" /> : null} Test tilkobling</button>
          {p.enabled
            ? <button className="btn" disabled={!!busy} onClick={() => run("off", () => cloudApi.save(p.id, { enabled: false }), "Slått av. Ingenting sendes lenger.")}>Slå av</button>
            : <button className="btn-primary" disabled={!!busy || !ok} onClick={() => run("on", async () => { await cloudApi.save(p.id, body()); await cloudApi.test(p.id).then((r) => { if (!r.ok) throw new Error(r.error); }); await cloudApi.save(p.id, { enabled: true, consent: true }); }, "Slått på. Modellene vises i modellvelgeren med sky-ikon.")}>Lagre og slå på</button>}
          {p.has_key && <button className="btn" disabled={!!busy} onClick={() => confirm("Slette nøkkelen fra denne PC-en?") && run("del", () => cloudApi.forget(p.id), "Nøkkel slettet.")}>Glem nøkkel</button>}
          <span className="ml-auto text-xs text-white/60">{p.requests_today} forespørsler i dag</span>
        </div>
        {msg && <div className={`flex items-start gap-2 text-xs ${msg.good ? "text-emerald-300" : "text-rose-300"}`}>{msg.good ? <Check size={13} className="mt-0.5 flex-none" /> : <X size={13} className="mt-0.5 flex-none" />}<span>{msg.t}</span></div>}
      </div>}
    </div>);
}

export default function CloudSettings() {
  const [ps, setPs] = useState<CloudProv[]>([]); const [err, setErr] = useState("");
  const load = () => cloudApi.list().then(setPs).catch((e) => setErr(clean(e)));
  useEffect(() => { load(); }, []);
  return (
    <div className="space-y-3">
      <div className="flex items-start gap-2.5 rounded-2xl bg-amber-500/12 px-4 py-3 text-xs ring-1 ring-amber-400/25"><ShieldAlert size={15} className="mt-0.5 flex-none" />
        <div>Sky er <b>av</b> som standard, og alt kjører lokalt til du selv slår på en leverandør. NEXUS bruker bare gratisnivåer: når kvoten er brukt opp, stopper den og sier fra. Den prøver aldri å omgå grenser og kan ikke betale for noe.
          Ærlig: ingen seriøs leverandør fungerer helt uten konto og nøkkel. Nøkkelen er gratis og lagres bare på denne PC-en.</div></div>
      {err && <div className="text-sm text-rose-300">{err}</div>}
      {ps.map((p) => <Card key={p.id + p.enabled} p={p} reload={load} />)}
    </div>);
}
