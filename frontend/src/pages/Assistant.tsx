import { useEffect, useRef, useState } from "react";
import { Plus, ArrowUp, Square, Trash2, Copy, Check, RotateCw, ChevronDown, Sparkles, Pencil, Wrench, Download, Paperclip, FileText, Lightbulb, Loader2 } from "lucide-react";
import { api, Conv, extrasApi, Msg, smartApi, Step, streamAgent, streamChat, Tpl } from "../api";
import Steps from "../components/Steps";
import { useApp } from "../store";
import Markdown from "../components/Markdown";

const SUGGEST = ["Forklar hva du kan hjelpe meg med", "Skriv en kort e-post til en kunde", "Lag en plan for uka mi", "Forklar noe vanskelig enkelt"];

export default function Assistant({ openId, onOpened, goModels }: { openId: number | null; onOpened: () => void; goModels: () => void }) {
  const { model, models, setModel, health, refresh, prefs } = useApp();
  const [convs, setConvs] = useState<Conv[]>([]);
  const [cid, setCid] = useState<number | null>(null);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const tokBuf = useRef(""); const tokTimer = useRef<number | null>(null);
  const flushTok = () => { tokTimer.current = null; const t = tokBuf.current; tokBuf.current = ""; if (!t) return;
    setMsgs((m) => { const c = [...m]; const l = c[c.length - 1]; if (!l) return m; c[c.length - 1] = { ...l, content: l.content + t }; return c; }); };
  const [agentMode, setAgentModeS] = useState(localStorage.getItem("nexus.agent") === "1");
  const setAgentMode = (v: boolean) => { localStorage.setItem("nexus.agent", v ? "1" : "0"); setAgentModeS(v); };
  const runId = useRef<string | null>(null);
  const [notice, setNotice] = useState("");
  const patchStep = (id: string, p: Partial<Step>) => setMsgs((m) => m.map((x) => (x.steps ? { ...x, steps: x.steps.map((st) => (st.call_id === id ? { ...st, ...p } : st)) } : x)));
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [pick, setPick] = useState(false);
  const [sugg, setSugg] = useState<string[]>([]); const [suggBusy, setSuggBusy] = useState(false);
  const [tpls, setTpls] = useState<Tpl[]>([]); const [tplOpen, setTplOpen] = useState(false);
  const fileIn = useRef<HTMLInputElement>(null);
  const attach = async (f: File) => {
    if (f.size > 120_000) { setErr(`${f.name} er for stor (maks 120 kB tekst). Bruk Kunnskap under Workspace for store filer.`); return; }
    const t = await f.text();
    if (t.includes("\u0000")) { setErr(`${f.name} ser ikke ut som en tekstfil.`); return; }
    setErr(""); setText((x) => (x ? x + "\n\n" : "") + "Fil: " + f.name + "\n```\n" + t + "\n```\n");
  };
  const [copied, setCopied] = useState<number | null>(null);
  const abort = useRef<AbortController | null>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const area = useRef<HTMLTextAreaElement>(null);
  const stick = useRef(true);

  const loadList = () => api.conversations().then(setConvs).catch(() => {});
  useEffect(() => { loadList(); }, []);
  useEffect(() => {
    if (openId === null) return;
    if (openId === -1) fresh(); else open(openId);
    onOpened();
  }, [openId]); // eslint-disable-line
  useEffect(() => { if (stick.current) scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: busy ? "auto" : "smooth" }); }, [msgs]);
  useEffect(() => { const a = area.current; if (a) { a.style.height = "auto"; a.style.height = Math.min(a.scrollHeight, 180) + "px"; } }, [text]);

  const open = async (id: number) => {
    if (busy) return;
    const c = await api.conversation(id);
    setCid(id); setMsgs(c.messages); setErr(""); stick.current = true;
  };
  const fresh = () => { if (!busy) { setCid(null); setMsgs([]); setErr(""); area.current?.focus(); } };

  const run = async (message: string, regenerate = false) => {
    if (!model) { setErr("Ingen modell valgt. Last ned en under Models."); return; }
    setErr(""); setNotice(""); setSugg([]); setBusy(true); stick.current = true; runId.current = null;
    setMsgs((m) => {
      const base = regenerate && m[m.length - 1]?.role === "assistant" ? m.slice(0, -1) : [...m, { role: "user" as const, content: message }];
      return [...base, { role: "assistant", content: "", model }];
    });
    abort.current = new AbortController();
    let id = cid;
    try {
      const handler = (e: import("../api").ChatEvent) => {
        if (e.type === "meta") { id = e.conversation_id; setCid(e.conversation_id); runId.current = e.run_id ?? null; }
        else if (e.type === "token") { tokBuf.current += e.text; if (!tokTimer.current) tokTimer.current = window.setTimeout(flushTok, 100); }
        else if (e.type === "stats") { if (tokTimer.current) clearTimeout(tokTimer.current); flushTok(); setMsgs((m) => { const c = [...m]; c[c.length - 1] = { ...c[c.length - 1], tps: e.tokens / Math.max(e.seconds, 0.01) }; return c; }); }
        else if (e.type === "tool_call") { flushTok(); setMsgs((m) => { const c = [...m]; const l = c[c.length - 1]; c[c.length - 1] = { ...l, steps: [...(l.steps ?? []), { call_id: e.call_id, tool: e.tool, describe: e.describe, risk: e.risk, status: e.needs_approval ? "waiting" : "running" }] }; return c; }); }
        else if (e.type === "tool_result") patchStep(e.call_id, { status: e.status, result: e.result });
        else if (e.type === "notice") setNotice(e.text);
        else if (e.type === "final") { if (tokTimer.current) clearTimeout(tokTimer.current); tokBuf.current = ""; setMsgs((m) => { const c = [...m]; c[c.length - 1] = { ...c[c.length - 1], content: e.text }; return c; }); }
        else if (e.type === "stopped") setErr("Stoppet. Ingenting mer ble gjort.");
        else if (e.type === "error") setErr(e.message);
      };
      if (agentMode && !regenerate) await streamAgent({ message, model, conversation_id: cid }, handler, abort.current.signal);
      else await streamChat({ message, model, conversation_id: cid, regenerate }, handler, abort.current.signal);
    } catch (e: any) { if (e.name !== "AbortError") setErr(String(e.message || e)); }
    finally {
      if (tokTimer.current) clearTimeout(tokTimer.current); flushTok();
      setBusy(false); loadList(); refresh();
      setMsgs((m) => (m.length && m[m.length - 1].role === "assistant" && !m[m.length - 1].content ? m.slice(0, -1) : m));
      if (id && cid === null && !regenerate) smartApi.autotitle(id, model).then((r) => { if (r.changed) loadList(); }).catch(() => {});
    }
  };
  const send = () => { const t = text.trim(); if (!t || busy) return; setText(""); run(t); };
  const lastUser = [...msgs].reverse().find((m) => m.role === "user")?.content;

  const noModel = models?.online && models.models.length === 0;
  return (
    <div className="flex h-full gap-3">
      <aside className="glass hidden w-64 flex-col rounded-[28px] p-3 xl:flex">
        <button className="btn-primary mb-3 flex items-center justify-center gap-2" onClick={fresh}><Plus size={16} />Ny samtale</button>
        <div className="flex-1 space-y-0.5 overflow-auto">
          {convs.length === 0 && <div className="px-3 py-6 text-center text-xs text-white/35">Samtaler dukker opp her</div>}
          {convs.map((c) => (
            <div key={c.id} onClick={() => open(c.id)}
              className={`group flex cursor-pointer items-center justify-between rounded-xl px-3 py-2.5 text-sm transition ${c.id === cid ? "bg-white/14" : "text-white/70 hover:bg-white/8"}`}>
              <span className="truncate">{c.title}</span>
              <button title="Slett" className="ml-2 opacity-0 transition group-hover:opacity-60 hover:!opacity-100"
                onClick={async (ev) => { ev.stopPropagation(); await api.remove(c.id); if (c.id === cid) fresh(); loadList(); }}><Trash2 size={13} /></button>
            </div>))}
        </div>
      </aside>
      <section className="glass flex min-w-0 flex-1 flex-col overflow-hidden rounded-[28px]">
        <div ref={scroller} className="flex-1 overflow-auto px-6 pt-6" onScroll={(e) => { const t = e.currentTarget; stick.current = t.scrollHeight - t.scrollTop - t.clientHeight < 80; }}>
          <div className="mx-auto max-w-3xl space-y-6 pb-6">
            {msgs.length === 0 && (
              <div className="flex min-h-[55vh] animate-rise flex-col items-center justify-center text-center">
                <div className="mb-5 grid h-16 w-16 place-items-center rounded-3xl text-[#04101f] shadow-[0_12px_40px_-8px_rgb(var(--accent)/.8)]" style={{ background: "linear-gradient(135deg,rgb(var(--accent-hi)),rgb(var(--accent)) 60%,rgb(var(--accent2)))" }}><Sparkles size={28} /></div>
                <h1 className="text-[28px] font-semibold tracking-tight">Hei, Benjamin</h1>
                <p className="mt-1 text-white/50">{noModel ? "Du trenger en modell først." : health?.ollama_online === false ? "Ollama er ikke startet." : "Hva vil du jobbe med?"}</p>
                {noModel ? <button className="btn-primary mt-5" onClick={goModels}>Last ned en modell</button> : (
                  <div className="mt-7 grid w-full max-w-xl gap-2 sm:grid-cols-2">
                    {SUGGEST.map((s, i) => <button key={s} onClick={() => run(s)} style={{ animationDelay: `${i * 60}ms` }}
                      className="animate-rise rounded-2xl glass-soft px-4 py-3 text-left text-sm text-white/75 transition hover:-translate-y-0.5 hover:bg-white/10">{s}</button>)}
                  </div>)}
              </div>)}
            {msgs.map((m, i) => {
              const last = i === msgs.length - 1;
              return m.role === "user" ? (
                <div key={i} className="flex animate-rise justify-end">
                  <div className="max-w-[80%] whitespace-pre-wrap rounded-[22px] rounded-br-md px-4 py-3 text-[15px] leading-relaxed shadow-lg"
                    style={{ background: "linear-gradient(135deg, rgb(var(--accent) / .38), rgb(var(--accent2) / .3))", boxShadow: "inset 0 1px 0 rgba(255,255,255,.25)" }}>{m.content}</div>
                </div>
              ) : (
                <div key={i} className="group flex animate-rise gap-3">
                  <div className="mt-0.5 grid h-8 w-8 flex-none place-items-center rounded-xl bg-white/10"><Sparkles size={15} className="text-nx-blue" /></div>
                  <div className="min-w-0 flex-1 text-[15px] leading-[1.7] text-white/90">
                    {m.steps && m.steps.length > 0 && <Steps steps={m.steps} runId={runId.current} onChange={patchStep} />}
                    {m.content ? <div className={busy && last ? "cursor" : ""}><Markdown text={m.content} /></div> : <div className="flex gap-1.5 py-2.5">{[0, 1, 2].map((d) => <span key={d} className="h-2 w-2 animate-bounce rounded-full bg-white/40" style={{ animationDelay: `${d * 120}ms` }} />)}</div>}
                    {m.content && !(busy && last) && (
                      <div className="mt-2 flex items-center gap-3 text-[11px] text-white/35 opacity-0 transition group-hover:opacity-100">
                        <span>{m.model}{m.tps ? ` · ${m.tps.toFixed(1)} tok/s` : ""}</span>
                        <button className="flex items-center gap-1 hover:text-white" onClick={() => { navigator.clipboard.writeText(m.content); setCopied(i); setTimeout(() => setCopied(null), 1500); }}>
                          {copied === i ? <><Check size={12} />Kopiert</> : <><Copy size={12} />Kopier</>}</button>
                        {last && lastUser && <button className="flex items-center gap-1 hover:text-white" onClick={() => run(lastUser, true)}><RotateCw size={12} />Prøv igjen</button>}
                      </div>)}
                  </div>
                </div>);
            })}
          </div>
        </div>
        {notice && <div className="mx-6 mb-2 rounded-xl bg-amber-400/10 px-4 py-2 text-xs text-amber-100">{notice}</div>}
        {sugg.length > 0 && !busy && <div className="mx-6 mb-2 flex flex-wrap gap-2">{sugg.map((s, i) => <button key={s} onClick={() => { setSugg([]); run(s); }} className="animate-pop rounded-full glass-soft px-3.5 py-1.5 text-sm transition hover:-translate-y-0.5 hover:bg-white/15 active:scale-95" style={{ animationDelay: `${i * 70}ms` }}>{s}</button>)}</div>}
        {err && <div className="mx-6 mb-2 animate-pop rounded-xl bg-rose-500/12 px-4 py-2.5 text-sm text-rose-200 ring-1 ring-rose-400/20">{err}</div>}
        <div className="px-6 pb-5">
          <div className="glass-soft mx-auto flex max-w-3xl items-end gap-2 rounded-[22px] p-2 pl-4 transition focus-within:ring-1 focus-within:ring-nx-blue/50">
            <textarea ref={area} value={text} onChange={(e) => setText(e.target.value)} rows={1} placeholder={`Skriv til ${prefs.agent_name}…`} autoFocus
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
              className="max-h-44 min-h-[40px] flex-1 resize-none bg-transparent py-2.5 text-[15px] outline-none placeholder:text-white/30" />
            <input ref={fileIn} type="file" className="hidden" accept=".txt,.md,.csv,.json,.py,.js,.ts,.tsx,.html,.css,.log,.yaml,.yml,.xml,.sql,.java,.c,.cpp,.cs,.go,.rs" onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) attach(f); }} />
            <button onClick={() => fileIn.current?.click()} title="Legg ved tekstfil" className="grid h-10 w-10 place-items-center rounded-xl text-white/55 transition hover:bg-white/10"><Paperclip size={16} /></button>
            <div className="relative">
              <button onClick={() => { setTplOpen((v) => !v); extrasApi.templates().then(setTpls).catch(() => {}); }} title="Maler" className="grid h-10 w-10 place-items-center rounded-xl text-white/55 transition hover:bg-white/10"><FileText size={16} /></button>
              {tplOpen && (<>
                <div className="fixed inset-0 z-20" onClick={() => setTplOpen(false)} />
                <div className="glass absolute bottom-12 right-0 z-30 w-72 animate-pop rounded-2xl p-1.5">
                  {tpls.length === 0 && <div className="p-3 text-xs text-white/60">Ingen maler. Lag dem under Notater, fanen Maler.</div>}
                  {tpls.map((t) => <button key={t.id} onClick={() => { setText((x) => (x ? x + "\n" : "") + t.body); setTplOpen(false); area.current?.focus(); }} className="block w-full rounded-xl px-3 py-2 text-left text-sm hover:bg-white/10"><div className="font-medium">{t.title}</div><div className="truncate text-xs text-white/55">{t.body}</div></button>)}
                </div></>)}
            </div>
            {cid && msgs.length > 0 && !busy && <button onClick={() => { setSuggBusy(true); smartApi.suggest(cid, model).then((r) => setSugg(r.suggestions)).catch(() => setSugg([])).finally(() => setSuggBusy(false)); }} title="Foreslå oppfølgingsspørsmål" className="grid h-10 w-10 place-items-center rounded-xl text-white/55 transition hover:bg-white/10">{suggBusy ? <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white/80" /> : <Lightbulb size={16} />}</button>}
            {cid && msgs.length > 0 && <a href={`/api/conversations/${cid}/export`} download title="Last ned samtalen som Markdown" className="grid h-10 w-10 place-items-center rounded-xl text-white/55 transition hover:bg-white/10"><Download size={16} /></a>}
            <button onClick={() => setAgentMode(!agentMode)} title={agentMode ? "Agent-modus er på: kan bruke filer og nett" : "Slå på agent-modus"}
              className={`grid h-10 w-10 place-items-center rounded-xl transition ${agentMode ? "bg-nx-blue/25 text-nx-ice ring-1 ring-nx-blue/60" : "text-white/45 hover:bg-white/10"}`}><Wrench size={16} /></button>
            <div className="relative">
              <button onClick={() => setPick((v) => !v)} className="flex h-10 items-center gap-1.5 rounded-xl px-3 text-xs text-white/60 transition hover:bg-white/10">
                <span className="max-w-[120px] truncate">{model || "ingen modell"}</span><ChevronDown size={13} /></button>
              {pick && (<>
                <div className="fixed inset-0 z-20" onClick={() => setPick(false)} />
                <div className="glass absolute bottom-12 right-0 z-30 w-60 animate-pop rounded-2xl p-1.5">
                  {!models?.models.length && <div className="p-3 text-xs text-white/50">Ingen modeller installert</div>}
                  {models?.models.map((m) => (
                    <button key={m.name} onClick={() => { setModel(m.name); setPick(false); }}
                      className="flex w-full items-center justify-between rounded-xl px-3 py-2 text-left text-sm hover:bg-white/10">
                      <span className="truncate">{m.name}</span>{m.name === model && <Check size={14} className="text-nx-blue" />}</button>))}
                  <div className="my-1 border-t border-white/10" />
                  <button onClick={() => { setPick(false); goModels(); }} className="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-sm text-white/60 hover:bg-white/10"><Pencil size={13} />Administrer modeller</button>
                </div></>)}
            </div>
            {busy
              ? <button className="btn-primary grid h-10 w-10 place-items-center !p-0" title="Stopp" onClick={() => { if (runId.current) api.stopRun(runId.current).catch(() => {}); else abort.current?.abort(); }}><Square size={14} fill="currentColor" /></button>
              : <button className="btn-primary grid h-10 w-10 place-items-center !p-0" title="Send" disabled={!text.trim()} onClick={send}><ArrowUp size={18} strokeWidth={2.5} /></button>}
          </div>
          <div className="mt-2 text-center text-[11px] text-white/30">{agentMode ? "Agent-modus: kan lese filer og søke på nettet (søkeord sendes til DuckDuckGo). Skriving og sletting krever din godkjenning." : "Lokal modell · samtalen forlater aldri PC-en"}</div>
        </div>
      </section>
    </div>
  );
}
