"""v1.5: Prosjekter. Et prosjekt har et navn og egne instrukser som legges til systemprompten i alle samtaler som hører til det."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import db

router = APIRouter()
db.init()

with db.conn() as _c:
    _c.executescript("""CREATE TABLE IF NOT EXISTS projects (
      id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, instructions TEXT NOT NULL DEFAULT '', created_at REAL NOT NULL);""")
    if "project_id" not in {r["name"] for r in _c.execute("PRAGMA table_info(conversations)").fetchall()}:
        _c.execute("ALTER TABLE conversations ADD COLUMN project_id INTEGER")


class ProjIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    instructions: str = Field(default="", max_length=4000)


class ProjPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    instructions: str | None = Field(default=None, max_length=4000)


class AssignIn(BaseModel):
    project_id: int | None = None


def instructions_for(cid: int | None) -> str:
    """Tekst som legges til systemprompten for denne samtalen ('' hvis ingen prosjekt)."""
    if not cid:
        return ""
    with db.conn() as c:
        r = c.execute("SELECT p.name, p.instructions FROM conversations v JOIN projects p ON p.id=v.project_id WHERE v.id=?", (cid,)).fetchone()
    if not r:
        return ""
    t = f"\n\nDenne samtalen hører til prosjektet «{r['name']}»."
    if r["instructions"].strip():
        t += " Følg disse prosjektinstruksene:\n" + r["instructions"].strip()
    return t


@router.get("/api/projects")
def projects():
    with db.conn() as c:
        rows = c.execute("""SELECT p.id, p.name, p.instructions, COUNT(v.id) AS chats FROM projects p
                            LEFT JOIN conversations v ON v.project_id=p.id GROUP BY p.id ORDER BY p.created_at""").fetchall()
    return [dict(r) for r in rows]


@router.post("/api/projects")
def create(b: ProjIn):
    with db.conn() as c:
        pid = c.execute("INSERT INTO projects(name,instructions,created_at) VALUES(?,?,?)", (b.name.strip(), b.instructions, db.now())).lastrowid
    return {"id": pid}


@router.patch("/api/projects/{pid}")
def patch(pid: int, b: ProjPatch):
    with db.conn() as c:
        r = c.execute("SELECT name, instructions FROM projects WHERE id=?", (pid,)).fetchone()
        if not r:
            raise HTTPException(404, "Prosjektet finnes ikke")
        c.execute("UPDATE projects SET name=?, instructions=? WHERE id=?",
                  (b.name.strip() if b.name else r["name"], r["instructions"] if b.instructions is None else b.instructions, pid))
    return {"ok": True}


@router.delete("/api/projects/{pid}")
def delete(pid: int):
    """Sletter bare prosjektet. Samtalene blir værende, uten prosjekt."""
    with db.conn() as c:
        c.execute("UPDATE conversations SET project_id=NULL WHERE project_id=?", (pid,))
        c.execute("DELETE FROM projects WHERE id=?", (pid,))
    return {"ok": True}


@router.put("/api/conversations/{cid}/project")
def assign(cid: int, b: AssignIn):
    with db.conn() as c:
        if b.project_id is not None and not c.execute("SELECT 1 FROM projects WHERE id=?", (b.project_id,)).fetchone():
            raise HTTPException(404, "Prosjektet finnes ikke")
        if c.execute("UPDATE conversations SET project_id=? WHERE id=?", (b.project_id, cid)).rowcount == 0:
            raise HTTPException(404, "Samtalen finnes ikke")
    return {"ok": True}


@router.get("/api/today")
def today(date: str | None = None):
    """Samlet dagsoversikt til Home. `date` (YYYY-MM-DD, brukerens lokale dag) kan sendes inn; ellers brukes PC-ens dato."""
    import re, time as _t
    from . import cloud, extras
    d = date if date and re.fullmatch(r"\d{4}-\d{2}-\d{2}", date) else _t.strftime("%Y-%m-%d")
    notes = [n for n in extras.list_notes(include_done=False)]
    dated = [n for n in notes if n["due"] and re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(n["due"]))]
    now = _t.time()
    with db.conn() as c:
        due_cards = c.execute("SELECT COUNT(*) FROM cards WHERE due<=?", (now,)).fetchone()[0]
        total_cards = c.execute("SELECT COUNT(*) FROM cards").fetchone()[0]
        last = c.execute("""SELECT v.id, v.title, v.updated_at, p.name AS project FROM conversations v
                            LEFT JOIN projects p ON p.id=v.project_id ORDER BY v.updated_at DESC LIMIT 1""").fetchone()
    quota = []
    for pid in cloud.PROVIDERS:
        s = cloud.status(pid)
        if s["enabled"] and s["usage"].get("limit") is not None:
            u = s["usage"]
            quota.append({"id": pid, "label": s["label"], "remaining": u["remaining"], "limit": u["limit"], "unit": u["unit"], "pct": u["pct"]})
    return {"date": d, "tasks_open": len(notes),
            "tasks_overdue": [n for n in dated if n["due"] < d][:5], "tasks_today": [n for n in dated if n["due"] == d][:5],
            "tasks_next": [n for n in notes if n not in dated or n["due"] >= d][:3],
            "cards_due": due_cards, "cards_total": total_cards, "quota": quota, "last_chat": dict(last) if last else None}
