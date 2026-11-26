"""Langtidsminne i SQLite. Brukeren ser, redigerer og sletter alt. Minnene legges i systemprompten
(maks MEM_CHARS tegn) når minne er slått på, og agenten kan lagre nye med verktøyet «remember»."""
import re
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import db

router = APIRouter()
KINDS = ("fact", "preference", "decision", "project")
MEM_CHARS = 2000
MAX_MEMORIES = 500


class MemIn(BaseModel):
    content: str = Field(min_length=1, max_length=500)
    kind: str = Field(default="fact", pattern="^(fact|preference|decision|project)$")
    pinned: bool = False


class MemPatch(BaseModel):
    content: Optional[str] = Field(default=None, min_length=1, max_length=500)
    kind: Optional[str] = Field(default=None, pattern="^(fact|preference|decision|project)$")
    pinned: Optional[bool] = None


def enabled() -> bool:
    with db.conn() as c:
        r = c.execute("SELECT value FROM settings WHERE key='memory:enabled'").fetchone()
    return r is None or r["value"] != "0"


def set_enabled(v: bool) -> None:
    with db.conn() as c:
        c.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('memory:enabled',?)", ("1" if v else "0",))


def add(content: str, kind: str = "fact", source: str = "user", pinned: bool = False) -> dict:
    content = re.sub(r"\s+", " ", content).strip()
    if not content:
        raise ValueError("Tomt minne")
    content = content[:500]
    with db.conn() as c:
        dup = c.execute("SELECT id FROM memories WHERE lower(content)=lower(?)", (content,)).fetchone()
        if dup:
            return {"id": dup["id"], "duplicate": True}
        n = c.execute("SELECT count(*) n FROM memories").fetchone()["n"]
        if n >= MAX_MEMORIES:
            raise ValueError(f"Maks {MAX_MEMORIES} minner. Slett noen først.")
        t = db.now()
        cur = c.execute("INSERT INTO memories(content,kind,source,pinned,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                        (content, kind, source, int(pinned), t, t))
        return {"id": cur.lastrowid, "duplicate": False}


def context() -> str:
    """Tekstblokk til systemprompten. Festede først, deretter nyeste, til grensen er nådd."""
    if not enabled():
        return ""
    with db.conn() as c:
        rows = c.execute("SELECT content FROM memories ORDER BY pinned DESC, updated_at DESC").fetchall()
    out, used = [], 0
    for r in rows:
        line = "- " + r["content"]
        if used + len(line) > MEM_CHARS:
            break
        out.append(line)
        used += len(line) + 1
    if not out:
        return ""
    return "Dette husker du om brukeren (fra minnet deres, bruk det når det er relevant):\n" + "\n".join(out)


def _row(r) -> dict:
    d = dict(r)
    d["pinned"] = bool(d["pinned"])
    return d


@router.get("/api/memory")
def list_memories(q: str = ""):
    with db.conn() as c:
        if q.strip():
            like = "%" + q.strip().replace("%", "").replace("_", "") + "%"
            rows = c.execute("SELECT * FROM memories WHERE content LIKE ? ORDER BY pinned DESC, updated_at DESC", (like,)).fetchall()
        else:
            rows = c.execute("SELECT * FROM memories ORDER BY pinned DESC, updated_at DESC").fetchall()
    return {"enabled": enabled(), "items": [_row(r) for r in rows], "limit": MAX_MEMORIES, "context_chars": len(context())}


@router.post("/api/memory")
def create_memory(m: MemIn):
    try:
        r = add(m.content, m.kind, "user", m.pinned)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return r


@router.patch("/api/memory/{mid}")
def patch_memory(mid: int, m: MemPatch):
    with db.conn() as c:
        if not c.execute("SELECT 1 FROM memories WHERE id=?", (mid,)).fetchone():
            raise HTTPException(404, "Finnes ikke")
        if m.content is not None:
            c.execute("UPDATE memories SET content=? WHERE id=?", (re.sub(r"\s+", " ", m.content).strip(), mid))
        if m.kind is not None:
            c.execute("UPDATE memories SET kind=? WHERE id=?", (m.kind, mid))
        if m.pinned is not None:
            c.execute("UPDATE memories SET pinned=? WHERE id=?", (int(m.pinned), mid))
        c.execute("UPDATE memories SET updated_at=? WHERE id=?", (db.now(), mid))
    return {"ok": True}


@router.delete("/api/memory/{mid}")
def delete_memory(mid: int):
    with db.conn() as c:
        c.execute("DELETE FROM memories WHERE id=?", (mid,))
    return {"ok": True}


@router.delete("/api/memory")
def clear_memories(confirm: bool = False):
    if not confirm:
        raise HTTPException(400, "Bekreft med confirm=true")
    with db.conn() as c:
        c.execute("DELETE FROM memories")
    return {"ok": True}


@router.put("/api/memory/enabled")
def put_enabled(body: dict):
    set_enabled(bool(body.get("enabled")))
    return {"enabled": enabled()}
