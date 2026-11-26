import { useEffect, useState } from "react";
import { Moon, Sun, MoonStar, Check } from "lucide-react";
import { useApp } from "../store";

const ACCENTS = ["#5aa9ff", "#8b7bff", "#c084fc", "#ff6b9d", "#ff8a5b", "#f5c542", "#34d399", "#22d3ee"];
const THEMES = [
  { id: "dark", label: "Mørk", icon: Moon }, { id: "midnight", label: "Midnatt", icon: MoonStar }, { id: "light", label: "Lys", icon: Sun },
] as const;
const PERSONAS = [
  { label: "Vennlig og kort", text: "Vær varm, vennlig og kortfattet. Gå rett på sak." },
  { label: "Direkte og kritisk", text: "Vær ærlig og direkte. Si fra når noe er en dårlig idé, og foreslå bedre alternativer." },
  { label: "Lærer", text: "Forklar steg for steg med enkle eksempler, som til en nysgjerrig nybegynner." },
  { label: "Kodehjelper", text: "Du er en erfaren utvikler. Gi kjørbar kode først, korte forklaringer etterpå." },
];

export default function SettingsPage() {
  const { health, model, prefs, setPrefs } = useApp();
  const [name, setName] = useState(prefs.agent_name);
  const [user, setUser] = useState(prefs.user_name);
  const [persona, setPersona] = useState(prefs.persona);
  const [saved, setSaved] = useState(false);
  useEffect(() => { setName(prefs.agent_name); setUser(prefs.user_name); setPersona(prefs.persona); }, [prefs.agent_name, prefs.user_name, prefs.persona]);
  const dirty = name !== prefs.agent_name || user !== prefs.user_name || persona !== prefs.persona;
  const save = () => { setPrefs({ agent_name: name.trim() || "NEXUS", user_name: user.trim() || "Benjamin", persona }); setSaved(true); setTimeout(() => setSaved(false), 1800); };
  const field = "w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm outline-none focus:border-nx-blue/60";
  const Sec = ({ t, d, children }: { t: string; d?: string; children: React.ReactNode }) => (
    <section className="glass-soft rounded-2xl p-5"><h2 className="font-semibold">{t}</h2>{d && <p className="mb-4 mt-0.5 text-xs text-white/50">{d}</p>}{!d && <div className="mb-3" />}{children}</section>);
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
          <label className="glass-soft flex cursor-pointer items-center gap-2 rounded-full py-1 pl-1 pr-3 text-xs">
            <input type="color" value={prefs.accent} onChange={(e) => setPrefs({ accent: e.target.value })} className="h-7 w-7 cursor-pointer rounded-full border-0 bg-transparent p-0" />Egen farge</label></div>
        <label className="mt-4 flex cursor-pointer items-center gap-3 text-sm">
          <input type="checkbox" checked={prefs.perf === "light"} onChange={(e) => setPrefs({ perf: e.target.checked ? "light" : "full" })} className="h-4 w-4 accent-[rgb(var(--accent))]" />
          Lett grafikk <span className="text-xs text-white/40">(anbefalt: ingen blur/animasjon, så PC-en holder seg rask mens modellen jobber)</span></label>
        <label className="mt-2 flex cursor-pointer items-center gap-3 text-sm">
          <input type="checkbox" disabled={prefs.perf === "light"} checked={prefs.aurora === "on" && prefs.perf === "full"} onChange={(e) => setPrefs({ aurora: e.target.checked ? "on" : "off" })} className="h-4 w-4 accent-[rgb(var(--accent))]" />
          Animert bakgrunn <span className="text-xs text-white/40">(slå av for å spare batteri)</span></label>
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

      <Sec t="Status">
        {([["Backend", health ? "kjører" : "svarer ikke"], ["Ollama", health?.ollama_online ? "tilkoblet v" + health.ollama_version : "ikke tilkoblet"],
          ["Valgt modell", model || "ingen"], ["Datalagring", "Lokalt på PC-en (%USERPROFILE%\\.nexus-ai)"], ["Cloud", "Av. Ingenting sendes ut av PC-en."]] as [string, string][]).map(([k, v]) => (
          <div key={k} className="flex justify-between border-t border-white/5 py-2.5 text-sm"><span className="text-white/60">{k}</span><span>{v}</span></div>))}
      </Sec>
    </div>
  );
}
