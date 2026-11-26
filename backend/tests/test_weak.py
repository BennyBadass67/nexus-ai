import os, sys, tempfile, time
os.environ["NEXUS_DB"] = os.path.join(tempfile.mkdtemp(), "w.db")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from fastapi.testclient import TestClient
from app import db
from app.main import app

client = TestClient(app)


def test_needs_four_cards(monkeypatch):
    from app import school
    real = db.conn
    class Fake:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def execute(self, *a): return self
        def fetchall(self): return []
    monkeypatch.setattr(school.db, "conn", lambda: Fake())
    assert client.get("/api/study/weak").status_code == 422


def test_weakest_first_across_decks():
    with db.conn() as c:
        a = c.execute("INSERT INTO decks(title,created_at) VALUES('A',?)", (time.time(),)).lastrowid
        b = c.execute("INSERT INTO decks(title,created_at) VALUES('B',?)", (time.time(),)).lastrowid
        for i in range(4):
            c.execute("INSERT INTO cards(deck_id,front,back,due,lapses) VALUES(?,?,?,0,0)", (a, f"A{i}?", f"a{i}"))
        c.execute("INSERT INTO cards(deck_id,front,back,due,lapses) VALUES(?,?,?,0,99)", (b, "Svak?", "svak"))
        c.execute("INSERT INTO cards(deck_id,front,back,due,lapses) VALUES(?,?,?,0,98)", (b, "Litt?", "litt"))
    qs = client.get("/api/study/weak?n=3").json()
    assert [q["question"] for q in qs[:2]] == ["Svak?", "Litt?"] and len(qs) == 3
    assert qs[0]["deck"] == "B" and qs[0]["lapses"] == 99
    for q in qs:
        assert len(set(q["options"])) == len(q["options"]) >= 4 and q["options"][q["answer"]]
    assert qs[0]["options"][qs[0]["answer"]] == "svak"
