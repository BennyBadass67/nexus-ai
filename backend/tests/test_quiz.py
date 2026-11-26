import os, sys, tempfile
os.environ["NEXUS_DB"] = os.path.join(tempfile.mkdtemp(), "q.db")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from fastapi.testclient import TestClient
from app import db
from app.main import app
import time

client = TestClient(app)


def mk(n):
    with db.conn() as c:
        did = c.execute("INSERT INTO decks(title,created_at) VALUES('T',?)", (time.time(),)).lastrowid
        for i in range(n):
            c.execute("INSERT INTO cards(deck_id,front,back,due) VALUES(?,?,?,0)", (did, f"Spm {i}?", f"Svar {i}"))
    return did


def test_quiz_options_and_answer():
    did = mk(6)
    qs = client.get(f"/api/study/decks/{did}/quiz?n=4").json()
    assert len(qs) == 4
    for q in qs:
        assert len(q["options"]) == 4 and len(set(q["options"])) == 4
        assert q["options"][q["answer"]] == "Svar " + q["question"][4:-1]


def test_quiz_needs_three_and_404():
    assert client.get(f"/api/study/decks/{mk(2)}/quiz").status_code == 422
    assert client.get("/api/study/decks/99999/quiz").status_code == 404
    assert len(client.get(f"/api/study/decks/{mk(3)}/quiz").json()[0]["options"]) == 3
