export type Health = { backend: string; ollama_online: boolean; ollama_version: string | null; conversations: number };
export type ModelInfo = { name: string; size: number; params?: string; quant?: string };
export type ModelsResp = { online: boolean; error?: string; models: ModelInfo[] };
export type Conv = { id: number; title: string; model: string | null; updated_at: number };
export type Msg = { id?: number; role: "user" | "assistant"; content: string; model?: string | null; tps?: number };
export type ConvFull = { id: number; title: string; model: string | null; messages: Msg[] };

async function j<T>(url: string, init?: RequestInit): Promise<T> {
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

export const api = {
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
  | { type: "meta"; conversation_id: number; model: string; provider: string }
  | { type: "token"; text: string }
  | { type: "stats"; tokens: number; seconds: number }
  | { type: "error"; message: string }
  | { type: "done" };

/** Leser NDJSON-strømmen fra /api/chat og kaller onEvent for hver hendelse. */
export async function streamChat(
  body: { message: string; model: string; conversation_id?: number | null; regenerate?: boolean },
  onEvent: (e: ChatEvent) => void,
  signal: AbortSignal,
) {
  const r = await fetch("/api/chat", {
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

export const fmtSize = (b: number) => (b > 1e9 ? (b / 1e9).toFixed(1) + " GB" : (b / 1e6).toFixed(0) + " MB");

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
