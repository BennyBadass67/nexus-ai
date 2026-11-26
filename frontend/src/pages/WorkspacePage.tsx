import { useEffect, useState } from "react";
import { Folder, FileText, ArrowUp, ExternalLink, Loader2, ChevronRight, Lock } from "lucide-react";
import KnowledgePanel from "../components/KnowledgePanel";
import { wsApi, WsList, WsFile, fmtSize } from "../api";

export default function WorkspacePage({ goSettings }: { goSettings: () => void }) {
  const [tab, setTab] = useState<"files" | "k">("files");
  const [roots, setRoots] = useState<string[]>([]);
  const [cur, setCur] = useState<WsList | null>(null);
  const [file, setFile] = useState<WsFile | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const clean = (e: unknown) => String(e).replace(/^Error: \d+ /, "").replace(/^\{"detail":"(.*)"\}$/, "$1");
  const go = (p: string) => { setErr(""); setFile(null); setBusy(true); wsApi.list(p).then(setCur).catch((e) => setErr(clean(e))).finally(() => setBusy(false)); };
  useEffect(() => { wsApi.roots().then((r) => { const rs = r.roots.filter((x) => x.exists).map((x) => x.path); setRoots(rs); if (rs[0]) go(rs[0]); }).catch((e) => setErr(clean(e))); }, []); // eslint-disable-line
  const view = (p: string) => { setErr(""); wsApi.read(p).then(setFile).catch((e) => setErr(clean(e))); };
  const crumbs = cur ? cur.path.split(/[\\/]/).filter(Boolean) : [];
  return (
    <div className="glass flex h-full flex-col overflow-hidden rounded-[28px] p-6">
      <div className="flex items-center gap-3">
        <div><h1 className="text-xl font-semibold">Workspace</h1>
          <p className="text-sm text-white/50">Mappene agenten har lov til å jobbe i. Alt utenfor er låst.</p></div>
        <div className="ml-auto flex gap-1 rounded-2xl glass-soft p-1 text-sm">
          {([["files", "Filer"], ["k", "Kunnskap"]] as const).map(([id, l]) => <button key={id} onClick={() => setTab(id)} className={`rounded-xl px-3 py-1.5 transition ${tab === id ? "bg-white/15 font-medium" : "text-white/60"}`}>{l}</button>)}</div>
        <button onClick={goSettings} className="rounded-2xl glass-soft px-3 py-2 text-xs text-white/70 hover:text-white">Endre mapper</button>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        {roots.map((r) => <button key={r} onClick={() => go(r)} className="flex items-center gap-2 rounded-full glass-soft px-3 py-1.5 text-xs text-white/70 hover:text-white"><Lock size={11} className="text-nx-blue" />{r}</button>)}
      </div>
      {err && <div className="mt-2 text-sm text-rose-300">{err}</div>}
      {tab === "k" ? <KnowledgePanel /> : (
      <div className="mt-3 flex min-h-0 flex-1 gap-3">
        <div className="flex min-w-0 flex-1 flex-col rounded-2xl glass-soft p-3">
          <div className="mb-2 flex items-center gap-1 overflow-x-auto whitespace-nowrap text-xs text-white/45">
            <button disabled={!cur?.parent} onClick={() => cur?.parent && go(cur.parent)} title="Opp" className="mr-1 rounded-lg p-1 hover:bg-white/10 disabled:opacity-30"><ArrowUp size={14} /></button>
            {crumbs.slice(-4).map((c, i) => <span key={i} className="flex items-center gap-1">{i > 0 && <ChevronRight size={10} />}{c}</span>)}
          </div>
          <div className="flex-1 space-y-0.5 overflow-auto">
            {busy && <Loader2 className="animate-spin text-white/40" />}
            {cur?.items.length === 0 && <div className="p-4 text-sm text-white/45">Tom mappe</div>}
            {cur?.items.map((i) => (
              <button key={i.path} onClick={() => (i.dir ? go(i.path) : view(i.path))}
                className={`flex w-full items-center gap-3 rounded-lg px-3 py-1.5 text-left text-sm hover:bg-white/10 ${file?.path === i.path ? "bg-white/10" : ""}`}>
                {i.dir ? <Folder size={15} className="flex-none text-nx-blue" /> : <FileText size={15} className="flex-none text-white/40" />}
                <span className="min-w-0 flex-1 truncate">{i.name}</span>
                {!i.dir && <span className="text-xs text-white/35">{fmtSize(i.size)}</span>}
              </button>))}
            {cur?.truncated && <div className="p-2 text-xs text-white/40">Viser de første 300.</div>}
          </div>
        </div>
        <div className="hidden min-w-0 flex-1 flex-col rounded-2xl glass-soft p-3 md:flex">
          {!file ? <div className="grid flex-1 place-items-center text-sm text-white/40">Velg en fil for forhåndsvisning</div> : (<>
            <div className="mb-2 flex items-center gap-2 text-xs text-white/50"><span className="min-w-0 flex-1 truncate" title={file.path}>{file.path}</span>
              <button onClick={() => wsApi.open(file.path).catch((e) => setErr(clean(e)))} className="flex items-center gap-1 rounded-lg px-2 py-1 hover:bg-white/10"><ExternalLink size={12} />Åpne</button></div>
            {file.binary ? <div className="grid flex-1 place-items-center text-sm text-white/45">Binærfil ({fmtSize(file.size)}), ingen forhåndsvisning</div>
              : <pre className="flex-1 overflow-auto whitespace-pre-wrap break-words text-xs leading-relaxed text-white/80">{file.text}{file.truncated ? "\n[… avkortet]" : ""}</pre>}
          </>)}
        </div>
      </div>)}
    </div>
  );
}
