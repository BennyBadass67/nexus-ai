import asyncio
import os
import json
import logging
import re

from typing import Optional

import httpx
from pydantic import BaseModel, Field
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import school, vision, projects, agent, config, db, extras, study, cloud, library, memory, ollama, rooms, system, teambuilder, tools, update, workspace
from .schemas import BenchRequest, ChatRequest, PullRequest, RenameRequest

log = logging.getLogger("nexus")
app = FastAPI(title="NEXUS AI", version="0.1.0")
db.init()
app.include_router(rooms.router)
app.include_router(projects.router)
app.include_router(school.router)
app.include_router(teambuilder.router)
app.include_router(update.router)
app.include_router(memory.router)
app.include_router(workspace.router)
app.include_router(extras.router)
app.include_router(study.router)
app.include_router(cloud.router)

SYSTEM_PROMPT = (
    "Du er NEXUS, en personlig KI-assistent som kjører lokalt på brukerens PC. "
    "Svar på samme språk som brukeren, kort og presist."
)
HISTORY_LIMIT = 30

PREF_DEFAULTS = {"agent_name": "NEXUS", "user_name": "Benjamin", "persona": "", "theme": "dark",
                 "accent": "#5aa9ff", "aurora": "on", "perf": "light", "reply_lang": "auto", "intro": "on", "screen_control": "off"}
PREF_LIMITS = {"agent_name": 24, "user_name": 40, "persona": 4000, "accent": 7}
PREF_CHOICES = {"theme": {"dark", "midnight", "light", "glass", "frost"}, "intro": {"on", "off"}, "aurora": {"on", "off"}, "perf": {"light", "full"}, "screen_control": {"on", "off"}}


def get_prefs() -> dict:
    out = dict(PREF_DEFAULTS)
    with db.conn() as c:
        for r in c.execute("SELECT key,value FROM settings WHERE key LIKE 'pref:%'").fetchall():
            k = r["key"][5:]
            if k in out:
                out[k] = r["value"]
    return out


def build_system_prompt(p: dict, cid: int | None = None) -> str:
    base = (f"Du er {p['agent_name']}, en personlig KI-assistent som kjører lokalt på brukerens PC. "
            f"Brukeren heter {p['user_name']}. Svar på samme språk som brukeren, kort og presist.")
    if p.get("persona", "").strip():
        base += "\n\nPersonlighet og egne instruksjoner fra brukeren:\n" + p["persona"].strip()
    mem = memory.context()
    if mem:
        base += "\n\n" + mem
    return base + projects.instructions_for(cid)


@app.get("/api/health")
async def health():
    v = await ollama.version()
    with db.conn() as c:
        n = c.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
    return {"backend": "ok", "ollama_online": v is not None,
            "ollama_version": v, "conversations": n}


@app.get("/api/models")
async def models():
    sky = cloud.enabled_models()
    try:
        items = await ollama.tags()
    except Exception as e:
        return {"online": False, "error": str(e), "models": sky}
    return {"online": True, "models": [
        {"name": m["name"], "size": m.get("size", 0),
         "params": m.get("details", {}).get("parameter_size"),
         "quant": m.get("details", {}).get("quantization_level")} for m in items] + sky}


@app.get("/api/conversations")
def list_conversations():
    with db.conn() as c:
        rows = c.execute("SELECT id,title,model,updated_at,project_id FROM conversations "
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
    imgs = vision.check(req.model, req.images)
    with db.conn() as c:
        cid = req.conversation_id
        if cid is None:
            title = req.message.strip().replace("\n", " ")[:48]
            cid = c.execute("INSERT INTO conversations(title,model,created_at,updated_at,project_id) "
                            "VALUES(?,?,?,?,?)", (title, req.model, db.now(), db.now(), req.project_id)).lastrowid
        elif not c.execute("SELECT 1 FROM conversations WHERE id=?", (cid,)).fetchone():
            raise HTTPException(404, "Samtalen finnes ikke")
        if req.regenerate:
            last = c.execute("SELECT id,role FROM messages WHERE conversation_id=? ORDER BY id DESC LIMIT 1",
                             (cid,)).fetchone()
            if last and last["role"] == "assistant":
                c.execute("DELETE FROM messages WHERE id=?", (last["id"],))
        else:
            c.execute("INSERT INTO messages(conversation_id,role,content,created_at) VALUES(?,?,?,?)",
                      (cid, "user", (f"🖼 [{len(imgs)} bilde(r) vedlagt]\n" if imgs else "") + req.message, db.now()))
        hist = c.execute("SELECT role,content FROM messages WHERE conversation_id=? "
                         "ORDER BY id DESC LIMIT ?", (cid, HISTORY_LIMIT)).fetchall()
    messages = [{"role": "system", "content": build_system_prompt(get_prefs(), cid)}] + \
               [dict(r) for r in reversed(hist)]
    if imgs and not req.regenerate:
        messages[-1] = {**messages[-1], "content": req.message, "images": imgs}

    async def gen():
        yield _ev(type="meta", conversation_id=cid, model=req.model, provider=("cloud" if cloud.is_cloud(req.model) else "ollama"))
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


class AgentRunReq(BaseModel):
    message: str = Field(min_length=1, max_length=20000)
    model: str = Field(min_length=1)
    conversation_id: Optional[int] = None
    text_mode: bool = False
    project_id: Optional[int] = None


class ApproveReq(BaseModel):
    call_id: str
    allow: bool


@app.post("/api/agent/run")
async def agent_run(req: AgentRunReq):
    """Agent-modus: strømmer meta, token, tool_call, approval, tool_result, final | error | stopped, done."""
    with db.conn() as c:
        cid = req.conversation_id
        if cid is None:
            cid = c.execute("INSERT INTO conversations(title,model,created_at,updated_at,project_id) VALUES(?,?,?,?,?)",
                            (req.message.strip().replace("\n", " ")[:48], req.model, db.now(), db.now(), req.project_id)).lastrowid
        elif not c.execute("SELECT 1 FROM conversations WHERE id=?", (cid,)).fetchone():
            raise HTTPException(404, "Samtalen finnes ikke")
        c.execute("INSERT INTO messages(conversation_id,role,content,created_at) VALUES(?,?,?,?)",
                  (cid, "user", req.message, db.now()))
        hist = c.execute("SELECT role,content FROM messages WHERE conversation_id=? ORDER BY id DESC LIMIT ?",
                         (cid, HISTORY_LIMIT)).fetchall()
    run = agent.Run()
    agent.RUNS[run.id] = run
    msgs = [dict(r) for r in reversed(hist)]

    async def gen():
        yield _ev(type="meta", conversation_id=cid, model=req.model, run_id=run.id, provider=("cloud" if cloud.is_cloud(req.model) else "ollama"))
        final = ""
        try:
            async for e in agent.run_agent(run, req.model, msgs, build_system_prompt(get_prefs(), cid), req.text_mode):
                if e["type"] == "token":
                    final += e["text"]
                elif e["type"] == "final":
                    final = e["text"]
                yield _ev(**e)
        except asyncio.CancelledError:
            run.stop.set()
            raise
        except Exception as e:
            log.exception("agent failed")
            yield _ev(type="error", message=str(e))
        finally:
            run.stop.set()
            agent.RUNS.pop(run.id, None)
            if final.strip():
                with db.conn() as c:
                    c.execute("INSERT INTO messages(conversation_id,role,content,model,created_at) VALUES(?,?,?,?,?)",
                              (cid, "assistant", final, req.model, db.now()))
                    c.execute("UPDATE conversations SET updated_at=?, model=? WHERE id=?", (db.now(), req.model, cid))
        yield _ev(type="done")

    return StreamingResponse(gen(), media_type="application/x-ndjson")


@app.get("/api/screen/last")
def screen_last():
    """Siste skjermbilde agenten tok (lagret bare lokalt), så brukeren kan se hva modellen så."""
    from fastapi.responses import FileResponse
    from . import screen
    p = screen.last_path()
    if not p.exists():
        raise HTTPException(404, "Ingen skjermbilder tatt ennå")
    return FileResponse(p, media_type="image/png", headers={"Cache-Control": "no-store"})


@app.post("/api/agent/{run_id}/approve")
def agent_approve(run_id: str, req: ApproveReq):
    run = agent.RUNS.get(run_id)
    fut = run.pending.get(req.call_id) if run else None
    if not fut or fut.done():
        raise HTTPException(404, "Ingen ventende godkjenning")
    fut.set_result(bool(req.allow))
    return {"ok": True}


@app.post("/api/agent/{run_id}/stop")
def agent_stop(run_id: str):
    run = agent.RUNS.get(run_id)
    if not run:
        return {"ok": True, "already_finished": True}
    run.stop.set()
    return {"ok": True}


@app.get("/api/agent/config")
def agent_config():
    return {"roots": tools.get_roots(),
            "tools": [{"name": t.name, "description": t.description, "risk": t.risk, "needs_approval": t.needs_approval}
                      for t in tools.TOOLS.values()]}


@app.put("/api/agent/config")
def agent_config_put(body: dict):
    try:
        roots = tools.set_roots([str(x) for x in body.get("roots", [])])
    except tools.ToolError as e:
        raise HTTPException(422, str(e))
    return {"roots": roots}


@app.get("/api/activity")
def activity(limit: int = 100):
    with db.conn() as c:
        rows = c.execute("SELECT * FROM activity ORDER BY id DESC LIMIT ?", (min(limit, 500),)).fetchall()
    return [dict(r) for r in rows]


@app.get("/api/system")
async def system_info(refresh: bool = False):
    hw = await asyncio.to_thread(system.hardware, refresh)
    return system.hw_dict(hw)


@app.get("/api/system/rate")
async def system_rate(size_gb: float):
    await load_cal()
    hw = await asyncio.to_thread(system.hardware)
    return system.rate(size_gb, hw)


@app.get("/api/recommendations")
async def recommendations():
    await load_cal()
    hw = await asyncio.to_thread(system.hardware)
    try:
        topics = await system.recommendations(hw)
    except Exception as e:
        return {"ok": False, "error": str(e), "hardware": system.hw_dict(hw), "topics": []}
    return {"ok": True, "hardware": system.hw_dict(hw), "topics": topics,
            "calibrated": system.CAL["k"] is not None, "measured_models": sorted(system.CAL["measured"])}


@app.post("/api/benchmark")
async def benchmark(req: BenchRequest):
    """Ekte hastighetstest: lar valgt modell skrive litt tekst og måler tokens per sekund."""
    try:
        r = await ollama.bench(req.model)
    except (httpx.ConnectError, httpx.ConnectTimeout):
        raise HTTPException(503, "Får ikke kontakt med Ollama")
    except Exception as e:
        raise HTTPException(500, str(e))
    size_gb = 0.0
    try:
        size_gb = next((m.get("size", 0) for m in await ollama.tags() if m["name"] == req.model), 0) / 1e9
    except Exception:
        pass
    r = {**r, "size_gb": round(size_gb, 2)}
    with db.conn() as c:
        c.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)",
                  (f"bench:{req.model}", json.dumps({**r, "at": db.now()})))
    await load_cal()
    return r


async def load_cal():
    """Henter lagrede målinger og kalibrerer vurderingen. Måling for modeller som er slettet ignoreres."""
    hw = await asyncio.to_thread(system.hardware)
    with db.conn() as c:
        rows = c.execute("SELECT key,value FROM settings WHERE key LIKE 'bench:%'").fetchall()
    try:
        installed = {m["name"] for m in await ollama.tags()}
    except Exception:
        installed = None
    data = {r["key"][6:]: json.loads(r["value"]) for r in rows}
    if installed is not None:
        data = {k: v for k, v in data.items() if k in installed}
    system.set_calibration(data, hw)


@app.post("/api/benchmark/auto")
async def benchmark_auto():
    """Måler alle installerte modeller som ikke er målt ennå (minste først)."""
    try:
        items = sorted(await ollama.tags(), key=lambda m: m.get("size", 0))
    except Exception:
        raise HTTPException(503, "Får ikke kontakt med Ollama")
    with db.conn() as c:
        have = {r["key"][6:] for r in c.execute("SELECT key FROM settings WHERE key LIKE 'bench:%'").fetchall()}
    todo = [m["name"] for m in items if m["name"] not in have][:3]
    done, errors = [], {}
    for name in todo:
        try:
            done.append(await benchmark(BenchRequest(model=name)))
        except HTTPException as e:
            errors[name] = str(e.detail)
    return {"measured": done, "errors": errors, "remaining": max(0, len([m for m in items if m["name"] not in have]) - len(todo))}


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
    await load_cal()
    try:
        hw = await asyncio.to_thread(system.hardware)
        models = await library.browse(q)
        for m in models:
            m["size_ratings"] = []
            for lab in m["sizes"]:
                gb = system.est_size_from_params(lab)
                m["size_ratings"].append({"label": lab, "est_gb": gb, **(system.rate(gb, hw) if gb else {"level": "unknown", "reason": ""})})
            m["categories"] = library.categorize(m)
            m["fits"] = any(r["level"] in ("green", "yellow") for r in m["size_ratings"])
        counts = {cid: sum(1 for m in models if cid in m["categories"]) for cid, _ in library.CATEGORIES}
        counts["passer"] = sum(1 for m in models if m["fits"])
        return {"ok": True, "models": models, "categories": [{"id": c, "label": l, "count": counts[c]} for c, l in library.CATEGORIES], "fits_count": counts["passer"], "source": "ollama.com/library"}
    except Exception as e:
        return {"ok": False, "error": f"Kunne ikke hente modelliste fra ollama.com ({e})", "models": []}


@app.get("/api/library/{name}/tags")
async def library_tags(name: str):
    await load_cal()
    if not re.fullmatch(r"[A-Za-z0-9._-]+", name):
        raise HTTPException(422, "Ugyldig modellnavn")
    try:
        hw = await asyncio.to_thread(system.hardware)
        return {"ok": True, "tags": [{**t, **system.rate(t["size_gb"], hw, t["tag"])} for t in await library.tags(name)]}
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
