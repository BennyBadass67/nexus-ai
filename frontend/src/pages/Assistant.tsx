import { useEffect, useRef, useState } from "react";
import { Plus, ArrowUp, Square, Trash2, Copy, Check, RotateCw, ChevronDown, Sparkles, Pencil } from "lucide-react";
import { api, Conv, Msg, streamChat } from "../api";
import { useApp } from "../store";
import Markdown from "../components/Markdown";

const SUGGEST = ["Forklar hva du kan hjelpe meg med", "Skriv en kort e-post til en kunde", "Lag en plan for uka mi", "Forklar noe vanskelig enkelt"];

export default function Assistant({ openId, onOpened, goModels }: { openId: number | null; onOpened: () => void; goModels: () => void }) {
  const { model, models, setModel, health, refresh } = useApp();
  const [convs, setConvs] = useState<Conv[]>([]);
  const [cid, setCid] = useState<number | null>(null);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [pick, setPick] = useState(false);
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
    setErr(""); setBusy(true); stick.current = true;
    setMsgs((m) => {
      const base = regenerate && m[m.length - 1]?.role === "assistant" ? m.slice(0, -1) : [...m, { role: "user" as const, content: message }];
      return [...base, { role: "assistant", content: "", model }];
    });
    abort.current = new AbortController();
    let id = cid;
    try {
      await streamChat({ message, model, conversation_id: cid, regenerate }, (e) => {
        if (e.type === "meta") { id = e.conversation_id; setCid(e.conversation_id); }
        else if (e.type === "token") setMsgs((m) => { const c = [...m]; const l = c[c.length - 1]; c[c.length - 1] = { ...l, content: l.content + e.text }; return c; });
        else if (e.type === "stats") setMsgs((m) => { const c = [...m]; c[c.length - 1] = { ...c[c.length - 1], tps: e.tokens / Math.max(e.seconds, 0.01) }; return c; });
        else if (e.type === "error") setErr(e.message);
      }, abort.current.signal);
    } catch (e: any) { if (e.name !== "AbortError") setErr(String(e.message || e)); }
    finally {
      setBusy(false); loadList(); refresh();
      setMsgs((m) => (m.length && m[m.length - 1].role === "assistant" && !m[m.length - 1].content ? m.slice(0, -1) : m));
      void id;
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
                <div className="mb-5 grid h-16 w-16 place-items-center rounded-3xl text-[#04101f] shadow-[0_12px_40px_-8px_rgba(90,169,255,.8)]" style={{ background: "linear-gradient(135deg,#d5ebff,#6b9bff 60%,#8d6bff)" }}><Sparkles size={28} /></div>
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
                    style={{ background: "linear-gradient(135deg, rgba(90,169,255,.38), rgba(110,120,255,.3))", boxShadow: "inset 0 1px 0 rgba(255,255,255,.25)" }}>{m.content}</div>
                </div>
              ) : (
                <div key={i} className="group flex animate-rise gap-3">
                  <div className="mt-0.5 grid h-8 w-8 flex-none place-items-center rounded-xl bg-white/10"><Sparkles size={15} className="text-nx-blue" /></div>
                  <div className="min-w-0 flex-1 text-[15px] leading-[1.7] text-white/90">
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
        {err && <div className="mx-6 mb-2 animate-pop rounded-xl bg-rose-500/12 px-4 py-2.5 text-sm text-rose-200 ring-1 ring-rose-400/20">{err}</div>}
        <div className="px-6 pb-5">
          <div className="glass-soft mx-auto flex max-w-3xl items-end gap-2 rounded-[22px] p-2 pl-4 transition focus-within:ring-1 focus-within:ring-nx-blue/50">
            <textarea ref={area} value={text} onChange={(e) => setText(e.target.value)} rows={1} placeholder="Skriv en melding…" autoFocus
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
              className="max-h-44 min-h-[40px] flex-1 resize-none bg-transparent py-2.5 text-[15px] outline-none placeholder:text-white/30" />
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
              ? <button className="btn-primary grid h-10 w-10 place-items-center !p-0" title="Stopp" onClick={() => abort.current?.abort()}><Square size={14} fill="currentColor" /></button>
              : <button className="btn-primary grid h-10 w-10 place-items-center !p-0" title="Send" disabled={!text.trim()} onClick={send}><ArrowUp size={18} strokeWidth={2.5} /></button>}
          </div>
          <div className="mt-2 text-center text-[11px] text-white/30">Lokal modell · samtalen forlater aldri PC-en</div>
        </div>
      </section>
    </div>
  );
}
