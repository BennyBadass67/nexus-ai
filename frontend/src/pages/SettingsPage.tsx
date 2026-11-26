import { useApp } from "../store";

export default function SettingsPage() {
  const { health, model } = useApp();
  const rows: [string, string][] = [
    ["Backend", health ? "kjører" : "svarer ikke"],
    ["Ollama", health?.ollama_online ? "tilkoblet v" + health.ollama_version : "ikke tilkoblet"],
    ["Valgt modell", model || "ingen"],
    ["Datalagring", "Lokalt: %USERPROFILE%\\.nexus-ai\\nexus.db"],
    ["Cloud", "Av. Ingenting sendes ut av PC-en."],
  ];
  return (
    <div className="glass h-full overflow-auto rounded-3xl p-6">
      <h1 className="text-xl font-semibold">Settings</h1>
      <p className="mb-5 text-sm text-white/50">Status akkurat nå. Redigerbare innstillinger (API-nøkler, tillatelser) kommer i fase 2 og 4.</p>
      {rows.map(([k, v]) => (
        <div key={k} className="flex justify-between border-t border-white/5 py-3 text-sm"><span className="text-white/60">{k}</span><span>{v}</span></div>
      ))}
    </div>
  );
}
