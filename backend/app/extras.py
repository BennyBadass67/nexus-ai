"""v1.0: søk overalt, notater, prompt-maler, eksport/sikkerhetskopi, systemmonitor og lokal dokumentsøk (kunnskap).
Alt er lokalt. Ingen nye pakker."""
import io
import json
import math
import os
import re
import sqlite3
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel, Field

from . import config, db

router = APIRouter()

EXTRA_SCHEMA = """
CREATE TABLE IF NOT EXISTS notes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  text TEXT NOT NULL,
  done INTEGER NOT NULL DEFAULT 0,
  due TEXT,
  source TEXT NOT NULL DEFAULT 'user',
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS templates (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS kdocs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  path TEXT NOT NULL UNIQUE,
  mtime REAL NOT NULL,
  size INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS kchunks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  doc_id INTEGER NOT NULL REFERENCES kdocs(id) ON DELETE CASCADE,
  pos INTEGER NOT NULL,
  text TEXT NOT NULL
);
"""


def init() -> None:
    with db.conn() as c:
        c.executescript(EXTRA_SCHEMA)


init()


def ensure() -> None:
    init()


# ---------- søk overalt ----------

def _like(q: str) -> str:
    return "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def _snip(text: str, q: str, n: int = 140) -> str:
    t = re.sub(r"\s+", " ", text)
    i = t.lower().find(q.lower())
    a = max(0, i - 40) if i >= 0 else 0
    return ("…" if a else "") + t[a:a + n] + ("…" if a + n < len(t) else "")


def search_all(q: str, limit: int = 8) -> dict:
    q = q.strip()
    if len(q) < 2:
        return {"query": q, "conversations": [], "memories": [], "agents": [], "notes": [], "rooms": [], "activity": []}
    like = _like(q)
    ensure()
    with db.conn() as c:
        conv = [{"id": r["conversation_id"], "title": r["title"], "snippet": _snip(r["content"], q), "role": r["role"]}
                for r in c.execute("SELECT m.conversation_id, c.title, m.content, m.role FROM messages m JOIN conversations c ON c.id=m.conversation_id "
                                   "WHERE m.content LIKE ? ESCAPE '\\' ORDER BY m.id DESC LIMIT ?", (like, limit)).fetchall()]
        conv += [{"id": r["id"], "title": r["title"], "snippet": "(tittel)", "role": "title"}
                 for r in c.execute("SELECT id,title FROM conversations WHERE title LIKE ? ESCAPE '\\' LIMIT ?", (like, limit)).fetchall()
                 if r["id"] not in {x["id"] for x in conv}]
        mem = [{"id": r["id"], "content": r["content"][:200], "kind": r["kind"]}
               for r in c.execute("SELECT id,content,kind FROM memories WHERE content LIKE ? ESCAPE '\\' ORDER BY pinned DESC, updated_at DESC LIMIT ?", (like, limit)).fetchall()]
        ag = [{"id": r["id"], "name": r["name"], "role": r["role"]}
              for r in c.execute("SELECT id,name,role FROM agents WHERE name LIKE ? ESCAPE '\\' OR role LIKE ? ESCAPE '\\' OR prompt LIKE ? ESCAPE '\\' LIMIT ?", (like, like, like, limit)).fetchall()]
        notes = [{"id": r["id"], "text": r["text"][:200], "done": bool(r["done"])}
                 for r in c.execute("SELECT id,text,done FROM notes WHERE text LIKE ? ESCAPE '\\' ORDER BY id DESC LIMIT ?", (like, limit)).fetchall()]
        rooms = [{"id": r["room_id"], "title": r["title"], "snippet": _snip(r["content"], q), "author": r["author"]}
                 for r in c.execute("SELECT m.room_id, r.title, m.content, m.author FROM room_messages m JOIN rooms r ON r.id=m.room_id "
                                    "WHERE m.content LIKE ? ESCAPE '\\' ORDER BY m.id DESC LIMIT ?", (like, limit)).fetchall()]
        act = [{"id": r["id"], "tool": r["tool"], "detail": (r["detail"] or "")[:160], "status": r["status"]}
               for r in c.execute("SELECT id,tool,detail,status FROM activity WHERE detail LIKE ? ESCAPE '\\' OR tool LIKE ? ESCAPE '\\' ORDER BY id DESC LIMIT ?", (like, like, limit)).fetchall()]
    return {"query": q, "conversations": conv[:limit], "memories": mem, "agents": ag, "notes": notes, "rooms": rooms, "activity": act}


@router.get("/api/search")
def api_search(q: str = "", limit: int = 8):
    return search_all(q, max(1, min(limit, 25)))


# ---------- notater ----------

class NoteIn(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    due: str | None = Field(default=None, max_length=40)


def add_note(text: str, due: str | None = None, source: str = "user") -> dict:
    t = text.strip()
    if not t:
        raise HTTPException(422, "Notatet er tomt")
    ensure()
    with db.conn() as c:
        dup = c.execute("SELECT id FROM notes WHERE text=? AND done=0", (t,)).fetchone()
        if dup:
            return {"id": dup["id"], "duplicate": True}
        i = c.execute("INSERT INTO notes(text,due,source,created_at) VALUES(?,?,?,?)", (t, due, source, db.now())).lastrowid
    return {"id": i, "duplicate": False}


def _note(r) -> dict:
    return {"id": r["id"], "text": r["text"], "done": bool(r["done"]), "due": r["due"], "source": r["source"], "created_at": r["created_at"]}


def list_notes(include_done: bool = True) -> list[dict]:
    ensure()
    with db.conn() as c:
        rows = c.execute("SELECT * FROM notes " + ("" if include_done else "WHERE done=0 ") + "ORDER BY done, id DESC").fetchall()
    return [_note(r) for r in rows]


@router.get("/api/notes")
def api_notes():
    return list_notes()


@router.post("/api/notes")
def api_add_note(n: NoteIn):
    return add_note(n.text, n.due)


@router.patch("/api/notes/{nid}")
def api_patch_note(nid: int, body: dict):
    ensure()
    with db.conn() as c:
        if not c.execute("SELECT 1 FROM notes WHERE id=?", (nid,)).fetchone():
            raise HTTPException(404, "Notatet finnes ikke")
        if "done" in body:
            c.execute("UPDATE notes SET done=? WHERE id=?", (1 if body["done"] else 0, nid))
        if "text" in body and str(body["text"]).strip():
            c.execute("UPDATE notes SET text=? WHERE id=?", (str(body["text"]).strip()[:500], nid))
    return {"ok": True}


@router.delete("/api/notes/{nid}")
def api_del_note(nid: int):
    ensure()
    with db.conn() as c:
        c.execute("DELETE FROM notes WHERE id=?", (nid,))
    return {"ok": True}


# ---------- prompt-maler ----------

class TplIn(BaseModel):
    title: str = Field(min_length=1, max_length=60)
    body: str = Field(min_length=1, max_length=4000)


@router.get("/api/templates")
def api_templates():
    ensure()
    with db.conn() as c:
        return [dict(r) for r in c.execute("SELECT id,title,body FROM templates ORDER BY id").fetchall()]


@router.post("/api/templates")
def api_add_template(t: TplIn):
    ensure()
    with db.conn() as c:
        i = c.execute("INSERT INTO templates(title,body,created_at) VALUES(?,?,?)", (t.title.strip(), t.body, db.now())).lastrowid
    return {"id": i}


@router.delete("/api/templates/{tid}")
def api_del_template(tid: int):
    ensure()
    with db.conn() as c:
        c.execute("DELETE FROM templates WHERE id=?", (tid,))
    return {"ok": True}


# ---------- eksport ----------

def conversation_markdown(cid: int, user_name: str = "Du") -> tuple[str, str]:
    with db.conn() as c:
        conv = c.execute("SELECT * FROM conversations WHERE id=?", (cid,)).fetchone()
        if not conv:
            raise HTTPException(404, "Samtalen finnes ikke")
        msgs = c.execute("SELECT role,content,model,created_at FROM messages WHERE conversation_id=? ORDER BY id", (cid,)).fetchall()
    out = [f"# {conv['title']}", "", f"_Eksportert fra NEXUS AI {time.strftime('%d.%m.%Y %H:%M')}_", ""]
    for m in msgs:
        who = user_name if m["role"] == "user" else f"NEXUS ({m['model']})" if m["model"] else "NEXUS"
        out += [f"**{who}**", "", m["content"], ""]
    name = re.sub(r"[^\w\-. ]+", "", conv["title"], flags=re.U).strip()[:40] or f"samtale-{cid}"
    return name, "\n".join(out)


@router.get("/api/conversations/{cid}/export")
def api_export_conv(cid: int):
    name, md = conversation_markdown(cid)
    return PlainTextResponse(md, headers={"Content-Disposition": f"attachment; filename*=UTF-8''{__import__('urllib.parse').parse.quote(name)}.md"},
                             media_type="text/markdown; charset=utf-8")


# ---------- sikkerhetskopi ----------

REQUIRED = {"conversations", "messages", "settings", "memories", "agents", "rooms"}


def backup_bytes() -> bytes:
    ensure()
    fd, tmp = tempfile.mkstemp(suffix=".db"); os.close(fd)
    try:
        src = sqlite3.connect(config.DB_PATH)
        dst = sqlite3.connect(tmp)
        src.backup(dst); dst.close(); src.close()
        return Path(tmp).read_bytes()
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def restore_bytes(data: bytes) -> dict:
    if not data.startswith(b"SQLite format 3\x00"):
        raise HTTPException(400, "Filen er ikke en NEXUS-sikkerhetskopi")
    fd, tmp = tempfile.mkstemp(suffix=".db"); os.close(fd)
    try:
        Path(tmp).write_bytes(data)
        chk = sqlite3.connect(tmp)
        try:
            if chk.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise HTTPException(400, "Sikkerhetskopien er skadet")
            tables = {r[0] for r in chk.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not REQUIRED <= tables:
                raise HTTPException(400, "Filen mangler NEXUS-tabeller: " + ", ".join(sorted(REQUIRED - tables)))
            stats = {t: chk.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("conversations", "memories", "agents")}
        except sqlite3.DatabaseError:
            raise HTTPException(400, "Sikkerhetskopien kan ikke leses")
        finally:
            chk.close()
        # sikkerhetskopi av dagens data først, så en feil kan reverseres
        safety = config.DATA_DIR / f"before-restore-{int(time.time())}.db"
        try:
            safety.write_bytes(backup_bytes())
        except Exception:
            pass
        src = sqlite3.connect(tmp); dst = sqlite3.connect(config.DB_PATH)
        src.backup(dst); dst.close(); src.close()
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass
    ensure()
    return {"ok": True, "restored": stats, "safety_copy": str(safety)}


@router.get("/api/backup")
def api_backup():
    return Response(backup_bytes(), media_type="application/octet-stream",
                    headers={"Content-Disposition": f"attachment; filename=nexus-backup-{time.strftime('%Y%m%d-%H%M')}.db"})


@router.post("/api/backup/restore")
async def api_restore(request: Request):
    """Tar imot selve .db-filen som rå kropp (ingen multipart-pakke nødvendig)."""
    data = b""
    async for chunk in request.stream():
        data += chunk
        if len(data) > 200 * 1024 * 1024:
            raise HTTPException(413, "Filen er for stor")
    return restore_bytes(data)


# ---------- systemmonitor ----------

def _linux_cpu() -> tuple[int, int]:
    p = Path("/proc/stat").read_text().splitlines()[0].split()[1:]
    v = [int(x) for x in p]
    return v[3] + (v[4] if len(v) > 4 else 0), sum(v)


_cpu_prev: tuple[float, tuple] | None = None
_cpu_last: int | None = None


def sysmon() -> dict:
    global _cpu_prev, _cpu_last
    out: dict = {"cpu_pct": None, "ram_used_gb": None, "ram_total_gb": None, "ram_pct": None, "os": sys.platform}
    try:
        if sys.platform == "win32":
            import ctypes

            class MS(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong), ("ullTotalPhys", ctypes.c_ulonglong),
                            ("ullAvailPhys", ctypes.c_ulonglong), ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong), ("sullAvailExtendedVirtual", ctypes.c_ulonglong)]
            ms = MS(); ms.dwLength = ctypes.sizeof(MS)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms))
            tot, free = ms.ullTotalPhys, ms.ullAvailPhys

            class FT(ctypes.Structure):
                _fields_ = [("lo", ctypes.c_ulong), ("hi", ctypes.c_ulong)]
            i, k, u = FT(), FT(), FT()
            ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(i), ctypes.byref(k), ctypes.byref(u))
            val = lambda f: (f.hi << 32) | f.lo
            idle, total = val(i), val(k) + val(u)
        else:
            mi = {l.split(":")[0]: int(l.split()[1]) * 1024 for l in Path("/proc/meminfo").read_text().splitlines() if ":" in l}
            tot, free = mi["MemTotal"], mi.get("MemAvailable", mi.get("MemFree", 0))
            idle, total = _linux_cpu()
        out["ram_total_gb"] = round(tot / 1e9, 1); out["ram_used_gb"] = round((tot - free) / 1e9, 1)
        out["ram_pct"] = round(100 * (tot - free) / tot) if tot else None
        if _cpu_prev:
            di, dt = idle - _cpu_prev[0], total - _cpu_prev[1]
            if dt > 0:
                _cpu_last = max(0, min(100, round(100 * (1 - di / dt))))
                _cpu_prev = (idle, total)
        else:
            _cpu_prev = (idle, total)
        out["cpu_pct"] = _cpu_last
    except Exception as e:
        out["error"] = str(e)[:100]
    return out


@router.get("/api/sysmon")
async def api_sysmon():
    import httpx
    out = sysmon()
    try:
        async with httpx.AsyncClient(timeout=1.5) as c:
            r = await c.get(f"{config.OLLAMA_URL}/api/ps")
            out["loaded"] = [{"name": m.get("name"), "size_gb": round(m.get("size", 0) / 1e9, 1), "vram_gb": round(m.get("size_vram", 0) / 1e9, 1)} for m in r.json().get("models", [])]
    except Exception:
        out["loaded"] = None
    return out


# ---------- kunnskap: lokal dokumentsøk (BM25) ----------

TEXT_EXT = {".txt", ".md", ".markdown", ".rst", ".csv", ".json", ".py", ".js", ".ts", ".tsx", ".html", ".css", ".log", ".ini", ".yaml", ".yml", ".toml", ".java", ".c", ".cpp", ".cs", ".go", ".rs", ".sql", ".xml"}
SKIP_DIRS = {"node_modules", ".git", "__pycache__", "AppData", "$RECYCLE.BIN", "venv", ".venv", "dist", "build"}
MAX_FILE = 1_000_000
MAX_FILES = 3000
CHUNK = 900


def tokenize(s: str) -> list[str]:
    return [w for w in re.findall(r"\w+", s.lower(), flags=re.U) if len(w) > 1]


def chunk_text(text: str, size: int = CHUNK) -> list[str]:
    parts, cur = [], ""
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if not para:
            continue
        while len(para) > size:
            cut = para.rfind(" ", 0, size)
            cut = cut if cut > size // 2 else size
            if cur:
                parts.append(cur); cur = ""
            parts.append(para[:cut]); para = para[cut:].lstrip()
        if len(cur) + len(para) + 2 > size and cur:
            parts.append(cur); cur = ""
        cur = (cur + "\n\n" + para).strip()
    if cur:
        parts.append(cur)
    return parts


def index_folders(roots: list[str]) -> dict:
    """Indekserer tekstfiler i de godkjente mappene. Bare endrede filer leses på nytt. Fjernede filer slettes."""
    ensure()
    seen: set[str] = set(); added = updated = skipped = 0
    t0 = time.time()
    with db.conn() as c:
        known = {r["path"]: (r["id"], r["mtime"], r["size"]) for r in c.execute("SELECT id,path,mtime,size FROM kdocs").fetchall()}
        for root in roots:
            for dp, dns, fns in os.walk(root):
                dns[:] = [d for d in dns if d not in SKIP_DIRS and not d.startswith(".")]
                for fn in fns:
                    p = os.path.join(dp, fn)
                    if Path(fn).suffix.lower() not in TEXT_EXT:
                        continue
                    if len(seen) >= MAX_FILES or time.time() - t0 > 20:
                        skipped += 1; continue
                    try:
                        st = os.stat(p)
                    except OSError:
                        continue
                    if st.st_size > MAX_FILE or st.st_size == 0:
                        skipped += 1; continue
                    seen.add(p)
                    k = known.get(p)
                    if k and abs(k[1] - st.st_mtime) < 1e-6 and k[2] == st.st_size:
                        continue
                    try:
                        raw = Path(p).read_bytes()
                        if b"\x00" in raw[:2000]:
                            skipped += 1; seen.discard(p); continue
                        text = raw.decode("utf-8", "replace")
                    except OSError:
                        continue
                    if k:
                        c.execute("DELETE FROM kchunks WHERE doc_id=?", (k[0],))
                        c.execute("UPDATE kdocs SET mtime=?, size=? WHERE id=?", (st.st_mtime, st.st_size, k[0])); did = k[0]; updated += 1
                    else:
                        did = c.execute("INSERT INTO kdocs(path,mtime,size) VALUES(?,?,?)", (p, st.st_mtime, st.st_size)).lastrowid; added += 1
                    for i, ch in enumerate(chunk_text(text)):
                        c.execute("INSERT INTO kchunks(doc_id,pos,text) VALUES(?,?,?)", (did, i, ch))
        gone = [pid for path, (pid, _, _) in known.items() if path not in seen]
        for pid in gone:
            c.execute("DELETE FROM kdocs WHERE id=?", (pid,))
        files = c.execute("SELECT COUNT(*) FROM kdocs").fetchone()[0]
        chunks = c.execute("SELECT COUNT(*) FROM kchunks").fetchone()[0]
    return {"added": added, "updated": updated, "removed": len(gone), "skipped": skipped, "files": files, "chunks": chunks}


def knowledge_search(query: str, k: int = 5) -> list[dict]:
    terms = list(dict.fromkeys(tokenize(query)))
    if not terms:
        return []
    ensure()
    with db.conn() as c:
        n = c.execute("SELECT COUNT(*) FROM kchunks").fetchone()[0]
        if not n:
            return []
        cond = " OR ".join(["lower(text) LIKE ?"] * len(terms))
        rows = c.execute(f"SELECT k.id,k.doc_id,k.pos,k.text,d.path FROM kchunks k JOIN kdocs d ON d.id=k.doc_id WHERE {cond} LIMIT 4000",
                         [f"%{t}%" for t in terms]).fetchall()
        df = {t: c.execute("SELECT COUNT(*) FROM kchunks WHERE lower(text) LIKE ?", (f"%{t}%",)).fetchone()[0] for t in terms}
        avg = c.execute("SELECT AVG(LENGTH(text)) FROM kchunks").fetchone()[0] or 1
    scored = []
    for r in rows:
        toks = tokenize(r["text"]); tf = Counter(toks); L = max(1, len(toks))
        s = 0.0
        for t in terms:
            f = tf.get(t, 0)
            if not f:
                f = sum(v for w, v in tf.items() if w.startswith(t)) * 0.5      # prefiks gir norsk bøying litt uttelling
            if f:
                idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
                s += idf * (f * 2.2) / (f + 1.2 * (0.25 + 0.75 * L / (avg / 5.5)))
        if s > 0:
            scored.append((s, r))
    scored.sort(key=lambda x: -x[0])
    return [{"path": r["path"], "pos": r["pos"], "score": round(s, 3), "text": r["text"]} for s, r in scored[:k]]


@router.post("/api/knowledge/index")
def api_kindex():
    from . import tools
    return index_folders(tools.get_roots())


@router.get("/api/knowledge/status")
def api_kstatus():
    ensure()
    with db.conn() as c:
        return {"files": c.execute("SELECT COUNT(*) FROM kdocs").fetchone()[0], "chunks": c.execute("SELECT COUNT(*) FROM kchunks").fetchone()[0]}


@router.get("/api/knowledge/search")
def api_ksearch(q: str = "", k: int = 5):
    return [{**r, "text": r["text"][:600]} for r in knowledge_search(q, max(1, min(k, 10)))]


@router.delete("/api/knowledge")
def api_kclear():
    ensure()
    with db.conn() as c:
        c.execute("DELETE FROM kdocs")
    return {"ok": True}
