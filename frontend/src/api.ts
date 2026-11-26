export type Health = { backend: string; ollama_online: boolean; ollama_version: string | null; conversations: number };
export type ModelInfo = { name: string; size: number; params?: string; quant?: string; cloud?: boolean; provider?: string };
export type ModelsResp = { online: boolean; error?: string; models: ModelInfo[] };
export type Conv = { id: number; title: string; model: string | null; updated_at: number; project_id?: number | null };
export type Project = { id: number; name: string; instructions: string; chats: number };
export type Step = { call_id: string; tool: string; describe: string; risk: string; status: "running" | "waiting" | "ok" | "error" | "denied"; result?: string };
export type Msg = { id?: number; role: "user" | "assistant"; content: string; model?: string | null; tps?: number; steps?: Step[]; imgs?: string[] };
export type ConvFull = { id: number; title: string; model: string | null; messages: Msg[] };

export async function j<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, init);
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json();
}

export type Level = "green" | "yellow" | "red" | "unknown";
export type SizeRating = { label: string; est_gb: number | null; level: Level; reason: string };
export type LibModel = { name: string; description: string; downloads: number; pulls?: number; categories?: string[]; fits?: boolean; sizes: string[]; capabilities: string[]; size_ratings?: SizeRating[] };
export type LibTag = { tag: string; size_gb: number; level?: Level; reason?: string };
export type HW = { cpu: string; cores: number; ram_gb: number; gpu: string | null; vram_gb: number; gpu_vendor: string | null; os: string };
export type RecModel = { tag: string; size_gb: number; level: Level; reason: string };
export type Topic = { id: string; title: string; desc: string; model: RecModel | null };
export type Bench = { model: string; tokens: number; tps: number; load_s: number };
export type Pull = { status: string; total?: number | null; completed?: number | null; error?: string; done?: boolean };

export type Prefs = { agent_name: string; user_name: string; persona: string; theme: "dark" | "midnight" | "light" | "glass" | "frost"; intro: "on" | "off"; accent: string; aurora: "on" | "off"; perf: "light" | "full"; reply_lang: string; screen_control: "on" | "off"; autoupdate: "on" | "off" };

export type AgentDef = { id: number; name: string; role: string; prompt: string; model: string | null; tools: string[] };
export type Room = { id: number; title: string; agent_ids: number[]; max_rounds: number; mode: "roundrobin" | "leader" };
export type RoomMsg = { id: number; author: string; agent_id: number | null; content: string; created_at: number };
export type RoomEvent =
  | { type: "meta"; run_id: string; room_id: number } | { type: "user_message"; text: string }
  | { type: "turn_start"; agent: string; agent_id: number; model: string } | { type: "token"; agent: string; text: string }
  | { type: "turn_end"; agent: string; text: string } | { type: "notice"; text: string } | { type: "stopped" }
  | { type: "error"; message: string } | { type: "done" }
  | { type: "tool_call"; agent: string; call_id: string; tool: string; describe: string; risk: string; needs_approval: boolean }
  | { type: "tool_result"; call_id: string; status: "ok" | "error" | "denied"; result: string } | { type: "approval"; call_id: string };

export async function streamRoom(id: number, body: { message: string; default_model: string }, onEvent: (e: RoomEvent) => void, signal: AbortSignal) {
  const r = await fetch(`/api/rooms/${id}/run`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal });
  if (!r.ok || !r.body) throw new Error(`${r.status} ${await r.text()}`);
  const reader = r.body.getReader(); const dec = new TextDecoder(); let buf = "";
  for (;;) {
    const { value, done } = await reader.read(); if (done) break;
    buf += dec.decode(value, { stream: true }); let i: number;
    while ((i = buf.indexOf("\n")) >= 0) { const line = buf.slice(0, i).trim(); buf = buf.slice(i + 1); if (line) onEvent(JSON.parse(line)); }
  }
}
const J = { "Content-Type": "application/json" };
export const teamApi = {
  agents: () => j<AgentDef[]>("/api/agents"),
  saveAgent: (a: Partial<AgentDef>) => j<AgentDef>(a.id ? `/api/agents/${a.id}` : "/api/agents", { method: a.id ? "PUT" : "POST", headers: J, body: JSON.stringify(a) }),
  delAgent: (id: number) => j<{ ok: boolean }>(`/api/agents/${id}`, { method: "DELETE" }),
  rooms: () => j<Room[]>("/api/rooms"),
  room: (id: number) => j<Room & { messages: RoomMsg[] }>(`/api/rooms/${id}`),
  saveRoom: (r: Partial<Room>) => j<Room>(r.id ? `/api/rooms/${r.id}` : "/api/rooms", { method: r.id ? "PUT" : "POST", headers: J, body: JSON.stringify(r) }),
  delRoom: (id: number) => j<{ ok: boolean }>(`/api/rooms/${id}`, { method: "DELETE" }),
  clearRoom: (id: number) => j<{ ok: boolean }>(`/api/rooms/${id}/clear`, { method: "POST" }),
  example: () => j<Room & { messages: RoomMsg[] }>("/api/rooms/example", { method: "POST" }),
};

export type ToolInfo = { name: string; description: string; risk: string; needs_approval: boolean };
export type Activity = { id: number; run_id: string | null; ts: number; kind: string; tool: string | null; detail: string; status: string; result: string };

export const api = {
  approve: (run: string, call_id: string, allow: boolean) => j<{ ok: boolean }>(`/api/agent/${run}/approve`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ call_id, allow }) }),
  stopRun: (run: string) => j<{ ok: boolean }>(`/api/agent/${run}/stop`, { method: "POST" }),
  agentConfig: () => j<{ roots: string[]; tools: ToolInfo[] }>("/api/agent/config"),
  saveRoots: (roots: string[]) => j<{ roots: string[] }>("/api/agent/config", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ roots }) }),
  activity: (limit = 100) => j<Activity[]>(`/api/activity?limit=${limit}`),
  prefs: () => j<Prefs>("/api/settings"),
  savePrefs: (p: Partial<Prefs>) => j<Prefs>("/api/settings", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(p) }),
  benchAuto: () => j<{ measured: Bench[]; errors: Record<string, string>; remaining: number }>("/api/benchmark/auto", { method: "POST" }),
  recommendations: () => j<{ ok: boolean; error?: string; hardware: HW; topics: Topic[]; calibrated?: boolean; measured_models?: string[] }>("/api/recommendations"),
  system: (refresh = false) => j<HW>(`/api/system?refresh=${refresh}`),
  benchmarks: () => j<Record<string, Bench & { at: number }>>("/api/benchmark"),
  benchmark: (model: string) => j<Bench>("/api/benchmark", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ model }) }),
  library: (q: string) => j<{ ok: boolean; error?: string; models: LibModel[]; categories?: { id: string; label: string; count: number }[]; fits_count?: number }>(`/api/library?q=${encodeURIComponent(q)}`),
  tags: (n: string) => j<{ ok: boolean; error?: string; tags: LibTag[] }>(`/api/library/${encodeURIComponent(n)}/tags`),
  deleteModel: (n: string) => j(`/api/models/${encodeURIComponent(n)}`, { method: "DELETE" }),
  health: () => j<Health>("/api/health"),
  models: () => j<ModelsResp>("/api/models"),
  conversations: () => j<Conv[]>("/api/conversations"),
  conversation: (id: number) => j<ConvFull>(`/api/conversations/${id}`),
  remove: (id: number) => j(`/api/conversations/${id}`, { method: "DELETE" }),
};

export type ChatEvent =
  | { type: "meta"; conversation_id: number; model: string; provider: string; run_id?: string }
  | { type: "token"; text: string }
  | { type: "stats"; tokens: number; seconds: number }
  | { type: "error"; message: string }
  | { type: "run"; run_id: string }
  | { type: "tool_call"; call_id: string; tool: string; describe: string; risk: string; needs_approval: boolean }
  | { type: "approval"; call_id: string }
  | { type: "tool_result"; call_id: string; status: "ok" | "error" | "denied"; result: string }
  | { type: "notice"; text: string }
  | { type: "final"; text: string }
  | { type: "stopped" }
  | { type: "done" };

/** Leser NDJSON-strømmen fra /api/chat og kaller onEvent for hver hendelse. */
export const streamChat = (body: { message: string; model: string; conversation_id?: number | null; regenerate?: boolean; project_id?: number | null; images?: string[] },
  onEvent: (e: ChatEvent) => void, signal: AbortSignal) => ndjson("/api/chat", body, onEvent, signal);
export const streamAgent = (body: { message: string; model: string; conversation_id?: number | null; text_mode?: boolean; project_id?: number | null },
  onEvent: (e: ChatEvent) => void, signal: AbortSignal) => ndjson("/api/agent/run", body, onEvent, signal);

async function ndjson(url: string, body: object, onEvent: (e: ChatEvent) => void, signal: AbortSignal) {
  const r = await fetch(url, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body), signal,
  });
  if (!r.ok || !r.body) throw new Error(`${r.status} ${await r.text()}`);
  const reader = r.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let i: number;
    while ((i = buf.indexOf("\n")) >= 0) {
      const line = buf.slice(0, i).trim();
      buf = buf.slice(i + 1);
      if (line) onEvent(JSON.parse(line));
    }
  }
}

export const fmtSize = (b: number) => (b > 1e9 ? (b / 1e9).toFixed(1) + " GB" : b >= 1e6 ? (b / 1e6).toFixed(0) + " MB" : b >= 1e3 ? (b / 1e3).toFixed(0) + " KB" : b + " B");

/** Strømmer nedlastingsfremdrift for en Ollama-modell. */
export async function streamPull(name: string, onP: (p: Pull) => void, signal: AbortSignal) {
  const r = await fetch("/api/models/pull", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }), signal });
  if (!r.ok || !r.body) throw new Error(`${r.status} ${await r.text()}`);
  const reader = r.body.getReader(); const dec = new TextDecoder(); let buf = "";
  for (;;) {
    const { value, done } = await reader.read(); if (done) break;
    buf += dec.decode(value, { stream: true });
    let i: number;
    while ((i = buf.indexOf("\n")) >= 0) {
      const line = buf.slice(0, i).trim(); buf = buf.slice(i + 1);
      if (!line) continue;
      const e = JSON.parse(line);
      if (e.type === "progress") onP({ status: e.status, total: e.total, completed: e.completed });
      else if (e.type === "error") onP({ status: "", error: e.message });
      else if (e.type === "done") onP({ status: "ferdig", done: true });
    }
  }
}

export type Mem = { id: number; content: string; kind: "fact" | "preference" | "decision" | "project"; source: "user" | "agent"; pinned: boolean; created_at: number; updated_at: number };
export type MemList = { enabled: boolean; items: Mem[]; limit: number; context_chars: number };
export const memApi = {
  list: (q = "") => j<MemList>("/api/memory" + (q ? "?q=" + encodeURIComponent(q) : "")),
  add: (content: string, kind: Mem["kind"], pinned = false) => j<{ id: number; duplicate?: boolean }>("/api/memory", { method: "POST", headers: J, body: JSON.stringify({ content, kind, pinned }) }),
  patch: (id: number, p: Partial<Pick<Mem, "content" | "kind" | "pinned">>) => j<{ ok: boolean }>(`/api/memory/${id}`, { method: "PATCH", headers: J, body: JSON.stringify(p) }),
  del: (id: number) => j<{ ok: boolean }>(`/api/memory/${id}`, { method: "DELETE" }),
  clear: () => j<{ ok: boolean }>("/api/memory?confirm=true", { method: "DELETE" }),
  enable: (enabled: boolean) => j<{ enabled: boolean }>("/api/memory/enabled", { method: "PUT", headers: J, body: JSON.stringify({ enabled }) }),
};

export type WsItem = { name: string; path: string; dir: boolean; size: number; mtime: number };
export type WsList = { path: string; parent: string | null; items: WsItem[]; truncated: boolean };
export type WsFile = { path: string; size: number; text: string | null; binary: boolean; truncated?: boolean };
export const wsApi = {
  roots: () => j<{ roots: { path: string; exists: boolean }[] }>("/api/workspace/roots"),
  list: (path: string) => j<WsList>("/api/workspace/list?path=" + encodeURIComponent(path)),
  read: (path: string) => j<WsFile>("/api/workspace/read?path=" + encodeURIComponent(path)),
  open: (path: string) => j<{ ok: boolean }>("/api/workspace/open", { method: "POST", headers: J, body: JSON.stringify({ path }) }),
};

export type UpdateInfo = { current: string; latest: string | null; available: boolean; url: string | null; notes: string; error: string | null };
export type UpdateStatus = { state: "idle" | "downloading" | "ready" | "launching" | "started" | "error"; done: number; total: number; error: string | null; path: string | null; version: string | null };
export const updateApi = {
  check: () => j<UpdateInfo>("/api/update"),
  status: () => j<UpdateStatus>("/api/update/status"),
  install: () => j<{ ok: boolean; version: string }>("/api/update/install", { method: "POST" }),
};

export type TeamAgent = { model?: string | null; name: string; role: string; prompt: string; tools: string[] };
export type TeamProposal = { title: string; agents: TeamAgent[]; mode: "roundrobin" | "leader"; max_rounds: number; model: string };
export const builderApi = {
  designer: () => j<DesignerInfo>("/api/teams/designer"),
  design: (description: string, model: string) => j<{ proposal: TeamProposal; model_used: string; missing_models: string[]; warning: string | null }>("/api/teams/design", { method: "POST", headers: J, body: JSON.stringify({ description, model }) }),
  create: (p: TeamProposal) => j<Room>("/api/teams/create", { method: "POST", headers: J, body: JSON.stringify(p) }),
};

export type DesignerInfo = { model: string; size_gb: number; level: "green" | "yellow" | "red"; reason: string; installed: boolean; online: boolean };

export type Note = { id: number; text: string; done: boolean; due: string | null; source: string; created_at: number };
export type Tpl = { id: number; title: string; body: string };
export type SearchRes = { query: string; conversations: { id: number; title: string; snippet: string }[]; memories: { id: number; content: string; kind: string }[]; agents: { id: number; name: string; role: string }[]; notes: { id: number; text: string; done: boolean }[]; rooms: { id: number; title: string; snippet: string; author: string }[]; activity: { id: number; tool: string; detail: string; status: string }[] };
export type SysMon = { cpu_pct: number | null; ram_used_gb: number | null; ram_total_gb: number | null; ram_pct: number | null; loaded: { name: string; size_gb: number; vram_gb: number }[] | null };
export type KHit = { path: string; pos: number; score: number; text: string };
export const extrasApi = {
  search: (q: string) => j<SearchRes>("/api/search?q=" + encodeURIComponent(q)),
  notes: () => j<Note[]>("/api/notes"),
  addNote: (text: string, due?: string) => j<{ id: number }>("/api/notes", { method: "POST", headers: J, body: JSON.stringify({ text, due: due || null }) }),
  patchNote: (id: number, body: Partial<{ done: boolean; text: string }>) => j<{ ok: boolean }>("/api/notes/" + id, { method: "PATCH", headers: J, body: JSON.stringify(body) }),
  delNote: (id: number) => j<{ ok: boolean }>("/api/notes/" + id, { method: "DELETE" }),
  templates: () => j<Tpl[]>("/api/templates"),
  addTemplate: (title: string, body: string) => j<{ id: number }>("/api/templates", { method: "POST", headers: J, body: JSON.stringify({ title, body }) }),
  delTemplate: (id: number) => j<{ ok: boolean }>("/api/templates/" + id, { method: "DELETE" }),
  sysmon: () => j<SysMon>("/api/sysmon"),
  kStatus: () => j<{ files: number; chunks: number }>("/api/knowledge/status"),
  kIndex: () => j<{ added: number; updated: number; removed: number; skipped: number; files: number; chunks: number }>("/api/knowledge/index", { method: "POST" }),
  kSearch: (q: string) => j<KHit[]>("/api/knowledge/search?q=" + encodeURIComponent(q)),
  kClear: () => j<{ ok: boolean }>("/api/knowledge", { method: "DELETE" }),
  restore: async (file: File) => { const r = await fetch("/api/backup/restore", { method: "POST", headers: { "content-type": "application/octet-stream" }, body: file }); if (!r.ok) throw new Error(String((await r.json().catch(() => ({ detail: r.statusText }))).detail)); return r.json() as Promise<{ ok: boolean; restored: Record<string, number>; safety_copy: string }>; },
};

export type Deck = { id: number; title: string; total: number; due: number; learned: number };
export type Card = { id: number; deck_id: number; front: string; back: string; interval: number; reps: number };
export const studyApi = {
  decks: () => j<Deck[]>("/api/study/decks"),
  cards: (id: number, due = false) => j<Card[]>(`/api/study/decks/${id}/cards${due ? "?due=true" : ""}`),
  generate: (b: { model: string; text?: string; title?: string; n?: number; deck_id?: number; note_id?: number }) => j<{ deck_id: number; added: number }>("/api/study/generate", { method: "POST", headers: J, body: JSON.stringify(b) }),
  review: (id: number, grade: number) => j<{ interval_days: number }>(`/api/study/cards/${id}/review`, { method: "POST", headers: J, body: JSON.stringify({ grade }) }),
  quiz: (id: number, n = 10) => j<{ card_id: number; question: string; options: string[]; answer: number }[]>(`/api/study/decks/${id}/quiz?n=${n}`),
  delDeck: (id: number) => j<{ ok: boolean }>("/api/study/decks/" + id, { method: "DELETE" }),
  ask: async (model: string, q: string, onTok: (t: string) => void) => {
    const r = await fetch("/api/knowledge/ask", { method: "POST", headers: J, body: JSON.stringify({ model, q }) });
    if (!r.ok || !r.body) throw new Error(await r.text());
    const srcs: string[] = JSON.parse(r.headers.get("X-Sources") || "[]");
    const rd = r.body.getReader(); const dec = new TextDecoder();
    for (;;) { const { done, value } = await rd.read(); if (done) break; onTok(dec.decode(value, { stream: true })); }
    return srcs;
  },
  complete: async (model: string, prompt: string, onTok: (t: string) => void, signal?: AbortSignal) => {
    const r = await fetch("/api/complete", { method: "POST", headers: J, body: JSON.stringify({ model, prompt }), signal });
    if (!r.ok || !r.body) throw new Error(await r.text());
    const rd = r.body.getReader(); const dec = new TextDecoder();
    for (;;) { const { done, value } = await rd.read(); if (done) break; onTok(dec.decode(value, { stream: true })); }
  },
  transform: async (model: string, action: string, text: string, onTok: (t: string) => void, signal?: AbortSignal) => {
    const r = await fetch("/api/write/transform", { method: "POST", headers: J, body: JSON.stringify({ model, action, text }), signal });
    if (!r.ok || !r.body) throw new Error(await r.text());
    const rd = r.body.getReader(); const dec = new TextDecoder();
    for (;;) { const { done, value } = await rd.read(); if (done) break; onTok(dec.decode(value, { stream: true })); }
  },
};

export const smartApi = {
  autotitle: (cid: number, model: string) => j<{ title: string; changed: boolean }>(`/api/conversations/${cid}/autotitle`, { method: "POST", headers: J, body: JSON.stringify({ model }) }),
  suggest: (cid: number, model: string) => j<{ suggestions: string[] }>(`/api/conversations/${cid}/suggest`, { method: "POST", headers: J, body: JSON.stringify({ model }) }),
};

export type CloudProv = { id: string; label: string; free: string; key_help: string; key_url: string; needs_account: boolean; custom: boolean; has_key: boolean; key_hint: string; account_id: string; base_url: string; custom_model: string; enabled: boolean; models: string[]; requests_today: number; usage: CloudUsage };
export type CloudUsage = { requests: number; tokens_in: number; tokens_out: number; estimate: boolean; resets: string; note: string; limit?: number; unit?: string; used?: number; remaining?: number; pct?: number };
export const cloudApi = {
  list: () => j<CloudProv[]>("/api/cloud/providers"),
  save: (id: string, b: Record<string, unknown>) => j<CloudProv>("/api/cloud/providers/" + id, { method: "PUT", headers: J, body: JSON.stringify(b) }),
  forget: (id: string) => j<CloudProv>("/api/cloud/providers/" + id, { method: "DELETE" }),
  test: (id: string) => j<{ ok: boolean; error?: string; model?: string; reply?: string; models?: string[] }>("/api/cloud/providers/" + id + "/test", { method: "POST" }),
};

export const projectsApi = {
  list: () => j<Project[]>("/api/projects"),
  create: (b: { name: string; instructions: string }) => j<{ id: number }>("/api/projects", { method: "POST", headers: J, body: JSON.stringify(b) }),
  patch: (id: number, b: { name?: string; instructions?: string }) => j("/api/projects/" + id, { method: "PATCH", headers: J, body: JSON.stringify(b) }),
  remove: (id: number) => j("/api/projects/" + id, { method: "DELETE" }),
  assign: (cid: number, project_id: number | null) => j(`/api/conversations/${cid}/project`, { method: "PUT", headers: J, body: JSON.stringify({ project_id }) }),
};

export type Today = { date: string; tasks_open: number; tasks_overdue: Note[]; tasks_today: Note[]; tasks_next: Note[]; cards_due: number; cards_total: number;
  quota: { id: string; label: string; remaining: number; limit: number; unit: string; pct: number }[]; last_chat: { id: number; title: string; updated_at: number; project: string | null } | null };
export const todayApi = { get: () => { const d = new Date(); const ds = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; return j<Today>("/api/today?date=" + ds); } };

export type StudyStats = { today: number; streak: number; last7: { day: string; n: number }[]; total: number; good_pct_7d: number | null };
const localDay = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };
export const schoolApi = {
  stats: () => j<StudyStats>("/api/study/stats?date=" + localDay()),
  plan: (b: { topics: string[]; exam_date: string; subject?: string; commit?: boolean }) =>
    j<{ items: { due: string; text: string }[]; added: number }>("/api/study/plan", { method: "POST", headers: J, body: JSON.stringify({ ...b, start_date: localDay() }) }),
};
