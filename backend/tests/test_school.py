import os, sys, tempfile
os.environ["NEXUS_DB"] = os.path.join(tempfile.mkdtemp(), "s.db")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import time
from datetime import date, timedelta
from fastapi.testclient import TestClient
from app import db, school
from app.main import app

client = TestClient(app)


def card():
    with db.conn() as c:
        did = c.execute("INSERT INTO decks(title,created_at) VALUES('D',?)", (time.time(),)).lastrowid
        return c.execute("INSERT INTO cards(deck_id,front,back,due) VALUES(?,?,?,0)", (did, "a?", "b")).lastrowid


def test_review_is_logged_and_stats():
    base = client.get("/api/study/stats").json()
    cid = card()
    client.post(f"/api/study/cards/{cid}/review", json={"grade": 2})
    client.post(f"/api/study/cards/{cid}/review", json={"grade": 0})
    s = client.get("/api/study/stats").json()
    assert s["today"] == base["today"] + 2 and s["streak"] >= 1 and s["total"] == base["total"] + 2
    assert s["last7"][-1]["n"] == s["today"] and len(s["last7"]) == 7 and 0 <= s["good_pct_7d"] <= 100


def test_streak_logic():
    with db.conn() as c:
        c.execute("DELETE FROM reviewlog")
        for day in ("2031-03-01", "2031-03-02", "2031-03-03", "2031-02-27"):
            c.execute("INSERT INTO reviewlog(ts,day,grade) VALUES(0,?,2)", (day,))
    assert client.get("/api/study/stats?date=2031-03-03").json()["streak"] == 3
    assert client.get("/api/study/stats?date=2031-03-04").json()["streak"] == 3      # i dag ikke øvd ennå: rekken lever
    assert client.get("/api/study/stats?date=2031-03-05").json()["streak"] == 0      # hull
    assert client.get("/api/study/stats?date=2031-03-01").json()["streak"] == 1     # 28. feb mangler


def test_build_plan_rules():
    start, exam = date(2031, 5, 1), date(2031, 5, 11)
    topics = ["Brøk", "Likninger", "Geometri", "Funksjoner"]
    items = school.build_plan(topics, start, exam, "Matte")
    assert all(start.isoformat() <= i["due"] < exam.isoformat() for i in items)
    for t in topics:
        assert any(f"Les og lag kort: {t}" in i["text"] for i in items)
    assert items[-1]["due"] == "2031-05-10" and "Repeter alt" in items[-1]["text"]
    assert items[0]["text"].startswith("Matte: ")
    per_day = {}
    for i in items:
        per_day[i["due"]] = per_day.get(i["due"], 0) + 1
    assert max(per_day.values()) <= 3
    one = school.build_plan(["A", "B", "C"], date(2031, 5, 1), date(2031, 5, 2))        # bare én dag: alt havner der
    assert {i["due"] for i in one} == {"2031-05-01"}


def test_plan_endpoint_preview_commit_and_errors():
    body = {"topics": ["Brøk", "Likninger"], "exam_date": "2031-06-10", "start_date": "2031-06-01", "subject": "Mat"}
    pv = client.post("/api/study/plan", json=body).json()
    assert pv["added"] == 0 and len(pv["items"]) >= 3
    r = client.post("/api/study/plan", json={**body, "commit": True}).json()
    assert r["added"] == len(pv["items"])
    notes = [n for n in client.get("/api/notes").json() if n["source"] == "plan"]
    assert len(notes) == r["added"] and all(n["due"] for n in notes)
    assert client.post("/api/study/plan", json={**body, "commit": True}).json()["added"] == 0      # ingen duplikater
    assert client.post("/api/study/plan", json={**body, "exam_date": "2031-05-01"}).status_code == 422
    assert client.post("/api/study/plan", json={**body, "exam_date": "i morgen"}).status_code == 422
    assert client.post("/api/study/plan", json={"topics": [], "exam_date": "2031-06-10"}).status_code == 422
