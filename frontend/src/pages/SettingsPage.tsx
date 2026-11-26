import { useEffect, useState } from "react";
import { Moon, Sun, MoonStar, Check, Sparkles } from "lucide-react";
import { api, ToolInfo, updateApi, UpdateInfo, UpdateStatus } from "../api";
import { useApp } from "../store";

const ACCENTS = ["#e8553f", "#5aa9ff", "#8b7bff", "#c084fc", "#ff6b9d", "#ff8a5b", "#f5c542", "#34d399", "#22d3ee"];
const THEMES = [
  { id: "glass", label: "Varm glass", icon: Sparkles }, { id: "dark", label: "Mørk", icon: Moon }, { id: "midnight", label: "Midnatt", icon: MoonStar }, { id: "light", label: "Lys", icon: Sun },
] as const;
const PERSONAS = [
  { label: "Vennlig og kort", text: "Vær varm, vennlig og kortfattet. Gå rett på sak." },
  { label: "Direkte og kritisk", text: "Vær ærlig og direkte. Si fra når noe er en dårlig idé, og foreslå bedre alternativer." },
  { label: "Lærer", text: "Forklar steg for steg med enkle eksempler, som til en nysgjerrig nybegynner." },
  { label: "Kodehjelper", text: "Du er en erfaren utvikler. Gi kjørbar kode først, korte forklaringer etterpå." },
];

function Sec({ t, d, children }: { t: string; d?: string; children: React.ReactNode }) {
  return (
    <section className="glass-soft rounded-2xl p-5"><h2 className="font-semibold">{t}</h2>{d && <p className="mb-4 mt-0.5 text-xs text-white/50">{d}</p>}{!d && <div className="mb-3" />}{children}</section>);
}

export default function SettingsPage() {
  const [upd, setUpd] = useState<UpdateInfo | null>(null); const [updBusy, setUpdBusy] = useState(false);
  const checkUpd = () => { setUpdBusy(true); updateApi.check().then(setUpd).catch((e) => setUpd({ current: "?", latest: null, available: false, url: null, notes: "", error: String(e) })).finally(() => setUpdBusy(false)); };
  useEffect(() => { checkUpd(); }, []); // eslint-disable-line
  const [us, setUs] = useState<UpdateStatus | null>(null); const [installErr, setInstallErr] = useState("");
  const install = async () => {
    setInstallErr("");
    try { await updateApi.install(); } catch (e) { setInstallErr(String(e).replace(/^Error: \d+ /, "").replace(/^\{"detail":"(.*)"\}$/, "$1")); return; }
    const t = setInterval(() => updateApi.status().then((s) => { setUs(s); if (s.state === "error" || s.state === "started") clearInterval(t); }).catch(() => { clearInterval(t); }), 600);
  };
  const busyInstall = us?.state === "downloading" || us?.state === "launching";
  const { health, model, prefs, setPrefs } = useApp();
  const [name, setName] = useState(prefs.agent_name);
  const [user, setUser] = useState(prefs.user_name);
  const [persona, setPersona] = useState(prefs.persona);
  const [saved, setSaved] = useState(false);
  useEffect(() => { setName(prefs.agent_name); setUser(prefs.user_name); setPersona(prefs.persona); }, [prefs.agent_name, prefs.user_name, prefs.persona]);
  const [roots, setRoots] = useState(""); const [tl, setTl] = useState<ToolInfo[]>([]); const [rootMsg, setRootMsg] = useState("");
  useEffect(() => { api.agentConfig().then((c) => { setRoots(c.roots.join("\n")); setTl(c.tools); }).catch(() => {}); }, []);
  const saveRoots = async () => { try { const r = await api.saveRoots(roots.split("\n").map((x) => x.trim()).filter(Boolean)); setRoots(r.roots.join("\n")); setRootMsg("Lagret."); } catch (e: any) { setRootMsg(String(e.message || e).replace(/^\d+ /, "")); } setTimeout(() => setRootMsg(""), 4000); };
  const dirty = name !== prefs.agent_name || user !== prefs.user_name || persona !== prefs.persona;
  const save = () => { setPrefs({ agent_name: name.trim() || "NEXUS", user_name: user.trim() || "Benjamin", persona }); setSaved(true); setTimeout(() => setSaved(false), 1800); };
  const field = "w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm outline-none focus:border-nx-blue/60";
  return (
    <div className="h-full space-y-3 overflow-auto pr-1">
      <div className="glass rounded-[28px] p-6"><h1 className="text-xl font-semibold">Tilpass</h1>
        <p className="text-sm text-white/50">Endringer gjelder med en gang og huskes til neste gang.</p></div>

      <Sec t="Utseende" d="Tema og aksentfarge brukes overalt i appen.">
        <div className="flex flex-wrap gap-2">{THEMES.map(({ id, label, icon: I }) => (
          <button key={id} onClick={() => setPrefs({ theme: id })}
            className={`flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm transition ${prefs.theme === id ? "bg-nx-blue/25 ring-1 ring-nx-blue/70" : "glass-soft hover:bg-white/10"}`}><I size={15} />{label}</button>))}</div>
        <div className="mt-4 text-xs text-white/50">Aksentfarge</div>
        <div className="mt-2 flex flex-wrap items-center gap-2.5">
          {ACCENTS.map((c) => (
            <button key={c} aria-label={c} onClick={() => setPrefs({ accent: c })} style={{ background: c }}
              className="grid h-9 w-9 place-items-center rounded-full transition hover:scale-110 active:scale-95">{prefs.accent.toLowerCase() === c && <Check size={16} className="text-black/70" />}</button>))}
          <label className="glass-soft flex cursor-pointer items-center gap-2 rounded-full py-1 pl-1 pr-3 text-xs" title="Velg hvilken som helst farge">
            <input type="color" value={prefs.accent} onChange={(e) => setPrefs({ accent: e.target.value })} className="h-7 w-7 cursor-pointer rounded-full border-0 bg-transparent p-0" />Egen farge</label></div>
        <label className="mt-4 flex cursor-pointer items-center gap-3 text-sm">
          <input type="checkbox" checked={prefs.perf === "light"} onChange={(e) => setPrefs({ perf: e.target.checked ? "light" : "full" })} className="h-4 w-4 accent-[rgb(var(--accent))]" />
          Lett grafikk <span className="text-xs text-white/40">(anbefalt: ingen blur/animasjon, så PC-en holder seg rask mens modellen jobber)</span></label>
        <label className="mt-2 flex cursor-pointer items-center gap-3 text-sm">
          <input type="checkbox" disabled={prefs.perf === "light"} checked={prefs.aurora === "on" && prefs.perf === "full"} onChange={(e) => setPrefs({ aurora: e.target.checked ? "on" : "off" })} className="h-4 w-4 accent-[rgb(var(--accent))]" />
          Animert bakgrunn <span className="text-xs text-white/40">(slå av for å spare batteri)</span></label>
        <label className="mt-2 flex cursor-pointer items-center gap-3 text-sm">
          <input type="checkbox" checked={prefs.intro !== "off"} onChange={(e) => setPrefs({ intro: e.target.checked ? "on" : "off" })} className="h-4 w-4 accent-[rgb(var(--accent))]" />
          Introanimasjon når appen åpnes</label>
      </Sec>

      <Sec t="Skjermstyring" d="La agenter se skjermen og styre mus og tastatur. Alt skjer lokalt på PC-en, og ingenting sendes ut.">
        <label className="flex cursor-pointer items-center gap-3 text-sm">
          <input type="checkbox" checked={prefs.screen_control === "on"} onChange={(e) => setPrefs({ screen_control: e.target.checked ? "on" : "off" })} className="h-4 w-4 accent-[rgb(var(--accent))]" />
          Tillat agenten å bruke skjerm, mus og tastatur</label>
        <ul className="mt-3 list-disc space-y-1 pl-5 text-xs text-white/55">
          <li>Hver handling (skjermbilde, klikk, skriving, tast) må godkjennes av deg i chatten før den utføres.</li>
          <li>Nødstopp: flytt musepekeren til øvre venstre hjørne av skjermen, så avbrytes alt. Du kan også trykke Stopp i chatten.</li>
          <li>Maks 30 handlinger i minuttet. Windows-tasten, Alt+F4 og Ctrl+Alt+Delete er blokkert.</li>
          <li>Agenten rører ikke vinduer som ser ut som passord, BankID eller innlogging.</li>
          <li>Skjermbilder beskrives av en lokal visjonsmodell (last ned moondream under Models) og lagres bare på PC-en.</li></ul>
        <img src="/api/screen/last" alt="" className="mt-3 hidden max-h-40 rounded-xl" onLoad={(e) => e.currentTarget.classList.remove("hidden")} />
        <div className="mt-1 text-[11px] text-white/40">Over: siste skjermbilde agenten tok (vises bare hvis det finnes).</div>
      </Sec>

      <Sec t="Din agent" d="Navn og personlighet. Teksten under sendes som instruks til modellen i hver samtale.">
        <div className="grid gap-3 md:grid-cols-2">
          <div><div className="mb-1 text-xs text-white/50">Agentens navn</div><input className={field} maxLength={24} value={name} onChange={(e) => setName(e.target.value)} /></div>
          <div><div className="mb-1 text-xs text-white/50">Hva skal agenten kalle deg?</div><input className={field} maxLength={40} value={user} onChange={(e) => setUser(e.target.value)} /></div></div>
        <div className="mb-1 mt-3 text-xs text-white/50">Personlighet / egne instrukser</div>
        <div className="mb-2 flex flex-wrap gap-1.5">{PERSONAS.map((p) => (
          <button key={p.label} className="rounded-lg bg-white/8 px-2.5 py-1 text-xs hover:bg-white/15" onClick={() => setPersona(p.text)}>{p.label}</button>))}</div>
        <textarea className={field + " min-h-[110px] resize-y"} maxLength={4000} value={persona} onChange={(e) => setPersona(e.target.value)}
          placeholder="F.eks. «Svar alltid på norsk, vær litt sarkastisk, og avslutt med et tips.»" />
        <div className="mt-3 flex items-center gap-3"><button className="btn-primary" disabled={!dirty} onClick={save}>Lagre</button>
          {saved && <span className="animate-fade text-sm text-emerald-300">Lagret. Gjelder fra neste melding.</span>}</div>
      </Sec>

      <Sec t="PC-kontroll (agent-modus)" d="Mapper agenten får lese og skrive i. Alt utenfor er låst. Én mappe per linje.">
        <textarea className={field + " min-h-[84px] font-mono text-xs"} value={roots} onChange={(e) => setRoots(e.target.value)} spellCheck={false} />
        <div className="mt-2 flex items-center gap-3"><button className="btn-primary" onClick={saveRoots}>Lagre mapper</button>{rootMsg && <span className="text-sm text-white/60">{rootMsg}</span>}</div>
        <div className="mb-1.5 mt-4 text-xs text-white/50">Verktøy agenten har</div>
        <div className="flex flex-wrap gap-1.5">{tl.map((t) => (
          <span key={t.name} title={t.description} className={`rounded-lg px-2 py-1 text-xs ${t.needs_approval ? "bg-amber-400/15 text-amber-200" : "bg-white/8 text-white/70"}`}>{t.name}{t.needs_approval ? " · krever godkjenning" : ""}</span>))}</div>
        <p className="mt-3 text-xs text-white/40">Agenten kan ikke kjøre kommandoer, installere programmer eller endre systeminnstillinger. Sletting går til papirkurven.</p>
      </Sec>

      <Sec t="Oppdateringer" d="Sjekker GitHub for en nyere versjon.">
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <span className="text-white/60">Installert: <b className="text-white">{upd?.current ?? "…"}</b></span>
          <span className="text-white/60">Nyeste: <b className="text-white">{upd?.latest ?? "…"}</b></span>
          <button className="btn-primary" disabled={updBusy} onClick={checkUpd}>{updBusy ? "Sjekker…" : "Sjekk nå"}</button>
          {upd?.available && <button className="btn-primary" disabled={busyInstall || us?.state === "started"} onClick={install}>{busyInstall ? "Laster ned…" : `Installer ${upd.latest} nå`}</button>}
        </div>
        {upd && !upd.error && !upd.available && upd.current !== "dev" && <p className="mt-2 text-xs text-emerald-300">Du har nyeste versjon.</p>}
        {upd?.available && !us && <p className="mt-2 text-xs text-amber-200">Ny versjon finnes. «Installer nå» laster ned, lukker NEXUS, oppdaterer og åpner appen igjen.</p>}
        {busyInstall && us && <div className="mt-3"><div className="h-1.5 overflow-hidden rounded-full bg-white/10"><div className="h-full rounded-full bg-nx-blue transition-all" style={{ width: us.total ? `${(us.done / us.total) * 100}%` : "10%" }} /></div>
          <p className="mt-1 text-xs text-white/50">{us.state === "launching" ? "Starter installasjonen…" : `Laster ned ${(us.done / 1e6).toFixed(1)} av ${(us.total / 1e6).toFixed(1)} MB`}</p></div>}
        {us?.state === "started" && <p className="mt-2 text-sm text-emerald-300">Installasjonen er startet. NEXUS lukkes av seg selv og åpnes på nytt med versjon {us.version}. Hvis ikke noe skjer innen to minutter, kjør filen: {us.path}</p>}
        {(us?.state === "error" || installErr) && <p className="mt-2 text-sm text-rose-300">Oppdateringen feilet: {us?.error || installErr}</p>}
        {upd?.available && upd.url && <p className="mt-2 text-xs text-white/40">Alternativ: <a className="underline" href={upd.url} target="_blank" rel="noreferrer">last ned filen og kjør den selv</a> (lukk NEXUS først).</p>}
        {upd?.error && <p className="mt-2 text-xs text-rose-300">Kunne ikke sjekke: {upd.error}</p>}
      </Sec>

      <Sec t="Status">
        {([["Backend", health ? "kjører" : "svarer ikke"], ["Ollama", health?.ollama_online ? "tilkoblet v" + health.ollama_version : "ikke tilkoblet"],
          ["Valgt modell", model || "ingen"], ["Datalagring", "Lokalt på PC-en (%USERPROFILE%\\.nexus-ai)"], ["Cloud", "Av. Ingenting sendes ut av PC-en."]] as [string, string][]).map(([k, v]) => (
          <div key={k} className="flex justify-between border-t border-white/5 py-2.5 text-sm"><span className="text-white/60">{k}</span><span>{v}</span></div>))}
      </Sec>
    </div>
  );
}
