"""Flere agenter som snakker sammen. Hver agent = navn, rolle, modell og tillatte verktøy.
Et rom har en felles meldingslogg. Agentene snakker i tur (én modell om gangen, pga. 8 GB RAM)."""
import asyncio
import json
import re
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from . import agent, db, ollama, tools

router = APIRouter()
LOG_LIMIT = 40
MAX_ROUNDS_CAP = 6
DONE_MARK = "[FERDIG]"


def _ev(**kw) -> bytes:
    return (json.dumps(kw, ensure_ascii=False) + "\n").encode()


class AgentIn(BaseModel):
    name: str = Field(min_length=1, max_length=30)
    role: str = Field(default="", max_length=200)
    prompt: str = Field(default="", max_length=4000)
    model: Optional[str] = Field(default=None, max_length=120)
    tools: list[str] = []


class RoomIn(BaseModel):
    title: str = Field(min_length=1, max_length=80)
    agent_ids: list[int] = Field(min_length=1, max_length=6)
    max_rounds: int = Field(default=2, ge=1, le=MAX_ROUNDS_CAP)
    mode: str = Field(default="roundrobin", pattern="^(roundrobin|leader)$")


class RoomRun(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    default_model: str = Field(min_length=1)


def _agent_row(r) -> dict:
    d = dict(r)
    d["tools"] = json.loads(d["tools"] or "[]")
    return d


def _room_row(r) -> dict:
    d = dict(r)
    d["agent_ids"] = json.loads(d["agent_ids"] or "[]")
    return d


def _check_tools(names: list[str]) -> list[str]:
    bad = [n for n in names if n not in tools.TOOLS]
    if bad:
        raise HTTPException(422, "Ukjente verktøy: " + ", ".join(bad))
    return names


# ---------- agenter ----------
@router.get("/api/agents")
def list_agents():
    with db.conn() as c:
        return [_agent_row(r) for r in c.execute("SELECT * FROM agents ORDER BY id").fetchall()]


@router.post("/api/agents")
def create_agent(a: AgentIn):
    _check_tools(a.tools)
    with db.conn() as c:
        i = c.execute("INSERT INTO agents(name,role,prompt,model,tools,created_at) VALUES(?,?,?,?,?,?)",
                      (a.name.strip(), a.role, a.prompt, a.model, json.dumps(a.tools), db.now())).lastrowid
        return _agent_row(c.execute("SELECT * FROM agents WHERE id=?", (i,)).fetchone())


@router.put("/api/agents/{aid}")
def update_agent(aid: int, a: AgentIn):
    _check_tools(a.tools)
    with db.conn() as c:
        if not c.execute("SELECT 1 FROM agents WHERE id=?", (aid,)).fetchone():
            raise HTTPException(404, "Agenten finnes ikke")
        c.execute("UPDATE agents SET name=?,role=?,prompt=?,model=?,tools=? WHERE id=?",
                  (a.name.strip(), a.role, a.prompt, a.model, json.dumps(a.tools), aid))
        return _agent_row(c.execute("SELECT * FROM agents WHERE id=?", (aid,)).fetchone())


@router.delete("/api/agents/{aid}")
def delete_agent(aid: int):
    with db.conn() as c:
        c.execute("DELETE FROM agents WHERE id=?", (aid,))
        # fjern fra rom, og slett rom som blir tomme
        for r in c.execute("SELECT id,agent_ids FROM rooms").fetchall():
            ids = [x for x in json.loads(r["agent_ids"]) if x != aid]
            if ids:
                c.execute("UPDATE rooms SET agent_ids=? WHERE id=?", (json.dumps(ids), r["id"]))
            else:
                c.execute("DELETE FROM rooms WHERE id=?", (r["id"],))
    return {"ok": True}


# ---------- rom ----------
def _validate_agents(ids: list[int]) -> None:
    with db.conn() as c:
        have = {r["id"] for r in c.execute("SELECT id FROM agents").fetchall()}
    if not set(ids) <= have or len(set(ids)) != len(ids):
        raise HTTPException(422, "Ugyldige agenter i rommet")


@router.get("/api/rooms")
def list_rooms():
    with db.conn() as c:
        return [_room_row(r) for r in c.execute("SELECT * FROM rooms ORDER BY id DESC").fetchall()]


@router.post("/api/rooms")
def create_room(r: RoomIn):
    _validate_agents(r.agent_ids)
    with db.conn() as c:
        i = c.execute("INSERT INTO rooms(title,agent_ids,max_rounds,mode,created_at) VALUES(?,?,?,?,?)",
                      (r.title.strip(), json.dumps(r.agent_ids), r.max_rounds, r.mode, db.now())).lastrowid
        return _room_row(c.execute("SELECT * FROM rooms WHERE id=?", (i,)).fetchone())


@router.put("/api/rooms/{rid}")
def update_room(rid: int, r: RoomIn):
    _validate_agents(r.agent_ids)
    with db.conn() as c:
        if not c.execute("SELECT 1 FROM rooms WHERE id=?", (rid,)).fetchone():
            raise HTTPException(404, "Rommet finnes ikke")
        c.execute("UPDATE rooms SET title=?,agent_ids=?,max_rounds=?,mode=? WHERE id=?",
                  (r.title.strip(), json.dumps(r.agent_ids), r.max_rounds, r.mode, rid))
        return _room_row(c.execute("SELECT * FROM rooms WHERE id=?", (rid,)).fetchone())


@router.delete("/api/rooms/{rid}")
def delete_room(rid: int):
    with db.conn() as c:
        c.execute("DELETE FROM rooms WHERE id=?", (rid,))
    return {"ok": True}


@router.get("/api/rooms/{rid}")
def get_room(rid: int):
    with db.conn() as c:
        r = c.execute("SELECT * FROM rooms WHERE id=?", (rid,)).fetchone()
        if not r:
            raise HTTPException(404, "Rommet finnes ikke")
        msgs = c.execute("SELECT id,author,agent_id,content,created_at FROM room_messages WHERE room_id=? ORDER BY id", (rid,)).fetchall()
    return {**_room_row(r), "messages": [dict(m) for m in msgs]}


@router.post("/api/rooms/{rid}/clear")
def clear_room(rid: int):
    with db.conn() as c:
        c.execute("DELETE FROM room_messages WHERE room_id=?", (rid,))
    return {"ok": True}


@router.post("/api/rooms/example")
def create_example():
    """Ett klikk: tre agenter og et rom, så man ser hvordan det virker."""
    spec = [("Idéviser", "Kommer med kreative forslag", "Du kommer med 2-3 konkrete, kreative forslag. Bygg videre på det andre har sagt. Svar kort (maks 4 setninger)."),
            ("Kritiker", "Finner svakheter", "Du leter etter svakheter og risiko i det som er foreslått, og sier hva som kan gå galt. Vær saklig og kort (maks 4 setninger)."),
            ("Oppsummerer", "Lander en konklusjon", f"Du oppsummerer diskusjonen og lander en tydelig anbefaling i 3-4 setninger. Avslutt med {DONE_MARK}.")]
    ids = []
    with db.conn() as c:
        for n, role, p in spec:
            ids.append(c.execute("INSERT INTO agents(name,role,prompt,model,tools,created_at) VALUES(?,?,?,?,?,?)",
                                 (n, role, p, None, "[]", db.now())).lastrowid)
        rid = c.execute("INSERT INTO rooms(title,agent_ids,max_rounds,mode,created_at) VALUES(?,?,?,?,?)",
                        ("Idémyldring", json.dumps(ids), 2, "roundrobin", db.now())).lastrowid
    return get_room(rid)


# ---------- samtalen ----------
def transcript(msgs: list[dict]) -> str:
    return "\n".join(f"[{m['author']}]: {m['content']}" for m in msgs[-LOG_LIMIT:])


def last_user_text(log: list[dict]) -> str:
    return next((m["content"] for m in reversed(log) if m["author"] == "Du"), "")


def turn_messages(ag: dict, members: list[dict], log: list[dict]) -> list[dict]:
    names = ", ".join(f"{m['name']} ({m['role']})" if m["role"] else m["name"] for m in members)
    q = last_user_text(log)
    system = (f"Du er {ag['name']}" + (f", {ag['role']}" if ag["role"] else "") + ". "
              f"Du er med i et samtalerom med: {names}, og brukeren. "
              "VIKTIGST: Svar først og fremst direkte på det brukeren faktisk spør om eller ber om i sin siste melding. "
              "Rollen din styrer bare vinkel, ekspertise og tonefall. Den er ikke temaet. "
              "Ikke presenter deg, ikke beskriv rollen din og ikke snakk om oppgaven din med mindre brukeren spør om det. "
              "Hvis spørsmålet ligger utenfor ekspertisen din, svar likevel kort så godt du kan, og si hvem i rommet som passer bedre. "
              + (f"Din stil og ekspertise: {ag['prompt']} " if ag["prompt"] else "")
              + "Skriv KUN din egen replikk, uten å skrive for andre og uten å starte med navnet ditt. "
              "Svar på samme språk som brukeren. Svar kort.")
    user = ("Samtalen så langt:\n" + transcript(log)
            + (f"\n\nBrukerens siste melding, som du skal svare direkte på:\n«{q}»" if q else "")
            + f"\n\nDet er din tur, {ag['name']}.")
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def pick_leader_choice(text: str, members: list[dict], last: str | None) -> str | None:
    """Leseren gir tilbake navnet på neste taler, 'FERDIG', eller None hvis svaret ikke kan tolkes."""
    t = text.strip().lower()
    if "ferdig" in t and not any(m["name"].lower() in t for m in members):
        return "FERDIG"
    found = [m["name"] for m in members if re.search(r"\b" + re.escape(m["name"].lower()) + r"\b", t)]
    found = [n for n in found if n != last] or found
    return found[0] if found else None


async def run_room(room: dict, members: list[dict], user_text: str, default_model: str, run: "agent.Run", base_system: str):
    rid = room["id"]
    with db.conn() as c:
        c.execute("INSERT INTO room_messages(room_id,author,agent_id,content,created_at) VALUES(?,?,?,?,?)",
                  (rid, "Du", None, user_text, db.now()))
        log = [dict(r) for r in c.execute("SELECT author,content FROM room_messages WHERE room_id=? ORDER BY id", (rid,)).fetchall()]
    yield {"type": "user_message", "text": user_text}
    total_turns = room["max_rounds"] * len(members)
    last: str | None = None
    order = list(members)
    turn = 0
    while turn < total_turns:
        if run.stop.is_set():
            yield {"type": "stopped"}; return
        if room["mode"] == "leader" and len(members) > 1:
            leader = members[0]
            q = [{"role": "system", "content": "Du leder en gruppesamtale. Svar med KUN navnet på hvem som skal snakke neste gang, eller ordet FERDIG hvis brukerens siste spørsmål er besvart. Velg den deltakeren som best kan svare på brukerens siste spørsmål. Deltakere: " + ", ".join(f"{m['name']} ({m['role']})" if m["role"] else m["name"] for m in members)},
                 {"role": "user", "content": transcript(log) + "\n\nBrukerens siste spørsmål: " + user_text + "\nHvem snakker neste gang?"}]
            ans = ""
            try:
                async for kind, val in ollama.chat_stream(leader["model"] or default_model, q):
                    if kind == "token":
                        ans += val  # type: ignore
            except Exception:
                ans = ""
            ch = pick_leader_choice(ans, members, last)
            if ch == "FERDIG" and turn == 0:
                ch = None                          # første replikk må alltid svare brukeren
            if ch == "FERDIG":
                yield {"type": "notice", "text": "Lederen avsluttet samtalen."}; break
            nxt = next((m for m in members if m["name"] == ch), None) if ch else None
            if nxt is None:
                nxt = order[turn % len(order)]       # kunne ikke tolke lederen: rund-og-rund i stedet
        else:
            nxt = order[turn % len(order)]
        turn += 1
        last = nxt["name"]
        model = nxt["model"] or default_model
        yield {"type": "turn_start", "agent_id": nxt["id"], "agent": nxt["name"], "model": model}
        parts: list[str] = []
        msgs = turn_messages(nxt, members, log)
        error = None
        try:
            if nxt["tools"]:
                async for e in agent.run_agent(run, model, msgs[1:], msgs[0]["content"], False, set(nxt["tools"])):
                    if e["type"] in ("tool_call", "approval", "tool_result", "notice"):
                        yield {**e, "agent": nxt["name"]}
                    elif e["type"] == "token":
                        yield {"type": "token", "agent": nxt["name"], "text": e["text"]}
                    elif e["type"] == "final":
                        parts = [e["text"]]
                    elif e["type"] == "stopped":
                        yield e; return
                    elif e["type"] == "error":
                        error = e["message"]
            else:
                async for kind, val in ollama.chat_stream(model, msgs):
                    if run.stop.is_set():
                        break
                    if kind == "token":
                        parts.append(val)  # type: ignore
                        yield {"type": "token", "agent": nxt["name"], "text": val}
        except (httpx.ConnectError, httpx.ConnectTimeout):
            error = "Får ikke kontakt med Ollama. Er Ollama startet?"
        except Exception as e:
            error = str(e)
        if run.stop.is_set():
            yield {"type": "stopped"}; return
        if error:
            yield {"type": "error", "message": f"{nxt['name']}: {error}"}; return
        text = "".join(parts).strip()
        done = DONE_MARK.lower() in text.lower()
        text = re.sub(re.escape(DONE_MARK), "", text, flags=re.I).strip()
        if text:
            with db.conn() as c:
                c.execute("INSERT INTO room_messages(room_id,author,agent_id,content,created_at) VALUES(?,?,?,?,?)",
                          (rid, nxt["name"], nxt["id"], text, db.now()))
            log.append({"author": nxt["name"], "content": text})
        yield {"type": "turn_end", "agent": nxt["name"], "text": text}
        if done:
            yield {"type": "notice", "text": f"{nxt['name']} mener samtalen er ferdig."}
            break


@router.post("/api/rooms/{rid}/run")
async def room_run(rid: int, req: RoomRun):
    from . import main as m   # unngår sirkulær import ved oppstart
    with db.conn() as c:
        r = c.execute("SELECT * FROM rooms WHERE id=?", (rid,)).fetchone()
        if not r:
            raise HTTPException(404, "Rommet finnes ikke")
        room = _room_row(r)
        ags = {a["id"]: _agent_row(a) for a in c.execute("SELECT * FROM agents").fetchall()}
    members = [ags[i] for i in room["agent_ids"] if i in ags]
    if not members:
        raise HTTPException(422, "Rommet har ingen agenter")
    run = agent.Run()
    agent.RUNS[run.id] = run

    async def gen():
        yield _ev(type="meta", run_id=run.id, room_id=rid)
        try:
            async for e in run_room(room, members, req.message, req.default_model, run, m.build_system_prompt(m.get_prefs())):
                yield _ev(**e)
        except asyncio.CancelledError:
            run.stop.set(); raise
        except Exception as e:
            yield _ev(type="error", message=str(e))
        finally:
            run.stop.set()
            agent.RUNS.pop(run.id, None)
        yield _ev(type="done")

    return StreamingResponse(gen(), media_type="application/x-ndjson")
