"""v1.8: Studiestatistikk (rekke, repetisjoner) og Studieplan (fordeler emner over dagene frem til prøven, med repetisjon)."""
import re
from datetime import date as _date, datetime, timedelta

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import db, extras

router = APIRouter()
db.init()
with db.conn() as _c:
    _c.executescript("""CREATE TABLE IF NOT EXISTS reviewlog (id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, day TEXT NOT NULL, grade INTEGER NOT NULL);
                        CREATE INDEX IF NOT EXISTS reviewlog_day ON reviewlog(day);""")

DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def local_day(ts: float | None = None) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d") if ts else datetime.now().strftime("%Y-%m-%d")


def log_review(grade: int) -> None:
    import time
    with db.conn() as c:
        c.execute("INSERT INTO reviewlog(ts,day,grade) VALUES(?,?,?)", (time.time(), local_day(), grade))


def _d(s: str) -> _date:
    return datetime.strptime(s, "%Y-%m-%d").date()


@router.get("/api/study/stats")
def stats(date: str | None = None):
    today = date if date and DATE_RE.fullmatch(date) else local_day()
    with db.conn() as c:
        rows = c.execute("SELECT day, COUNT(*) AS n, SUM(CASE WHEN grade>=2 THEN 1 ELSE 0 END) AS good FROM reviewlog GROUP BY day").fetchall()
    per = {r["day"]: (r["n"], r["good"] or 0) for r in rows}
    t = _d(today)
    streak, d = 0, t if today in per else t - timedelta(days=1)    # i dag uten øving bryter ikke rekken før dagen er over
    while d.strftime("%Y-%m-%d") in per:
        streak += 1; d -= timedelta(days=1)
    last7 = [{"day": (t - timedelta(days=i)).strftime("%Y-%m-%d"), "n": per.get((t - timedelta(days=i)).strftime("%Y-%m-%d"), (0, 0))[0]} for i in range(6, -1, -1)]
    n7 = sum(x["n"] for x in last7); g7 = sum(per.get(x["day"], (0, 0))[1] for x in last7)
    return {"today": per.get(today, (0, 0))[0], "streak": streak, "last7": last7, "total": sum(v[0] for v in per.values()),
            "good_pct_7d": round(100 * g7 / n7) if n7 else None}


class PlanIn(BaseModel):
    topics: list[str] = Field(min_length=1, max_length=30)
    exam_date: str
    start_date: str | None = None
    subject: str = Field(default="", max_length=60)
    commit: bool = False


def build_plan(topics: list[str], start: _date, exam: _date, subject: str = "") -> list[dict]:
    """Ren logikk. Hvert emne: 'Les' en dag, 'Repeter' 2 dager senere (hvis det er tid). Siste dag før prøven: repetisjon av alt.
    Emnene fordeles jevnt, og hver dag får maks 2 oppgaver."""
    days = (exam - start).days          # dager fra start til dagen før prøven er start..exam-1
    if days < 1:
        raise ValueError("Prøvedatoen må være etter startdatoen.")
    pre = f"{subject}: " if subject else ""
    topics = [t.strip() for t in topics if t.strip()]
    last = exam - timedelta(days=1)
    read_days = max(1, days - 1) if days > 1 else 1
    plan: dict[_date, list[str]] = {}
    for i, t in enumerate(topics):
        off = int(i * read_days / len(topics))
        d = start + timedelta(days=off)
        plan.setdefault(d, []).append(f"{pre}Les og lag kort: {t}")
        r = d + timedelta(days=2)
        if r < last:
            plan.setdefault(r, []).append(f"{pre}Repeter: {t}")
    plan.setdefault(last, []).append(f"{pre}Repeter alt fra start til slutt, øv på alle kortene")
    out = []
    for d in sorted(plan):
        for task in plan[d][:3]:
            out.append({"due": d.strftime("%Y-%m-%d"), "text": task})
    return out


@router.post("/api/study/plan")
def plan(b: PlanIn):
    if not DATE_RE.fullmatch(b.exam_date) or (b.start_date and not DATE_RE.fullmatch(b.start_date)):
        raise HTTPException(422, "Dato må være på formen ÅÅÅÅ-MM-DD.")
    try:
        start = _d(b.start_date) if b.start_date else _d(local_day())
        items = build_plan(b.topics, start, _d(b.exam_date), b.subject.strip())
    except ValueError as e:
        raise HTTPException(422, str(e))
    added = 0
    if b.commit:
        for it in items:
            if not extras.add_note(it["text"], it["due"], source="plan")["duplicate"]:
                added += 1
    return {"items": items, "added": added}


@router.get("/api/study/weak")
def weak_quiz(n: int = 10):
    """Flervalgsquiz på tvers av alle stokker, med kortene du sliter mest med først (flest feil, lavest «ease»).
    Feil svaralternativer hentes fra andre kort. Trenger minst 4 kort totalt."""
    import random
    n = max(1, min(n, 30))
    with db.conn() as c:
        rows = [dict(r) for r in c.execute(
            "SELECT c.id, c.front, c.back, c.lapses, c.ease, c.reps, d.title AS deck FROM cards c JOIN decks d ON d.id=c.deck_id").fetchall()]
    if len(rows) < 4:
        raise HTTPException(422, "Trenger minst 4 kort totalt for å lage en quiz.")
    random.shuffle(rows)                                   # jevn fordeling blant like svake kort
    rows.sort(key=lambda r: (-(r["lapses"] or 0), r["ease"] if r["ease"] else 2.5))
    pool = list({r["back"].strip().lower(): r["back"] for r in rows}.values())
    qs = []
    for r in rows[:n]:
        others = [b for b in pool if b.strip().lower() != r["back"].strip().lower()]
        random.shuffle(others)
        opts = others[:3] + [r["back"]]
        if len(opts) < 2:
            continue
        random.shuffle(opts)
        qs.append({"card_id": r["id"], "question": r["front"], "options": opts, "answer": opts.index(r["back"]),
                   "deck": r["deck"], "lapses": r["lapses"] or 0})
    return qs
