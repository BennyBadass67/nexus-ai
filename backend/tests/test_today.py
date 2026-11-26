import os, sys, tempfile
os.environ["NEXUS_DB"] = os.path.join(tempfile.mkdtemp(), "t.db")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import time
from fastapi.testclient import TestClient
from app import cloud, db
from app.main import app

client = TestClient(app)


def test_empty_today():
    r = client.get("/api/today?date=2020-06-15").json()
    assert r["date"] == "2020-06-15" and r["tasks_overdue"] == [] and r["tasks_today"] == []


def test_tasks_cards_quota_and_last_chat():
    client.post("/api/notes", json={"text": "Gammel", "due": "2020-06-10"})
    client.post("/api/notes", json={"text": "I dag", "due": "2020-06-15"})
    client.post("/api/notes", json={"text": "Senere", "due": "2020-06-20"})
    nid = client.post("/api/notes", json={"text": "Ferdig", "due": "2020-06-11"}).json()["id"]
    client.patch(f"/api/notes/{nid}", json={"done": True})
    with db.conn() as c:
        did = c.execute("INSERT INTO decks(title,created_at) VALUES('D',?)", (time.time(),)).lastrowid
        for i in range(3):
            c.execute("INSERT INTO cards(deck_id,front,back,due) VALUES(?,?,?,?)", (did, "a?", "b", 0 if i < 2 else time.time() + 99999))
    pid = client.post("/api/projects", json={"name": "P"}).json()["id"]
    cid = client.post("/api/chat", json={"message": "hei", "model": "m", "project_id": pid}).text and client.get("/api/conversations").json()[0]["id"]
    cloud._bump("cloudflare"); cloud._add_usage("cloudflare", "@cf/meta/llama-3.1-8b-instruct-fp8-fast", 1000, 1000)
    client.put("/api/cloud/providers/cloudflare", json={"api_key": "k" * 12, "account_id": "0" * 32})
    client.put("/api/cloud/providers/cloudflare", json={"enabled": True, "consent": True})
    r = client.get("/api/today?date=2020-06-15").json()
    assert r["tasks_open"] >= 3 and "Ferdig" not in str(r["tasks_overdue"])      # ferdige oppgaver telles ikke
    assert [n["text"] for n in r["tasks_overdue"]] == ["Gammel"] and [n["text"] for n in r["tasks_today"]] == ["I dag"]
    assert r["cards_due"] >= 2 and r["cards_total"] >= 3
    assert r["quota"][0]["id"] == "cloudflare" and r["quota"][0]["remaining"] < 10000
    assert r["last_chat"]["project"] == "P"
    assert client.get("/api/today?date=junk").json()["date"] != "junk"
    client.put("/api/cloud/providers/cloudflare", json={"enabled": False})
