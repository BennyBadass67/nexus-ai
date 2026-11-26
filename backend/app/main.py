import asyncio
import json
import logging
import re

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import config, db, library, ollama, system
from .schemas import BenchRequest, ChatRequest, PullRequest, RenameRequest

log = logging.getLogger("nexus")
app = FastAPI(title="NEXUS AI", version="0.1.0")
db.init()

SYSTEM_PROMPT = (
    "Du er NEXUS, en personlig KI-assistent som kjører lokalt på brukerens PC. "
    "Svar på samme språk som brukeren, kort og presist."
)
HISTORY_LIMIT = 30

PREF_DEFAULTS = {"agent_name": "NEXUS", "user_name": "Benjamin", "persona": "", "theme": "dark",
                 "accent": "#5aa9ff", "aurora": "on", "reply_lang": "auto"}
PREF_LIMITS = {"agent_name": 24, "user_name": 40, "persona": 4000, "accent": 7}
PREF_CHOICES = {"theme": {"dark", "midnight", "light"}, "aurora": {"on", "off"}}


def get_prefs() -> dict:
    out = dict(PREF_DEFAULTS)
    with db.conn() as c:
        for r in c.execute("SELECT key,value FROM settings WHERE key LIKE 'pref:%'").fetchall():
            k = r["key"][5:]
            if k in out:
                out[k] = r["value"]
    return out


def build_system_prompt(p: dict) -> str:
    base = (f"Du er {p['agent_name']}, en personlig KI-assistent som kjører lokalt på brukerens PC. "
            f"Brukeren heter {p['user_name']}. Svar på samme språk som brukeren, kort og presist.")
    if p.get("persona", "").strip():
        base += "\n\nPersonlighet og egne instruksjoner fra brukeren:\n" + p["persona"].strip()
    return base


@app.get("/api/health")
async def health():
    v = await ollama.version()
    with db.conn() as c:
        n = c.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
    return {"backend": "ok", "ollama_online": v is not None,
            "ollama_version": v, "conversations": n}


@app.get("/api/models")
async def models():
    try:
        items = await ollama.tags()
    except Exception as e:
        return {"online": False, "error": str(e), "models": []}
    return {"online": True, "models": [
        {"name": m["name"], "size": m.get("size", 0),
         "params": m.get("details", {}).get("parameter_size"),
         "quant": m.get("details", {}).get("quantization_level")} for m in items]}


@app.get("/api/conversations")
def list_conversations():
    with db.conn() as c:
        rows = c.execute("SELECT id,title,model,updated_at FROM conversations "
                         "ORDER BY updated_at DESC").fetchall()
    return [dict(r) for r in rows]


@app.get("/api/conversations/{cid}")
def get_conversation(cid: int):
    with db.conn() as c:
        conv = c.execute("SELECT id,title,model FROM conversations WHERE id=?", (cid,)).fetchone()
        if not conv:
            raise HTTPException(404, "Samtalen finnes ikke")
        msgs = c.execute("SELECT id,role,content,model,created_at FROM messages "
                         "WHERE conversation_id=? ORDER BY id", (cid,)).fetchall()
    return {**dict(conv), "messages": [dict(m) for m in msgs]}


@app.patch("/api/conversations/{cid}")
def rename_conversation(cid: int, body: RenameRequest):
    with db.conn() as c:
        cur = c.execute("UPDATE conversations SET title=? WHERE id=?", (body.title, cid))
        if cur.rowcount == 0:
            raise HTTPException(404, "Samtalen finnes ikke")
    return {"ok": True}


@app.delete("/api/conversations/{cid}")
def delete_conversation(cid: int):
    with db.conn() as c:
        c.execute("DELETE FROM conversations WHERE id=?", (cid,))
    return {"ok": True}


def _ev(**kw) -> bytes:
    return (json.dumps(kw, ensure_ascii=False) + "\n").encode()


@app.post("/api/chat")
async def chat(req: ChatRequest):
    """Strømmer svar som NDJSON: meta, token*, done | error."""
    with db.conn() as c:
        cid = req.conversation_id
        if cid is None:
            title = req.message.strip().replace("\n", " ")[:48]
            cid = c.execute("INSERT INTO conversations(title,model,created_at,updated_at) "
                            "VALUES(?,?,?,?)", (title, req.model, db.now(), db.now())).lastrowid
        elif not c.execute("SELECT 1 FROM conversations WHERE id=?", (cid,)).fetchone():
            raise HTTPException(404, "Samtalen finnes ikke")
        if req.regenerate:
            last = c.execute("SELECT id,role FROM messages WHERE conversation_id=? ORDER BY id DESC LIMIT 1",
                             (cid,)).fetchone()
            if last and last["role"] == "assistant":
                c.execute("DELETE FROM messages WHERE id=?", (last["id"],))
        else:
            c.execute("INSERT INTO messages(conversation_id,role,content,created_at) VALUES(?,?,?,?)",
                      (cid, "user", req.message, db.now()))
        hist = c.execute("SELECT role,content FROM messages WHERE conversation_id=? "
                         "ORDER BY id DESC LIMIT ?", (cid, HISTORY_LIMIT)).fetchall()
    messages = [{"role": "system", "content": build_system_prompt(get_prefs())}] + \
               [dict(r) for r in reversed(hist)]

    async def gen():
        yield _ev(type="meta", conversation_id=cid, model=req.model, provider="ollama")
        parts: list[str] = []
        try:
            async for kind, val in ollama.chat_stream(req.model, messages):
                if kind == "token":
                    parts.append(val)  # type: ignore
                    yield _ev(type="token", text=val)
                else:
                    yield _ev(type="stats", **val)  # type: ignore
        except (httpx.ConnectError, httpx.ConnectTimeout):
            yield _ev(type="error", message="Får ikke kontakt med Ollama. Er Ollama startet?")
        except Exception as e:
            log.exception("chat failed")
            yield _ev(type="error", message=str(e))
        finally:
            text = "".join(parts)
            if text:
                with db.conn() as c:
                    c.execute("INSERT INTO messages(conversation_id,role,content,model,created_at) "
                              "VALUES(?,?,?,?,?)", (cid, "assistant", text, req.model, db.now()))
                    c.execute("UPDATE conversations SET updated_at=?, model=? WHERE id=?",
                              (db.now(), req.model, cid))
        yield _ev(type="done")

    return StreamingResponse(gen(), media_type="application/x-ndjson")


@app.get("/api/system")
async def system_info(refresh: bool = False):
    hw = await asyncio.to_thread(system.hardware, refresh)
    return system.hw_dict(hw)


@app.get("/api/system/rate")
async def system_rate(size_gb: float):
    hw = await asyncio.to_thread(system.hardware)
    return system.rate(size_gb, hw)


@app.get("/api/recommendations")
async def recommendations():
    hw = await asyncio.to_thread(system.hardware)
    try:
        topics = await system.recommendations(hw)
    except Exception as e:
        return {"ok": False, "error": str(e), "hardware": system.hw_dict(hw), "topics": []}
    return {"ok": True, "hardware": system.hw_dict(hw), "topics": topics}


@app.post("/api/benchmark")
async def benchmark(req: BenchRequest):
    """Ekte hastighetstest: lar valgt modell skrive litt tekst og måler tokens per sekund."""
    try:
        r = await ollama.bench(req.model)
    except (httpx.ConnectError, httpx.ConnectTimeout):
        raise HTTPException(503, "Får ikke kontakt med Ollama")
    except Exception as e:
        raise HTTPException(500, str(e))
    with db.conn() as c:
        c.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)",
                  (f"bench:{req.model}", json.dumps({**r, "at": db.now()})))
    return r


@app.get("/api/settings")
def read_settings():
    return get_prefs()


@app.put("/api/settings")
def write_settings(body: dict):
    for k, v in body.items():
        if k not in PREF_DEFAULTS:
            raise HTTPException(422, f"Ukjent innstilling: {k}")
        v = str(v)
        if k in PREF_CHOICES and v not in PREF_CHOICES[k]:
            raise HTTPException(422, f"Ugyldig verdi for {k}")
        if k == "accent" and not re.fullmatch(r"#[0-9a-fA-F]{6}", v):
            raise HTTPException(422, "Aksentfarge må være #rrggbb")
        if len(v) > PREF_LIMITS.get(k, 50):
            raise HTTPException(422, f"{k} er for lang")
        if k == "agent_name" and not v.strip():
            raise HTTPException(422, "Navn kan ikke være tomt")
        with db.conn() as c:
            c.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (f"pref:{k}", v))
    return get_prefs()


@app.get("/api/benchmark")
def benchmarks():
    with db.conn() as c:
        rows = c.execute("SELECT key,value FROM settings WHERE key LIKE 'bench:%'").fetchall()
    return {r["key"][6:]: json.loads(r["value"]) for r in rows}


@app.get("/api/library")
async def library_search(q: str = ""):
    try:
        hw = await asyncio.to_thread(system.hardware)
        models = await library.search(q)
        for m in models:
            m["size_ratings"] = []
            for lab in m["sizes"]:
                gb = system.est_size_from_params(lab)
                m["size_ratings"].append({"label": lab, "est_gb": gb, **(system.rate(gb, hw) if gb else {"level": "unknown", "reason": ""})})
        return {"ok": True, "models": models}
    except Exception as e:
        return {"ok": False, "error": f"Kunne ikke hente modelliste fra ollama.com ({e})", "models": []}


@app.get("/api/library/{name}/tags")
async def library_tags(name: str):
    if not re.fullmatch(r"[A-Za-z0-9._-]+", name):
        raise HTTPException(422, "Ugyldig modellnavn")
    try:
        hw = await asyncio.to_thread(system.hardware)
        return {"ok": True, "tags": [{**t, **system.rate(t["size_gb"], hw)} for t in await library.tags(name)]}
    except Exception as e:
        return {"ok": False, "error": f"Kunne ikke hente versjoner ({e})", "tags": []}


@app.post("/api/models/pull")
async def pull_model(req: PullRequest):
    """Laster ned en modell. Strømmer NDJSON: progress*, done | error."""
    async def gen():
        try:
            async for p in ollama.pull_stream(req.name):
                yield _ev(type="progress", status=p.get("status", ""),
                          total=p.get("total"), completed=p.get("completed"))
            yield _ev(type="done")
        except (httpx.ConnectError, httpx.ConnectTimeout):
            yield _ev(type="error", message="Får ikke kontakt med Ollama. Er Ollama startet?")
        except Exception as e:
            yield _ev(type="error", message=str(e))
    return StreamingResponse(gen(), media_type="application/x-ndjson")


@app.delete("/api/models/{name:path}")
async def delete_model(name: str):
    try:
        await ollama.delete(name)
    except FileNotFoundError:
        raise HTTPException(404, "Modellen finnes ikke")
    except (httpx.ConnectError, httpx.ConnectTimeout):
        raise HTTPException(503, "Får ikke kontakt med Ollama")
    return {"ok": True}


# --- frontend (bygget React-app) ---
if config.FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=config.FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        f = (config.FRONTEND_DIST / path).resolve()
        if path and f.is_file() and config.FRONTEND_DIST in f.parents:
            return FileResponse(f)
        return FileResponse(config.FRONTEND_DIST / "index.html")
