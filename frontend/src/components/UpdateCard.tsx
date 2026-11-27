import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowRight, Check, Download, Loader2, PackageCheck, RefreshCw, Rocket, Search, TriangleAlert } from "lucide-react";
import { updateApi, UpdateInfo, UpdateStatus } from "../api";

type Phase = "checking" | "uptodate" | "available" | "downloading" | "installing" | "restarting" | "error";
const STEPS = ["Sjekk", "Last ned", "Installer", "Start på nytt"];
const stepIndex: Record<Phase, number> = { checking: 0, uptodate: 4, available: 0, downloading: 1, installing: 2, restarting: 3, error: -1 };

const mb = (n: number) => (n / 1e6).toFixed(1);
const fmtEta = (s: number) => (s < 5 ? "straks ferdig" : s < 60 ? `ca. ${Math.round(s)} sek igjen` : `ca. ${Math.ceil(s / 60)} min igjen`);

export default function UpdateCard() {
  const [info, setInfo] = useState<UpdateInfo | null>(null);
  const [phase, setPhase] = useState<Phase>("checking");
  const [st, setSt] = useState<UpdateStatus | null>(null);
  const [err, setErr] = useState("");
  const [speed, setSpeed] = useState(0);
  const [shown, setShown] = useState(0);            // glattet fremdrift 0..1
  const target = useRef(0); const samples = useRef<{ t: number; d: number }[]>([]);

  const check = useCallback(() => {
    setPhase("checking"); setErr("");
    const t0 = Date.now();
    updateApi.check().then((u) => {
      setInfo(u);
      const wait = Math.max(0, 700 - (Date.now() - t0));      // la sjekke-animasjonen få vises
      setTimeout(() => { if (u.error) { setErr("Kunne ikke sjekke: " + u.error); setPhase("error"); } else setPhase(u.available ? "available" : "uptodate"); }, wait);
    }).catch((e) => { setErr("Kunne ikke sjekke: " + String(e)); setPhase("error"); });
  }, []);
  useEffect(() => { check(); }, [check]);

  // jevn animasjon av fremdriftsfeltet mot siste målte verdi
  useEffect(() => {
    let raf = 0;
    const tick = () => { setShown((s) => s + (target.current - s) * 0.12); raf = requestAnimationFrame(tick); };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, []);

  // Etter at installeren er startet: vent på at den nye versjonen svarer. Svarer fortsatt gammel versjon etter 90 sek, har installasjonen feilet.
  const watchRestart = (to: string | null, path: string | null) => {
    const t0 = Date.now();
    const id = setInterval(() => {
      updateApi.check().then((u) => {
        if (to && u.current === to) { clearInterval(id); window.location.reload(); }
        else if (Date.now() - t0 > 90_000) { clearInterval(id); setErr(`Installasjonen ser ikke ut til å ha gått gjennom (appen kjører fortsatt ${u.current}).${path ? " Kjør filen selv: " + path : ""}`); setPhase("error"); }
      }).catch(() => { /* backend er nede mens installeren jobber */ });
    }, 3000);
  };

  const install = async () => {
    setErr(""); setSpeed(0); setShown(0); target.current = 0; samples.current = [];
    try { await updateApi.install(); } catch (e) { setErr(String(e).replace(/^Error: \d+ /, "").replace(/^\{"detail":"(.*)"\}$/, "$1")); setPhase("error"); return; }
    setPhase("downloading");
    let fails = 0;
    const t = setInterval(() => updateApi.status().then((s) => {
      fails = 0; setSt(s);
      if (s.total) target.current = s.done / s.total;
      const now = Date.now(); samples.current.push({ t: now, d: s.done });
      samples.current = samples.current.filter((x) => now - x.t < 4000);
      const a = samples.current[0]; if (a && now > a.t) setSpeed(((s.done - a.d) / (now - a.t)) * 1000);
      if (s.state === "launching") { target.current = 1; setPhase("installing"); }
      if (s.state === "started") { target.current = 1; setPhase("installing"); try { localStorage.setItem("nexus.updating", JSON.stringify({ from: info?.current, to: s.version })); } catch { /* */ } setTimeout(() => { setPhase("restarting"); watchRestart(s.version, s.path); }, 3500); clearInterval(t); }
      if (s.state === "error") { clearInterval(t); setErr(s.error || "Ukjent feil"); setPhase("error"); }
    }).catch(() => { if (++fails >= 3) { clearInterval(t); setPhase("restarting"); } }), 500);
  };

  const idx = stepIndex[phase];
  const pct = Math.round(Math.min(1, shown) * 100);
  const eta = st && st.total && speed > 50_000 ? (st.total - st.done) / speed : 0;

  return (
    <div className="upd">
      <div className="upd-steps">
        {STEPS.map((s, i) => (
          <div key={s} className={`upd-step ${i < idx ? "done" : i === idx ? "now" : ""}`}>
            <span className="upd-dot">{i < idx ? <Check size={12} strokeWidth={3} /> : i + 1}</span><span className="upd-lbl">{s}</span>
            {i < STEPS.length - 1 && <span className="upd-line"><i style={{ transform: `scaleX(${i < idx ? 1 : 0})` }} /></span>}
          </div>))}
      </div>

      <div key={phase} className="upd-body animate-pop">
        {phase === "checking" && <div className="upd-row"><span className="upd-ring"><Search size={18} /></span><div><div className="upd-h">Ser etter nyere versjon…</div><div className="upd-s">Kobler til GitHub</div></div></div>}

        {phase === "uptodate" && <div className="upd-row"><span className="upd-ok"><PackageCheck size={20} /></span><div className="flex-1"><div className="upd-h">Du har nyeste versjon</div><div className="upd-s">NEXUS {info?.current}</div></div>
          <button className="btn" onClick={check}><RefreshCw size={14} /> Sjekk igjen</button></div>}

        {phase === "available" && info && <div>
          <div className="upd-row"><span className="upd-ring on"><Rocket size={18} /></span>
            <div className="flex-1"><div className="upd-h">Ny versjon klar</div>
              <div className="upd-s flex items-center gap-2"><span>{info.current}</span><ArrowRight size={12} /><b className="text-nx-blue">{info.latest}</b></div></div>
            <button className="btn-primary" onClick={install}><Download size={15} /> Installer {info.latest} nå</button></div>
          {info.notes && <p className="upd-notes">{info.notes}</p>}
          {info.url && <p className="mt-2 text-xs text-white/55">Alternativ: <a className="underline" href={info.url} target="_blank" rel="noreferrer">last ned filen og kjør den selv</a> (lukk NEXUS først).</p>}
        </div>}

        {phase === "downloading" && <div>
          <div className="upd-row"><span className="upd-ring on"><Download size={18} /></span><div className="flex-1"><div className="upd-h">Laster ned {st?.version ?? info?.latest}</div>
            <div className="upd-s">{st && st.total ? `${mb(st.done)} av ${mb(st.total)} MB` : "Starter nedlasting…"}</div></div>
            <div className="upd-pct">{pct}<small>%</small></div></div>
          <div className="upd-bar"><div className="upd-fill" style={{ width: `${Math.max(2, pct)}%` }} /></div>
          <div className="upd-s mt-2 flex justify-between"><span>{speed > 0 ? `${(speed / 1e6).toFixed(1)} MB/s` : "måler hastighet…"}</span><span>{eta ? fmtEta(eta) : ""}</span></div>
        </div>}

        {phase === "installing" && <div>
          <div className="upd-row"><span className="upd-ring on spin"><Loader2 size={18} className="animate-spin" /></span><div className="flex-1"><div className="upd-h">Installerer {st?.version}</div>
            <div className="upd-s">NEXUS lukkes av seg selv og åpnes igjen. Ikke slå av PC-en.</div></div></div>
          <div className="upd-bar"><div className="upd-fill indet" /></div></div>}

        {phase === "restarting" && <div className="upd-row"><span className="upd-ring on"><Loader2 size={18} className="animate-spin" /></span><div className="flex-1"><div className="upd-h">Starter på nytt…</div>
          <div className="upd-s">Vinduet åpnes igjen med versjon {st?.version} om et øyeblikk. Skjer det ikke innen to minutter, kjør filen {st?.path}</div></div></div>}

        {phase === "error" && <div>
          <div className="upd-row"><span className="upd-err"><TriangleAlert size={20} /></span><div className="flex-1"><div className="upd-h">Oppdateringen stoppet</div><div className="upd-s">{err}</div></div>
            <button className="btn-primary" onClick={check}><RefreshCw size={14} /> Prøv igjen</button></div></div>}
      </div>
    </div>
  );
}

export function UpdatedToast({ version, notes, onClose }: { version: string; notes?: string; onClose: () => void }) {
  useEffect(() => { const t = setTimeout(onClose, 9000); return () => clearTimeout(t); }, [onClose]);
  return (
    <div className="upd-toast animate-pop" onClick={onClose} role="status">
      <div className="upd-burst">{Array.from({ length: 12 }).map((_, i) => <i key={i} style={{ ["--a" as string]: `${i * 30}deg`, animationDelay: `${i * 25}ms` }} />)}<span className="upd-ok big"><Check size={26} strokeWidth={3} /></span></div>
      <div><div className="upd-h">Oppdatert til {version}</div><div className="upd-s">{notes || "Alt er klart. Takk for tålmodigheten."}</div></div>
    </div>
  );
}

/** Automatisk oppdatering: viser fremdrift når backend laster ned i bakgrunnen, og tilbyr omstart når filen er klar. */
export function AutoUpdateBar() {
  const [st, setSt] = useState<UpdateStatus | null>(null); const [hide, setHide] = useState<string | null>(null); const [err, setErr] = useState("");
  useEffect(() => {
    let alive = true;
    const tick = () => updateApi.status().then((s) => alive && setSt(s)).catch(() => {});
    tick(); const id = setInterval(tick, 4000); return () => { alive = false; clearInterval(id); };
  }, []);
  const go = async () => { setErr(""); try { await updateApi.install(); } catch (e) { setErr(String(e).replace(/^Error: \d+ /, "").replace(/^\{"detail":"(.*)"\}$/, "$1")); } };
  if (st && st.state === "error" && hide !== "err:" + st.error) return (
    <div className="upd-toast animate-pop" role="status" style={{ bottom: 20 }}>
      <span className="upd-err"><TriangleAlert size={18} /></span>
      <div><div className="upd-h">Automatisk oppdatering stoppet</div><div className="upd-s">{st.error}</div>
        <div className="mt-2 flex gap-2"><button className="btn-primary" onClick={go}><RefreshCw size={14} /> Prøv igjen</button><button className="btn-ghost" onClick={() => setHide("err:" + st.error)}>Lukk</button></div></div>
    </div>);
  if (!st || (st.state !== "downloading" && st.state !== "ready" && st.state !== "launching" && st.state !== "started")) return null;
  const pct = st.total ? Math.round((st.done / st.total) * 100) : 0;
  if (st.state === "downloading") return (
    <div className="upd-toast animate-pop" role="status" style={{ bottom: 20 }}>
      <span className="upd-ring"><Download size={18} /></span>
      <div><div className="upd-h">Laster ned {st.version} i bakgrunnen</div><div className="upd-s">{pct ? `${pct} %` : "Starter…"} Du kan fortsette å bruke appen.</div></div>
    </div>);
  if (st.state === "ready" && hide !== st.version) return (
    <div className="upd-toast animate-pop" role="status" style={{ bottom: 20 }}>
      <span className="upd-ok"><Check size={18} strokeWidth={3} /></span>
      <div><div className="upd-h">Versjon {st.version} er klar</div><div className="upd-s">{err || "Lastet ned. Appen starter på nytt av seg selv under installasjonen."}</div>
        <div className="mt-2 flex gap-2"><button className="btn-primary" onClick={go}><Rocket size={14} /> Start på nytt og installer</button><button className="btn-ghost" onClick={() => setHide(st.version)}>Senere</button></div></div>
    </div>);
  if (st.state === "launching" || st.state === "started") return (
    <div className="upd-toast animate-pop" role="status" style={{ bottom: 20 }}><span className="upd-ring"><Loader2 size={18} className="animate-spin" /></span><div><div className="upd-h">Installerer {st.version}…</div><div className="upd-s">Appen starter på nytt.</div></div></div>);
  return null;
}
