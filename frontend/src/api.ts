export type Health = { backend: string; ollama_online: boolean; ollama_version: string | null; conversations: number };
export type ModelInfo = { name: string; size: number; params?: string; quant?: string };
export type ModelsResp = { online: boolean; error?: string; models: ModelInfo[] };
export type Conv = { id: number; title: string; model: string | null; updated_at: number };
export type Step = { call_id: string; tool: string; describe: string; risk: string; status: "running" | "waiting" | "ok" | "error" | "denied"; result?: string };
export type Msg = { id?: number; role: "user" | "assistant"; content: string; model?: string | null; tps?: number; steps?: Step[] };
export type ConvFull = { id: number; title: string; model: string | null; messages: Msg[] };

export async function j<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, init);
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json();
}

export type Level = "green" | "yellow" | "red" | "unknown";
export type SizeRating = { label: string; est_gb: number | null; level: Level; reason: string };
export type LibModel = { name: string; description: string; downloads: number; sizes: string[]; capabilities: string[]; size_ratings?: SizeRating[] };
export type LibTag = { tag: string; size_gb: number; level?: Level; reason?: string };
export type HW = { cpu: string; cores: number; ram_gb: number; gpu: string | null; vram_gb: number; gpu_vendor: string | null; os: string };
export type RecModel = { tag: string; size_gb: number; level: Level; reason: string };
export type Topic = { id: string; title: string; desc: string; model: RecModel | null };
export type Bench = { model: string; tokens: number; tps: number; load_s: number };
export type Pull = { status: string; total?: number | null; completed?: number | null; error?: string; done?: boolean };

export type Prefs = { agent_name: string; user_name: string; persona: string; theme: "dark" | "midnight" | "light"; accent: string; aurora: "on" | "off"; perf: "light" | "full"; reply_lang: string };

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
  library: (q: string) => j<{ ok: boolean; error?: string; models: LibModel[] }>(`/api/library?q=${encodeURIComponent(q)}`),
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
export const streamChat = (body: { message: string; model: string; conversation_id?: number | null; regenerate?: boolean },
  onEvent: (e: ChatEvent) => void, signal: AbortSignal) => ndjson("/api/chat", body, onEvent, signal);
export const streamAgent = (body: { message: string; model: string; conversation_id?: number | null; text_mode?: boolean },
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
export const updateApi = { check: () => j<UpdateInfo>("/api/update") };
