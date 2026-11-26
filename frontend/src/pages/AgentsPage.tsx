import { useEffect, useRef, useState } from "react";
import { Plus, Users, Bot, Square, ArrowUp, Trash2, Sparkles, Eraser, Pencil, Check } from "lucide-react";
import { api, AgentDef, Room, RoomMsg, Step, streamRoom, teamApi, ToolInfo } from "../api";
import { useApp } from "../store";
import Markdown from "../components/Markdown";
import Steps from "../components/Steps";

const COLORS = ["#5aa9ff", "#c084fc", "#34d399", "#fbbf24", "#fb7185", "#22d3ee"];
const colorOf = (id: number | null, name: string) => id === null ? "#ffffff" : COLORS[(id + name.length) % COLORS.length];
type Live = { agent: string; agent_id?: number; text: string; steps: Step[]; done: boolean };

export default function AgentsPage() {
  const [tab, setTab] = useState<"rooms" | "agents">("rooms");
  const [agents, setAgents] = useState<AgentDef[]>([]);
  const [rooms, setRooms] = useState<Room[]>([]);
  const load = () => { teamApi.agents().then(setAgents).catch(() => {}); teamApi.rooms().then(setRooms).catch(() => {}); };
  useEffect(load, []);
  return (
    <div className="flex h-full flex-col gap-3">
      <div className="glass flex items-center justify-between rounded-[24px] px-5 py-3">
        <div><h1 className="text-lg font-semibold">Agenter</h1><p className="text-xs text-white/50">Flere agenter med egne roller som snakker sammen. Én modell kjører om gangen.</p></div>
        <div className="flex rounded-2xl bg-white/5 p-1">{([["rooms", "Rom", Users], ["agents", "Agenter", Bot]] as const).map(([id, l, I]) => (
          <button key={id} onClick={() => setTab(id)} className={`flex items-center gap-2 rounded-xl px-4 py-1.5 text-sm transition ${tab === id ? "bg-white/14" : "text-white/55 hover:text-white"}`}><I size={14} />{l}</button>))}</div>
      </div>
      <div className="min-h-0 flex-1">{tab === "rooms" ? <Rooms agents={agents} rooms={rooms} reload={load} goAgents={() => setTab("agents")} /> : <Agents agents={agents} reload={load} />}</div>
    </div>
  );
}

function Agents({ agents, reload }: { agents: AgentDef[]; reload: () => void }) {
  const { models } = useApp();
  const [tl, setTl] = useState<ToolInfo[]>([]);
  const [edit, setEdit] = useState<Partial<AgentDef> | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => { api.agentConfig().then((c) => setTl(c.tools)).catch(() => {}); }, []);
  const save = async () => { try { await teamApi.saveAgent(edit!); setEdit(null); setErr(""); reload(); } catch (e: any) { setErr(String(e.message || e).replace(/^\d+ /, "")); } };
  const field = "w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm outline-none focus:border-nx-blue/60";
  return (
    <div className="glass h-full overflow-auto rounded-[28px] p-5">
      <div className="mb-4 flex items-center justify-between"><div className="text-sm text-white/55">{agents.length} agent(er)</div>
        <button className="btn-primary flex items-center gap-2" onClick={() => setEdit({ name: "", role: "", prompt: "", model: null, tools: [] })}><Plus size={15} />Ny agent</button></div>
      {edit && (
        <div className="glass-soft mb-4 animate-pop space-y-3 rounded-2xl p-4">
          <div className="grid gap-3 md:grid-cols-2">
            <div><div className="mb-1 text-xs text-white/50">Navn</div><input className={field} maxLength={30} value={edit.name ?? ""} onChange={(e) => setEdit({ ...edit, name: e.target.value })} /></div>
            <div><div className="mb-1 text-xs text-white/50">Rolle (kort)</div><input className={field} maxLength={200} value={edit.role ?? ""} onChange={(e) => setEdit({ ...edit, role: e.target.value })} placeholder="f.eks. kritiker" /></div></div>
          <div><div className="mb-1 text-xs text-white/50">Instrukser</div><textarea className={field + " min-h-[90px]"} value={edit.prompt ?? ""} onChange={(e) => setEdit({ ...edit, prompt: e.target.value })} placeholder="Hvordan skal agenten tenke og svare?" /></div>
          <div><div className="mb-1 text-xs text-white/50">Modell (hver agent kan ha sin egen, men bytte av modell tar tid på 8 GB RAM)</div>
            <select className={field} value={edit.model ?? ""} onChange={(e) => setEdit({ ...edit, model: e.target.value || null })}>
              <option value="">Samme som valgt modell</option>{models?.models.map((m) => <option key={m.name} value={m.name}>{m.name}</option>)}</select></div>
          <div><div className="mb-1 text-xs text-white/50">Verktøy agenten får bruke (ingen = bare snakke)</div>
            <div className="flex flex-wrap gap-1.5">{tl.map((t) => { const on = edit.tools?.includes(t.name); return (
              <button key={t.name} title={t.description} onClick={() => setEdit({ ...edit, tools: on ? edit.tools!.filter((x) => x !== t.name) : [...(edit.tools ?? []), t.name] })}
                className={`rounded-lg px-2.5 py-1 text-xs transition ${on ? "bg-nx-blue/30 ring-1 ring-nx-blue/60" : "bg-white/8 text-white/60 hover:bg-white/15"}`}>{t.name}{t.needs_approval ? " 🔒" : ""}</button>); })}</div></div>
          {err && <div className="text-sm text-rose-300">{err}</div>}
          <div className="flex gap-2"><button className="btn-primary" disabled={!edit.name?.trim()} onClick={save}>Lagre</button><button className="btn-ghost" onClick={() => { setEdit(null); setErr(""); }}>Avbryt</button></div>
        </div>)}
      <div className="grid gap-3 md:grid-cols-2">
        {agents.map((a) => (
          <div key={a.id} className="glass-soft animate-rise rounded-2xl p-4">
            <div className="flex items-center gap-3"><div className="grid h-9 w-9 flex-none place-items-center rounded-xl text-sm font-semibold text-black/75" style={{ background: colorOf(a.id, a.name) }}>{a.name[0]}</div>
              <div className="min-w-0 flex-1"><div className="truncate font-medium">{a.name}</div><div className="truncate text-xs text-white/50">{a.role || "ingen rolle"} · {a.model || "valgt modell"}</div></div>
              <button className="text-white/45 hover:text-white" title="Rediger" onClick={() => setEdit(a)}><Pencil size={14} /></button>
              <button className="text-white/45 hover:text-rose-300" title="Slett" onClick={async () => { await teamApi.delAgent(a.id); reload(); }}><Trash2 size={14} /></button></div>
            {a.tools.length > 0 && <div className="mt-2 flex flex-wrap gap-1">{a.tools.map((t) => <span key={t} className="rounded-md bg-white/8 px-1.5 py-0.5 text-[11px] text-white/60">{t}</span>)}</div>}
          </div>))}
      </div>
      {agents.length === 0 && !edit && <div className="rounded-2xl bg-white/5 p-6 text-center text-sm text-white/55">Ingen agenter ennå. Lag en, eller gå til Rom og trykk «Lag eksempel».</div>}
    </div>
  );
}

function Rooms({ agents, rooms, reload, goAgents }: { agents: AgentDef[]; rooms: Room[]; reload: () => void; goAgents: () => void }) {
  const { model } = useApp();
  const [sel, setSel] = useState<number | null>(null);
  const [msgs, setMsgs] = useState<RoomMsg[]>([]);
  const [live, setLive] = useState<Live[]>([]);
  const [text, setText] = useState(""); const [busy, setBusy] = useState(false); const [err, setErr] = useState(""); const [notice, setNotice] = useState("");
  const [editing, setEditing] = useState<Partial<Room> | null>(null);
  const runId = useRef<string | null>(null); const abort = useRef<AbortController | null>(null); const scroller = useRef<HTMLDivElement>(null);
  const room = rooms.find((r) => r.id === sel) ?? null;
  const members = room ? room.agent_ids.map((i) => agents.find((a) => a.id === i)).filter(Boolean) as AgentDef[] : [];
  const open = async (id: number) => { setSel(id); setLive([]); setErr(""); setNotice(""); const r = await teamApi.room(id); setMsgs(r.messages); };
  useEffect(() => { if (sel === null && rooms.length) open(rooms[0].id); }, [rooms]); // eslint-disable-line
  useEffect(() => { scroller.current?.scrollTo({ top: scroller.current.scrollHeight }); }, [msgs, live]);
  const patchStep = (id: string, p: Partial<Step>) => setLive((l) => l.map((x) => ({ ...x, steps: x.steps.map((s) => (s.call_id === id ? { ...s, ...p } : s)) })));
  const send = async () => {
    const t = text.trim(); if (!t || busy || !room) return;
    if (!model && members.some((m) => !m.model)) { setErr("Ingen modell valgt. Last ned en under Models."); return; }
    setText(""); setBusy(true); setErr(""); setNotice(""); setLive([]); abort.current = new AbortController();
    try {
      await streamRoom(room.id, { message: t, default_model: model || members.find((m) => m.model)?.model || "" }, (e) => {
        if (e.type === "meta") runId.current = e.run_id;
        else if (e.type === "user_message") setMsgs((m) => [...m, { id: -1, author: "Du", agent_id: null, content: e.text, created_at: Date.now() / 1000 }]);
        else if (e.type === "turn_start") setLive((l) => [...l, { agent: e.agent, agent_id: e.agent_id, text: "", steps: [], done: false }]);
        else if (e.type === "token") setLive((l) => l.map((x, i) => (i === l.length - 1 ? { ...x, text: x.text + e.text } : x)));
        else if (e.type === "turn_end") setLive((l) => l.map((x, i) => (i === l.length - 1 ? { ...x, text: e.text, done: true } : x)));
        else if (e.type === "tool_call") setLive((l) => l.map((x, i) => (i === l.length - 1 ? { ...x, steps: [...x.steps, { call_id: e.call_id, tool: e.tool, describe: e.describe, risk: e.risk, status: e.needs_approval ? "waiting" : "running" }] } : x)));
        else if (e.type === "tool_result") patchStep(e.call_id, { status: e.status, result: e.result });
        else if (e.type === "notice") setNotice(e.text);
        else if (e.type === "stopped") setErr("Stoppet.");
        else if (e.type === "error") setErr(e.message);
      }, abort.current.signal);
    } catch (e: any) { if (e.name !== "AbortError") setErr(String(e.message || e)); }
    setBusy(false); runId.current = null;
    const r = await teamApi.room(room.id); setMsgs(r.messages); setLive([]);
  };
  const saveRoom = async () => { try { const r = await teamApi.saveRoom(editing!); setEditing(null); reload(); open(r.id); } catch (e: any) { setErr(String(e.message || e).replace(/^\d+ /, "")); } };
  const field = "w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm outline-none focus:border-nx-blue/60";
  const bubble = (author: string, id: number | null, content: string, key: string | number, cursor = false, steps?: Step[]) => {
    const you = author === "Du";
    return (
      <div key={key} className={`animate-rise flex gap-3 ${you ? "justify-end" : ""}`}>
        {!you && <div className="mt-0.5 grid h-8 w-8 flex-none place-items-center rounded-xl text-sm font-semibold text-black/75" style={{ background: colorOf(id, author) }}>{author[0]}</div>}
        <div className={`min-w-0 max-w-[85%] ${you ? "rounded-[20px] rounded-br-md px-4 py-2.5" : ""}`} style={you ? { background: "linear-gradient(135deg, rgba(var(--accent),.38), rgba(var(--accent2),.3))" } : {}}>
          {!you && <div className="mb-0.5 text-xs font-medium" style={{ color: colorOf(id, author) }}>{author}</div>}
          {steps && steps.length > 0 && <Steps steps={steps} runId={runId.current} onChange={patchStep} />}
          {content ? <div className={`text-[15px] leading-relaxed ${cursor ? "cursor" : ""}`}><Markdown text={content} /></div> : cursor ? <div className="py-1 text-white/40">tenker…</div> : null}
        </div></div>);
  };
  const idOf = (n: string) => agents.find((a) => a.name === n)?.id ?? null;
  return (
    <div className="flex h-full gap-3">
      <aside className="glass flex w-64 flex-none flex-col rounded-[28px] p-3">
        <button className="btn-primary mb-2 flex items-center justify-center gap-2" disabled={agents.length === 0} onClick={() => setEditing({ title: "", agent_ids: [], max_rounds: 2, mode: "roundrobin" })}><Plus size={15} />Nytt rom</button>
        <div className="flex-1 space-y-0.5 overflow-auto">
          {rooms.map((r) => (
            <div key={r.id} onClick={() => open(r.id)} className={`group flex cursor-pointer items-center justify-between rounded-xl px-3 py-2.5 text-sm ${r.id === sel ? "bg-white/14" : "text-white/70 hover:bg-white/8"}`}>
              <span className="truncate">{r.title}</span>
              <button className="ml-2 opacity-0 group-hover:opacity-60 hover:!opacity-100" onClick={async (e) => { e.stopPropagation(); await teamApi.delRoom(r.id); if (sel === r.id) { setSel(null); setMsgs([]); } reload(); }}><Trash2 size={13} /></button></div>))}
          {rooms.length === 0 && <div className="p-3 text-xs text-white/45">Ingen rom ennå.</div>}
        </div>
        <button className="btn-ghost mt-2 flex items-center justify-center gap-2 text-xs" onClick={async () => { const r = await teamApi.example(); reload(); setTimeout(() => open(r.id), 200); }}><Sparkles size={13} />Lag eksempel (3 agenter)</button>
        {agents.length === 0 && <button className="mt-2 text-xs text-nx-blue hover:underline" onClick={goAgents}>Eller lag agenter selv →</button>}
      </aside>
      <section className="glass flex min-w-0 flex-1 flex-col overflow-hidden rounded-[28px]">
        {editing ? (
          <div className="flex-1 overflow-auto p-6"><h2 className="mb-4 text-lg font-semibold">{editing.id ? "Rediger rom" : "Nytt rom"}</h2>
            <div className="max-w-xl space-y-4">
              <div><div className="mb-1 text-xs text-white/50">Navn på rommet</div><input className={field} value={editing.title ?? ""} onChange={(e) => setEditing({ ...editing, title: e.target.value })} /></div>
              <div><div className="mb-1 text-xs text-white/50">Hvem er med? (snakker i den rekkefølgen du velger)</div>
                <div className="flex flex-wrap gap-2">{agents.map((a) => { const on = editing.agent_ids?.includes(a.id); return (
                  <button key={a.id} onClick={() => setEditing({ ...editing, agent_ids: on ? editing.agent_ids!.filter((x) => x !== a.id) : [...(editing.agent_ids ?? []), a.id] })}
                    className={`flex items-center gap-2 rounded-xl px-3 py-2 text-sm ${on ? "bg-nx-blue/25 ring-1 ring-nx-blue/60" : "glass-soft hover:bg-white/10"}`}>{on && <Check size={13} />}{a.name}</button>); })}</div></div>
              <div className="grid gap-3 md:grid-cols-2">
                <div><div className="mb-1 text-xs text-white/50">Antall runder (maks {6})</div><input type="number" min={1} max={6} className={field} value={editing.max_rounds ?? 2} onChange={(e) => setEditing({ ...editing, max_rounds: Math.max(1, Math.min(6, +e.target.value || 1)) })} /></div>
                <div><div className="mb-1 text-xs text-white/50">Hvem snakker når?</div><select className={field} value={editing.mode} onChange={(e) => setEditing({ ...editing, mode: e.target.value as Room["mode"] })}>
                  <option value="roundrobin">Rund og rund</option><option value="leader">Første agent leder (velger hvem som snakker)</option></select></div></div>
              {err && <div className="text-sm text-rose-300">{err}</div>}
              <div className="flex gap-2"><button className="btn-primary" disabled={!editing.title?.trim() || !editing.agent_ids?.length} onClick={saveRoom}>Lagre</button><button className="btn-ghost" onClick={() => { setEditing(null); setErr(""); }}>Avbryt</button></div>
            </div></div>
        ) : !room ? (
          <div className="grid flex-1 place-items-center p-8 text-center"><div><Users size={34} className="mx-auto mb-3 text-nx-blue" /><div className="text-lg font-semibold">Agenter som snakker sammen</div>
            <p className="mx-auto mt-1 max-w-sm text-sm text-white/55">Lag et rom med flere agenter, gi dem en oppgave, og se dem diskutere i tur og orden. Prøv «Lag eksempel» til venstre.</p></div></div>
        ) : (<>
          <div className="flex items-center justify-between border-b border-white/8 px-5 py-3">
            <div><div className="font-medium">{room.title}</div><div className="text-xs text-white/45">{members.map((m) => m.name).join(" · ")} · {room.max_rounds} runde(r) · {room.mode === "leader" ? "leder" : "rund og rund"}</div></div>
            <div className="flex gap-1"><button className="btn-ghost !px-2.5" title="Rediger rom" onClick={() => setEditing(room)}><Pencil size={14} /></button>
              <button className="btn-ghost !px-2.5" title="Tøm samtalen" onClick={async () => { await teamApi.clearRoom(room.id); setMsgs([]); }}><Eraser size={14} /></button></div></div>
          <div ref={scroller} className="flex-1 space-y-4 overflow-auto px-6 py-5">
            {msgs.length === 0 && live.length === 0 && <div className="py-16 text-center text-sm text-white/45">Gi gruppen en oppgave eller et spørsmål.</div>}
            {msgs.map((m, i) => bubble(m.author, m.agent_id, m.content, m.id + "-" + i))}
            {live.map((l, i) => bubble(l.agent, l.agent_id ?? idOf(l.agent), l.text, "live" + i, !l.done && busy && i === live.length - 1, l.steps))}
          </div>
          {notice && <div className="mx-6 mb-2 rounded-xl bg-white/6 px-4 py-2 text-xs text-white/60">{notice}</div>}
          {err && <div className="mx-6 mb-2 rounded-xl bg-rose-500/12 px-4 py-2.5 text-sm text-rose-200">{err}</div>}
          <div className="px-6 pb-5"><div className="glass-soft mx-auto flex max-w-3xl items-end gap-2 rounded-[22px] p-2 pl-4">
            <textarea value={text} onChange={(e) => setText(e.target.value)} rows={1} placeholder="Gi gruppen en oppgave…" onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
              className="max-h-40 min-h-[40px] flex-1 resize-none bg-transparent py-2.5 text-[15px] outline-none placeholder:text-white/30" />
            {busy ? <button className="btn-primary grid h-10 w-10 place-items-center !p-0" title="Stopp" onClick={() => { if (runId.current) api.stopRun(runId.current).catch(() => abort.current?.abort()); else abort.current?.abort(); }}><Square size={14} fill="currentColor" /></button>
              : <button className="btn-primary grid h-10 w-10 place-items-center !p-0" disabled={!text.trim()} onClick={send}><ArrowUp size={18} strokeWidth={2.5} /></button>}</div></div>
        </>)}
      </section>
    </div>
  );
}
