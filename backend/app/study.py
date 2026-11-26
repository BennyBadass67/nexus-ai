"""v1.1: Studie (kort + quiz fra egen tekst, repetisjon) og Skriveverktøy (oppsummer, rett, oversett, forenkle).
Alt går mot den lokale modellen. Ingen nye pakker."""
import json

import httpx
import re
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from . import db, ollama, tools

router = APIRouter()

SCHEMA = """
CREATE TABLE IF NOT EXISTS decks (
  id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS cards (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  deck_id INTEGER NOT NULL REFERENCES decks(id) ON DELETE CASCADE,
  front TEXT NOT NULL, back TEXT NOT NULL,
  ease REAL NOT NULL DEFAULT 2.5, interval REAL NOT NULL DEFAULT 0,
  reps INTEGER NOT NULL DEFAULT 0, lapses INTEGER NOT NULL DEFAULT 0,
  due REAL NOT NULL DEFAULT 0
);
"""
with db.conn() as _c:
    _c.executescript(SCHEMA)

DAY = 86400.0
MAX_SRC = 5000          # tegn per modellkall: passer 4096-konteksten
MAX_TEXT = 60000


class GenIn(BaseModel):
    model: str = Field(min_length=1)
    title: str = Field(default="", max_length=120)
    text: str = ""
    note_id: int | None = None
    path: str | None = None
    n: int = Field(default=8, ge=1, le=20)
    deck_id: int | None = None


def source_text(g: GenIn) -> tuple[str, str]:
    if g.text.strip():
        return g.text.strip(), g.title or "Egen tekst"
    if g.note_id is not None:
        with db.conn() as c:
            r = c.execute("SELECT text FROM notes WHERE id=?", (g.note_id,)).fetchone()
        if not r:
            raise HTTPException(404, "Notatet finnes ikke")
        return r["text"], g.title or "Notat"
    if g.path:
        try:
            p = tools.resolve_safe(g.path)
            return p.read_text("utf-8", errors="replace"), g.title or p.name
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(400, f"Kan ikke lese filen: {e}")
    raise HTTPException(422, "Gi tekst, et notat eller en fil")


def chunks(text: str, size: int = MAX_SRC) -> list[str]:
    text = text.strip()[:MAX_TEXT]
    out, cur = [], ""
    for para in re.split(r"\n\s*\n", text):
        if len(cur) + len(para) > size and cur:
            out.append(cur); cur = ""
        while len(para) > size:
            out.append(para[:size]); para = para[size:]
        cur += para + "\n\n"
    if cur.strip():
        out.append(cur)
    return out


def parse_cards(raw: str) -> list[dict]:
    """Tåler {"cards":[...]}, ren liste, og andre nøkkelnavn (question/answer, spørsmål/svar)."""
    try:
        d = json.loads(raw)
    except Exception:
        m = re.search(r"[\[{].*[\]}]", raw, re.S)
        if not m:
            return []
        try:
            d = json.loads(m.group(0))
        except Exception:
            return []
    if isinstance(d, dict):
        lst = next((v for v in d.values() if isinstance(v, list)), [])
    else:
        lst = d
    out = []
    for x in lst:
        if not isinstance(x, dict):
            continue
        low = {str(k).lower(): v for k, v in x.items()}
        f = next((low[k] for k in ("front", "question", "spørsmål", "q", "term") if k in low), None)
        b = next((low[k] for k in ("back", "answer", "svar", "a", "definition") if k in low), None)
        if isinstance(f, str) and isinstance(b, str) and f.strip() and b.strip():
            out.append({"front": f.strip()[:400], "back": b.strip()[:800]})
    return out


PROMPT = ("Lag {n} studiekort på norsk fra teksten under. 'front' er et SPØRSMÅL som slutter på ?. 'back' er et kort svar (noen få ord eller én setning) "
          "som bare bygger på teksten. Spørsmålet må være annerledes enn svaret: ikke kopier setninger fra teksten som spørsmål.\n"
          "Eksempel på tekst: «Oslo har blitt hovedstad i 1814.» gir kortet "
          "{{\"front\":\"Når ble Oslo hovedstad?\",\"back\":\"I 1814.\"}}\n"
          "Svar KUN med JSON: {{\"cards\":[{{\"front\":\"...?\",\"back\":\"...\"}}]}}\n\nTEKST:\n{t}")


def good_card(c: dict) -> bool:
    """Små modeller kopierer ofte setningen som både spørsmål og svar. Slike kort er verdiløse."""
    f, b = c["front"].lower().strip(" ?.!"), c["back"].lower().strip(" ?.!")
    if f == b or f in b or b in f and len(b) > 25:
        return False
    return "?" in c["front"]


@router.post("/api/study/generate")
async def generate(g: GenIn):
    text, title = source_text(g)
    if len(text) < 40:
        raise HTTPException(422, "For lite tekst til å lage kort av (minst ca. 40 tegn).")
    parts = chunks(text)
    per = max(1, round(g.n / len(parts)))
    cards, seen = [], set()
    for part in parts:
        got = 0
        for attempt in range(2):                     # små modeller bommer ofte: ett forsøk til hvis det ble for få
            if len(cards) >= g.n or got >= per:
                break
            try:
                raw = await ollama.chat_json(g.model, [{"role": "user", "content": PROMPT.format(n=per, t=part)}])
            except RuntimeError as e:
                raise HTTPException(502, "Modellen feilet: " + str(e))
            except httpx.HTTPError:
                raise HTTPException(503, "Ollama svarer ikke. Start Ollama først.")
            for c in filter(good_card, parse_cards(raw)):
                k = c["front"].lower()
                if k not in seen and len(cards) < g.n:
                    seen.add(k); cards.append(c); got += 1
    if not cards:
        raise HTTPException(422, f"Modellen ({g.model}) ga ingen brukbare kort. Prøv kortere tekst eller en større modell.")
    now = time.time()
    with db.conn() as c:
        did = g.deck_id
        if did is None:
            did = c.execute("INSERT INTO decks(title,created_at) VALUES(?,?)", (title[:120], now)).lastrowid
        elif not c.execute("SELECT 1 FROM decks WHERE id=?", (did,)).fetchone():
            raise HTTPException(404, "Stokken finnes ikke")
        for k in cards:
            c.execute("INSERT INTO cards(deck_id,front,back,due) VALUES(?,?,?,?)", (did, k["front"], k["back"], now))
    return {"deck_id": did, "added": len(cards), "cards": cards}


@router.get("/api/study/decks")
def decks():
    now = time.time()
    with db.conn() as c:
        rows = c.execute("""SELECT d.id, d.title, d.created_at, COUNT(k.id) AS total,
            COALESCE(SUM(CASE WHEN k.due<=? THEN 1 ELSE 0 END),0) AS due,
            COALESCE(SUM(CASE WHEN k.reps>=3 AND k.interval>=6 THEN 1 ELSE 0 END),0) AS learned
            FROM decks d LEFT JOIN cards k ON k.deck_id=d.id GROUP BY d.id ORDER BY d.created_at DESC""", (now,)).fetchall()
    return [dict(r) for r in rows]


@router.get("/api/study/decks/{did}/cards")
def deck_cards(did: int, due: bool = False):
    with db.conn() as c:
        if not c.execute("SELECT 1 FROM decks WHERE id=?", (did,)).fetchone():
            raise HTTPException(404, "Stokken finnes ikke")
        q = "SELECT * FROM cards WHERE deck_id=?" + (" AND due<=?" if due else "") + " ORDER BY due, id"
        rows = c.execute(q, (did, time.time()) if due else (did,)).fetchall()
    return [dict(r) for r in rows]


@router.get("/api/study/decks/{did}/quiz")
def deck_quiz(did: int, n: int = 10):
    """Flervalgsquiz uten modell: feil svar hentes fra andre kort i samme stokk. Trenger minst 3 kort."""
    import random
    with db.conn() as c:
        if not c.execute("SELECT 1 FROM decks WHERE id=?", (did,)).fetchone():
            raise HTTPException(404, "Stokken finnes ikke")
        rows = [dict(r) for r in c.execute("SELECT id, front, back FROM cards WHERE deck_id=?", (did,)).fetchall()]
    if len(rows) < 3:
        raise HTTPException(422, "Quiz trenger minst 3 kort i stokken.")
    random.shuffle(rows)
    qs = []
    for r in rows[:max(1, min(n, 30))]:
        others = list({o["back"] for o in rows if o["back"].strip().lower() != r["back"].strip().lower()})
        random.shuffle(others)
        opts = others[:3] + [r["back"]]
        random.shuffle(opts)
        qs.append({"card_id": r["id"], "question": r["front"], "options": opts, "answer": opts.index(r["back"])})
    return qs


@router.delete("/api/study/decks/{did}")
def del_deck(did: int):
    with db.conn() as c:
        c.execute("DELETE FROM cards WHERE deck_id=?", (did,))
        c.execute("DELETE FROM decks WHERE id=?", (did,))
    return {"ok": True}


class CardIn(BaseModel):
    front: str = Field(min_length=1, max_length=400)
    back: str = Field(min_length=1, max_length=800)


@router.post("/api/study/decks/{did}/cards")
def add_card(did: int, b: CardIn):
    with db.conn() as c:
        if not c.execute("SELECT 1 FROM decks WHERE id=?", (did,)).fetchone():
            raise HTTPException(404, "Stokken finnes ikke")
        i = c.execute("INSERT INTO cards(deck_id,front,back,due) VALUES(?,?,?,?)", (did, b.front.strip(), b.back.strip(), time.time())).lastrowid
    return {"id": i}


@router.delete("/api/study/cards/{cid}")
def del_card(cid: int):
    with db.conn() as c:
        c.execute("DELETE FROM cards WHERE id=?", (cid,))
    return {"ok": True}


def schedule(ease: float, interval: float, reps: int, lapses: int, grade: int) -> tuple[float, float, int, int]:
    """SM-2 i enkel form. grade: 0=Igjen, 1=Vanskelig, 2=Bra, 3=Lett. interval i dager."""
    if grade == 0:
        return max(1.3, ease - 0.2), 0.0, 0, lapses + 1       # ny runde om ~10 min
    if reps == 0:
        interval = 1.0 if grade < 3 else 3.0
    elif reps == 1:
        interval = 3.0 if grade < 3 else 6.0
    else:
        mult = {1: 1.2, 2: ease, 3: ease * 1.3}[grade]
        interval = max(interval + 1, interval * mult)
    ease = max(1.3, ease + {1: -0.15, 2: 0.0, 3: 0.15}[grade])
    return ease, round(interval, 2), reps + 1, lapses


class ReviewIn(BaseModel):
    grade: int = Field(ge=0, le=3)


@router.post("/api/study/cards/{cid}/review")
def review(cid: int, b: ReviewIn):
    with db.conn() as c:
        k = c.execute("SELECT * FROM cards WHERE id=?", (cid,)).fetchone()
        if not k:
            raise HTTPException(404, "Kortet finnes ikke")
        ease, iv, reps, lap = schedule(k["ease"], k["interval"], k["reps"], k["lapses"], b.grade)
        due = time.time() + (600 if b.grade == 0 else iv * DAY)
        c.execute("UPDATE cards SET ease=?,interval=?,reps=?,lapses=?,due=? WHERE id=?", (ease, iv, reps, lap, due, cid))
    from . import school
    school.log_review(b.grade)
    return {"interval_days": iv, "due": due, "ease": ease}


# ---------- Skriveverktøy ----------
ACTIONS = {
    "summarize": "Oppsummer teksten kort og presist på samme språk som teksten. Bare oppsummeringen.",
    "bullets": "Gjør teksten om til korte punkter (maks 8). Bare punktene.",
    "fix": "Rett stave- og grammatikkfeil i teksten uten å endre meningen eller stilen. Svar bare med den rettede teksten.",
    "simplify": "Skriv teksten om så den er lett å forstå for en 12-åring. Svar bare med den nye teksten.",
    "formal": "Skriv teksten om i en høflig, formell tone. Svar bare med den nye teksten.",
    "to_en": "Oversett teksten til engelsk. Svar bare med oversettelsen.",
    "to_no": "Oversett teksten til norsk bokmål. Svar bare med oversettelsen.",
    "explain": "Forklar hva teksten betyr, steg for steg, på norsk.",
    "questions": "Lag 5 gode spørsmål en lærer kunne stilt om teksten, på samme språk som teksten. Bare spørsmålene.",
}


class TransformIn(BaseModel):
    model: str = Field(min_length=1)
    action: str
    text: str = Field(min_length=1, max_length=12000)


@router.get("/api/write/actions")
def write_actions():
    return list(ACTIONS)


@router.post("/api/write/transform")
async def transform(b: TransformIn):
    if b.action not in ACTIONS:
        raise HTTPException(422, "Ukjent handling")
    msgs = [{"role": "system", "content": ACTIONS[b.action]}, {"role": "user", "content": b.text}]

    async def gen():
        try:
            async for kind, val in ollama.chat_stream(b.model, msgs):
                if kind == "token":
                    yield val
        except Exception as e:
            yield "\n\n[Feil: " + str(e) + "]"
    return StreamingResponse(gen(), media_type="text/plain; charset=utf-8")


# ---------- Spør dokumentene dine (RAG) ----------
class AskIn(BaseModel):
    model: str = Field(min_length=1)
    q: str = Field(min_length=2, max_length=500)


@router.post("/api/knowledge/ask")
async def ask(b: AskIn):
    from . import extras
    hits = extras.knowledge_search(b.q, 4)
    srcs = list(dict.fromkeys(h["path"] for h in hits))
    headers = {"X-Sources": json.dumps(srcs)}
    if not hits:
        return StreamingResponse(iter(["Fant ikke noe om dette i dokumentene dine. Oppdater indeksen eller prøv andre ord."]),
                                 media_type="text/plain; charset=utf-8", headers=headers)
    ctx = "\n\n".join(f"[{i + 1}] ({Path(h['path']).name})\n{h['text'][:1200]}" for i, h in enumerate(hits))
    sysm = ("Svar på spørsmålet KUN ut fra utdragene under. Hvis svaret ikke står der, si at du ikke finner det i dokumentene. "
            "Svar kort, på samme språk som spørsmålet, og vis til kilde som [1], [2].\n\nUTDRAG:\n" + ctx)
    msgs = [{"role": "system", "content": sysm}, {"role": "user", "content": b.q}]

    async def gen():
        try:
            async for kind, val in ollama.chat_stream(b.model, msgs):
                if kind == "token":
                    yield val
        except Exception as e:
            yield "\n\n[Feil: " + str(e) + "]"
    return StreamingResponse(gen(), media_type="text/plain; charset=utf-8", headers=headers)


# ---------- Smart chat: auto-tittel og oppfølgingsforslag ----------
class ModelIn(BaseModel):
    model: str = Field(min_length=1)


def _conv_text(cid: int, limit: int = 4) -> tuple[str, str]:
    with db.conn() as c:
        conv = c.execute("SELECT title FROM conversations WHERE id=?", (cid,)).fetchone()
        if not conv:
            raise HTTPException(404, "Samtalen finnes ikke")
        rows = c.execute("SELECT role,content FROM messages WHERE conversation_id=? AND role IN ('user','assistant') "
                         "ORDER BY id LIMIT ?", (cid, limit)).fetchall()
    return conv["title"], "\n".join(f"{r['role']}: {r['content'][:600]}" for r in rows)


def clean_title(t: str) -> str:
    t = re.sub(r"[\"“”«»*#`]", "", t.strip().splitlines()[0] if t.strip() else "")
    t = re.sub(r"^(tittel|title)\s*:\s*", "", t, flags=re.I).strip(" .:-")
    return t[:48]


@router.post("/api/conversations/{cid}/autotitle")
async def autotitle(cid: int, b: ModelIn):
    old, text = _conv_text(cid)
    if not text:
        raise HTTPException(422, "Samtalen er tom")
    first = text.split("\n", 1)[0].removeprefix("user: ").replace("\n", " ")[:48]
    if old.strip() != first.strip():                    # brukeren har gitt navn selv: ikke rør
        return {"title": old, "changed": False}
    sysm = "Lag en kort tittel (2 til 5 ord) for samtalen under, på samme språk som brukeren. Svar KUN med tittelen, uten anførselstegn."
    out = ""
    try:
        async for kind, val in ollama.chat_stream(b.model, [{"role": "system", "content": sysm}, {"role": "user", "content": text}]):
            if kind == "token":
                out += val
                if len(out) > 120:
                    break
    except Exception:
        return {"title": old, "changed": False}
    t = clean_title(out)
    if len(t) < 3:
        return {"title": old, "changed": False}
    with db.conn() as c:
        c.execute("UPDATE conversations SET title=? WHERE id=?", (t, cid))
    return {"title": t, "changed": True}


@router.post("/api/conversations/{cid}/suggest")
async def suggest(cid: int, b: ModelIn):
    _, text = _conv_text(cid, 8)
    if not text:
        raise HTTPException(422, "Samtalen er tom")
    sysm = ("Foreslå 3 korte oppfølgingsspørsmål brukeren kan stille videre, på samme språk som samtalen. "
            "Svar KUN med JSON: {\"suggestions\":[\"...?\",\"...?\",\"...?\"]}")
    try:
        raw = await ollama.chat_json(b.model, [{"role": "system", "content": sysm}, {"role": "user", "content": text}])
    except RuntimeError as e:
        raise HTTPException(502, "Modellen feilet: " + str(e))
    except httpx.HTTPError:
        raise HTTPException(503, "Ollama svarer ikke. Start Ollama først.")
    try:
        d = json.loads(raw)
        lst = d if isinstance(d, list) else next((v for v in d.values() if isinstance(v, list)), [])
    except Exception:
        lst = []
    out = []
    for x in lst:
        if isinstance(x, dict):
            x = next((v for v in x.values() if isinstance(v, str)), "")
        if isinstance(x, str) and 3 <= len(x.strip()) <= 140 and x.strip() not in out:
            out.append(x.strip())
    return {"suggestions": out[:3]}


# ---------- Modellduell: samme spørsmål til en valgt modell, strømmet som ren tekst ----------
class CompleteIn(BaseModel):
    model: str = Field(min_length=1)
    prompt: str = Field(min_length=1, max_length=4000)


@router.post("/api/complete")
async def complete(b: CompleteIn):
    async def gen():
        try:
            async for kind, val in ollama.chat_stream(b.model, [{"role": "user", "content": b.prompt}]):
                if kind == "token":
                    yield val
        except Exception as e:
            yield "\n\n[Feil: " + str(e) + "]"
    return StreamingResponse(gen(), media_type="text/plain; charset=utf-8")
