import { useEffect, useState } from "react";
import { Cpu, Hourglass, MemoryStick, StickyNote, Check, Plus, Timer, Trash2 } from "lucide-react";
import { useApp } from "../store";
import { GraduationCap } from "lucide-react";
import { Deck, Exam, extrasApi, FocusStats, Note, schoolApi, studyApi, SysMon, Today, todayApi } from "../api";
import { CalendarCheck, Cloud, MessageSquare } from "lucide-react";

const Bar = ({ pct, label, sub }: { pct: number | null; label: string; sub?: string }) => (
  <div>
    <div className="flex items-baseline justify-between text-xs"><span className="font-medium">{label}</span><span className="tabular-nums text-white/60">{pct == null ? "–" : pct + " %"}{sub ? ` · ${sub}` : ""}</span></div>
    <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-white/15"><div className={`h-full rounded-full transition-all duration-700 ${pct != null && pct > 85 ? "bg-rose-600" : "sysbar"}`} style={{ width: `${pct ?? 0}%` }} /></div>
  </div>);

export function SysMonCard() {
  const [s, setS] = useState<SysMon | null>(null);
  useEffect(() => { let on = true; const f = () => extrasApi.sysmon().then((x) => on && setS(x)).catch(() => {}); f(); const t = setInterval(f, 3000); return () => { on = false; clearInterval(t); }; }, []);
  return (
    <div className="glass animate-rise rounded-[26px] p-5">
      <div className="flex items-center gap-2 text-sm font-semibold"><Cpu size={15} />Systemmonitor <span className="ml-auto h-2 w-2 animate-pulse rounded-full bg-emerald-500" /></div>
      <div className="mt-4 space-y-3.5">
        <Bar pct={s?.cpu_pct ?? null} label="Prosessor" />
        <Bar pct={s?.ram_pct ?? null} label="Minne" sub={s?.ram_total_gb ? `${s.ram_used_gb} av ${s.ram_total_gb} GB` : undefined} />
      </div>
      <div className="mt-4 flex items-center gap-2 text-xs text-white/65"><MemoryStick size={13} />
        {s?.loaded == null ? "Ollama svarer ikke" : s.loaded.length === 0 ? "Ingen modell er lastet i minnet akkurat nå" : `I minnet: ${s.loaded.map((m) => `${m.name} (${m.size_gb} GB${m.vram_gb ? `, ${m.vram_gb} på GPU` : ""})`).join(", ")}`}</div>
    </div>);
}

export function NotesCard({ go }: { go: () => void }) {
  const [n, setN] = useState<Note[]>([]); const [t, setT] = useState("");
  const load = () => extrasApi.notes().then(setN).catch(() => {});
  useEffect(() => { load(); }, []);
  const open = n.filter((x) => !x.done);
  const add = () => { if (t.trim()) extrasApi.addNote(t.trim()).then(() => { setT(""); load(); }).catch(() => {}); };
  return (
    <div className="glass animate-rise rounded-[26px] p-5">
      <div className="flex items-center gap-2 text-sm font-semibold"><StickyNote size={15} />Notater<button className="ml-auto text-xs font-normal text-white/60 hover:underline" onClick={go}>Se alle ({open.length})</button></div>
      <div className="mt-3 space-y-1.5">
        {open.slice(0, 3).map((x) => (
          <div key={x.id} className="flex items-center gap-2.5 text-sm">
            <button title="Ferdig" onClick={() => extrasApi.patchNote(x.id, { done: true }).then(load)} className="grid h-5 w-5 flex-none place-items-center rounded-full border border-white/45 transition hover:border-emerald-600 hover:bg-emerald-600 hover:text-white"><Check size={11} strokeWidth={3} className="opacity-0 hover:opacity-100" /></button>
            <span className="truncate">{x.text}</span></div>))}
        {open.length === 0 && <div className="text-xs text-white/60">Ingen åpne notater.</div>}
      </div>
      <div className="mt-3 flex gap-2"><input value={t} onChange={(e) => setT(e.target.value)} onKeyDown={(e) => e.key === "Enter" && add()} maxLength={500} placeholder="Nytt notat…" className="min-w-0 flex-1 rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm outline-none focus:border-nx-blue/60" />
        <button className="btn-primary !px-3" onClick={add} disabled={!t.trim()} title="Legg til"><Plus size={15} /></button></div>
    </div>);
}

export function StudyCard({ go }: { go: () => void }) {
  const [d, setD] = useState<Deck[] | null>(null);
  useEffect(() => { studyApi.decks().then(setD).catch(() => setD([])); }, []);
  if (!d) return null;
  const due = d.reduce((a, x) => a + x.due, 0);
  return (
    <div className="glass animate-rise rounded-[26px] p-5">
      <div className="flex items-center gap-2 text-sm font-semibold"><GraduationCap size={15} />Studie<button className="ml-auto text-xs font-normal text-white/60 hover:underline" onClick={go}>Åpne</button></div>
      {d.length === 0 ? <div className="mt-3 text-xs text-white/60">Lim inn pensum og få øvingskort laget lokalt.</div> :
        <div className="mt-3 flex items-end gap-3"><div className="text-3xl font-semibold tabular-nums">{due}</div><div className="pb-1 text-xs text-white/65">kort å øve på i dag, fordelt på {d.length} {d.length === 1 ? "stokk" : "stokker"}</div></div>}
      <button className="btn mt-3" onClick={go}>{due ? "Øv nå" : "Lag kort"}</button>
    </div>);
}

export function TodayCard({ go }: { go: (p: string) => void }) {
  const [t, setT] = useState<Today | null>(null);
  const load = () => todayApi.get().then(setT).catch(() => {});
  useEffect(() => { load(); }, []);
  if (!t) return null;
  const hour = new Date().getHours();
  const hi = hour < 5 ? "God natt" : hour < 11 ? "God morgen" : hour < 17 ? "God dag" : "God kveld";
  const list = [...t.tasks_overdue.map((n) => ({ n, tag: "forfalt" })), ...t.tasks_today.map((n) => ({ n, tag: "i dag" })), ...(t.tasks_overdue.length + t.tasks_today.length === 0 ? t.tasks_next.map((n) => ({ n, tag: "" })) : [])];
  const tile = "glass-soft flex min-h-[112px] flex-col rounded-2xl p-4 text-left transition hover:-translate-y-0.5 hover:brightness-105 active:scale-[.98]";
  return (
    <div className="glass animate-rise rounded-[26px] p-5">
      <div className="flex items-center gap-2 text-sm font-semibold"><CalendarCheck size={15} />I dag<span className="ml-1 font-normal text-white/60">{hi}. {t.tasks_overdue.length ? `${t.tasks_overdue.length} forfalt.` : t.tasks_open ? `${t.tasks_open} åpne oppgaver.` : "Ingen åpne oppgaver."}</span></div>
      <div className="mt-3 grid gap-3 md:grid-cols-4">
        <div className={tile + " cursor-default"}>
          <div className="text-xs text-white/65">Oppgaver</div>
          <div className="mt-1.5 space-y-1">
            {list.length === 0 && <div className="text-xs text-white/60">Ingenting haster.</div>}
            {list.slice(0, 3).map(({ n, tag }) => (
              <button key={n.id} className="flex w-full items-center gap-1.5 text-left text-xs" onClick={async () => { await extrasApi.patchNote(n.id, { done: true }); load(); }} title="Merk som ferdig">
                <span className="grid h-3.5 w-3.5 flex-none place-items-center rounded border border-white/40" /><span className="truncate">{n.text}</span>{tag && <span className="ml-auto flex-none rounded-full bg-white/15 px-1.5 text-[10px]">{tag}</span>}</button>))}
          </div>
        </div>
        <button className={tile} onClick={() => go("study")}><div className="text-xs text-white/65">Øvingskort</div>
          <div className="mt-1 text-3xl font-semibold tabular-nums">{t.cards_due}</div><div className="mt-auto text-xs text-white/65">{t.cards_total === 0 ? "Lag din første stokk" : t.cards_due ? "klare til å øves på" : "ferdig for nå"}</div></button>
        <button className={tile} onClick={() => go("settings")}><div className="flex items-center gap-1 text-xs text-white/65"><Cloud size={12} />Sky-kvote</div>
          {t.quota.length === 0 ? <div className="mt-2 text-xs text-white/60">Sky-KI er av. Alt kjører lokalt.</div> : t.quota.map((q) => (
            <div key={q.id} className="mt-2"><div className="text-xs"><b className="tabular-nums">{q.remaining.toLocaleString("nb-NO")}</b> {q.unit} igjen <span className="text-white/60">(anslag)</span></div>
              <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-white/15"><div className="sysbar h-full transition-all duration-700" style={{ width: q.pct + "%" }} /></div></div>))}</button>
        <button className={tile} onClick={() => go("assistant")}><div className="flex items-center gap-1 text-xs text-white/65"><MessageSquare size={12} />Fortsett</div>
          {t.last_chat ? <><div className="mt-1.5 line-clamp-2 text-sm font-medium">{t.last_chat.title}</div>{t.last_chat.project && <div className="mt-auto text-xs text-white/65">Prosjekt: {t.last_chat.project}</div>}</> : <div className="mt-2 text-xs text-white/60">Start din første samtale.</div>}</button>
      </div>
    </div>);
}

const FOCUS_KEY = "nexus.focus";
type FocusState = { mode: "focus" | "break"; end: number | null; left: number; done: number; day: string };
const day = () => new Date().toISOString().slice(0, 10);
const LEN = { focus: 25 * 60, break: 5 * 60 };
const loadFocus = (): FocusState => {
  try { const s = JSON.parse(localStorage.getItem(FOCUS_KEY) || ""); if (s && s.day === day()) return s; if (s) return { mode: "focus", end: null, left: LEN.focus, done: 0, day: day() }; } catch { /* ignore */ }
  return { mode: "focus", end: null, left: LEN.focus, done: 0, day: day() };
};

const GOALS: [string, string][] = [["off", "Av"], ["120", "2 t"], ["300", "5 t"], ["600", "10 t"]];

export function FocusCard() {
  const { prefs, setPrefs } = useApp();
  const [s, setS] = useState<FocusState>(loadFocus);
  const [stats, setStats] = useState<FocusStats | null>(null);
  const [, tick] = useState(0);
  useEffect(() => { schoolApi.focusStats().then(setStats).catch(() => {}); }, []);
  useEffect(() => { localStorage.setItem(FOCUS_KEY, JSON.stringify(s)); }, [s]);
  useEffect(() => { if (s.end == null) return; const t = setInterval(() => tick((x) => x + 1), 500); return () => clearInterval(t); }, [s.end]);
  const left = s.end == null ? s.left : Math.max(0, Math.round((s.end - Date.now()) / 1000));
  useEffect(() => {
    if (s.end != null && left === 0) {
      const next = s.mode === "focus" ? "break" : "focus";
      if (s.mode === "focus") schoolApi.logFocus(Math.round(LEN.focus / 60)).then(setStats).catch(() => {});
      setS({ mode: next, end: null, left: LEN[next], done: s.done + (s.mode === "focus" ? 1 : 0), day: day() });
    }
  }, [left, s]);
  const mm = String(Math.floor(left / 60)).padStart(2, "0"), ss = String(left % 60).padStart(2, "0");
  const total = LEN[s.mode], pct = Math.round(((total - left) / total) * 100);
  const running = s.end != null;
  return (
    <div className="glass animate-rise rounded-[26px] p-5">
      <div className="flex items-center gap-2 text-sm font-semibold"><Timer size={15} />Fokus<span className="ml-auto text-xs font-normal text-white/60">{stats ? `${stats.today_min} min i dag · ${stats.week_min} min denne uken${stats.streak > 1 ? ` · rekke ${stats.streak} dager` : ""}` : `${s.done} økt${s.done === 1 ? "" : "er"} i dag`}</span></div>
      <div className="mt-3 flex items-end gap-3"><div className="text-4xl font-semibold tabular-nums">{mm}:{ss}</div><div className="pb-1 text-xs text-white/65">{s.mode === "focus" ? "lekser/arbeid (25 min)" : "pause (5 min)"}</div></div>
      <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-white/15"><div className="sysbar h-full transition-all duration-700" style={{ width: pct + "%" }} /></div>
      <div className="mt-3 flex gap-2">
        <button className="btn-primary" onClick={() => setS(running ? { ...s, end: null, left } : { ...s, end: Date.now() + left * 1000 })}>{running ? "Pause" : left < total ? "Fortsett" : "Start"}</button>
        <button className="btn" onClick={() => setS({ ...s, end: null, left: total })}>Nullstill</button>
        <button className="btn" onClick={() => { const n = s.mode === "focus" ? "break" : "focus"; setS({ ...s, mode: n, end: null, left: LEN[n] }); }}>{s.mode === "focus" ? "Hopp til pause" : "Hopp til fokus"}</button>
      </div>
      <div className="mt-3 border-t border-white/10 pt-3">
        <div className="flex items-center gap-2 text-xs text-white/65">Ukemål
          <span className="ml-auto flex gap-1">{GOALS.map(([v, l]) => (
            <button key={v} onClick={() => setPrefs({ focus_goal: v as typeof prefs.focus_goal })}
              className={`rounded-full px-2 py-0.5 transition ${prefs.focus_goal === v ? "bg-nx-blue/30 ring-1 ring-nx-blue/70" : "bg-white/10 hover:bg-white/20"}`}>{l}</button>))}</span>
        </div>
        {prefs.focus_goal !== "off" && stats && (
          <div className="mt-2">
            <div className="flex items-baseline justify-between text-xs"><span className="tabular-nums text-white/70">{stats.week_min} av {prefs.focus_goal} min siste 7 dager</span><span className="tabular-nums text-white/60">{Math.min(100, Math.round((stats.week_min / +prefs.focus_goal) * 100))} %</span></div>
            <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-white/15"><div className="sysbar h-full transition-all duration-700" style={{ width: `${Math.min(100, (stats.week_min / +prefs.focus_goal) * 100)}%` }} /></div>
          </div>)}
      </div>
    </div>);
}

export function ExamsCard() {
  const [exams, setExams] = useState<Exam[] | null>(null);
  const [subj, setSubj] = useState(""); const [date, setDate] = useState(""); const [err, setErr] = useState("");
  const load = () => schoolApi.exams().then((r) => setExams(r.exams)).catch(() => setExams([]));
  useEffect(() => { load(); }, []);
  const add = () => {
    if (!subj.trim() || !date) return;
    schoolApi.addExam(subj.trim(), date).then(() => { setSubj(""); setDate(""); setErr(""); load(); })
      .catch((e) => { try { setErr(JSON.parse(String(e.message).replace(/^\d+ /, ""))?.detail || "Kunne ikke lagre."); } catch { setErr("Kunne ikke lagre."); } });
  };
  const fmt = (iso: string) => { const [y, m, d] = iso.split("-"); return `${Number(d)}. ${["jan", "feb", "mar", "apr", "mai", "jun", "jul", "aug", "sep", "okt", "nov", "des"][Number(m) - 1]} ${y}`; };
  const when = (n: number) => n === 0 ? "i dag!" : n === 1 ? "i morgen" : n < 0 ? `for ${-n} d siden` : `om ${n} dager`;
  if (!exams) return null;
  const upcoming = exams.filter((e) => e.days_left >= 0);
  const next = upcoming[0];
  return (
    <div className="glass animate-rise rounded-[26px] p-5">
      <div className="flex items-center gap-2 text-sm font-semibold"><Hourglass size={15} />Prøvenedtelling<span className="ml-auto text-xs font-normal text-white/60">{upcoming.length ? `${upcoming.length} kommende` : "ingen planlagt"}</span></div>
      {next && (
        <div className="mt-3 flex items-end gap-3">
          <div className="text-4xl font-semibold tabular-nums">{next.days_left === 0 ? "I dag" : next.days_left}</div>
          <div className="pb-1 text-xs text-white/65">{next.days_left === 0 ? `${next.subject} er i dag. Lykke til!` : next.days_left === 1 ? `dag til ${next.subject}` : `dager til ${next.subject} (${fmt(next.date)})`}</div>
        </div>)}
      <div className="mt-3 space-y-1.5">
        {exams.slice(next ? 1 : 0, 4).map((e) => (
          <div key={e.id} className={`flex items-center gap-2.5 text-sm ${e.days_left < 0 ? "text-white/40" : ""}`}>
            <span className="truncate">{e.subject}</span>
            <span className="ml-auto flex-none text-xs text-white/55">{fmt(e.date)} · {when(e.days_left)}</span>
            <button title="Fjern" className="flex-none text-white/40 transition hover:text-rose-600" onClick={() => schoolApi.delExam(e.id).then(load)}><Trash2 size={13} /></button>
          </div>))}
        {exams.length === 0 && <div className="text-xs text-white/60">Legg inn neste prøve, så teller NEXUS ned for deg.</div>}
      </div>
      <div className="mt-3 flex gap-2">
        <input value={subj} onChange={(e) => setSubj(e.target.value)} maxLength={60} placeholder="Fag, f.eks. Matte" className="min-w-0 flex-1 rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm outline-none focus:border-nx-blue/60" />
        <input type="date" value={date} onChange={(e) => setDate(e.target.value)} className="rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm outline-none [color-scheme:dark] focus:border-nx-blue/60" />
        <button className="btn-primary !px-3" onClick={add} disabled={!subj.trim() || !date} title="Legg til"><Plus size={15} /></button>
      </div>
      {err && <div className="mt-2 text-xs text-rose-700">{err}</div>}
    </div>);
}
