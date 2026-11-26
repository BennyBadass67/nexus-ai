import json, os, sys, tempfile
os.environ["NEXUS_DB"] = os.path.join(tempfile.mkdtemp(), "t.db")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from fastapi.testclient import TestClient
from app import library
from app.main import app

F = os.path.join(os.path.dirname(__file__), "fixtures")
c = TestClient(app)

def test_parse_search():
    r = library.parse_search(open(f"{F}/search.html").read())
    assert len(r) >= 10 and all(m["name"] for m in r)
    assert any(m["description"] for m in r) and any(m["sizes"] for m in r)
    assert any(m["downloads"] > 0 for m in r)

def test_parse_tags():
    t = library.parse_tags(open(f"{F}/tags.html").read(), "qwen2.5")
    d = {x["tag"]: x["size_gb"] for x in t}
    assert d["qwen2.5:3b"] == 1.9 and "qwen2.5:0.5b" in d and len(d) > 5

def test_pull_progress_and_error():
    ev = [json.loads(l) for l in c.post("/api/models/pull", json={"name": "foo:1b"}).text.splitlines()]
    assert ev[0]["type"] == "progress" and ev[-1]["type"] == "done"
    assert any(e.get("completed") == 100 for e in ev)
    ev = [json.loads(l) for l in c.post("/api/models/pull", json={"name": "nope:1"}).text.splitlines()]
    assert any(e["type"] == "error" and "manifest" in e["message"] for e in ev)

def test_pull_validation():
    assert c.post("/api/models/pull", json={"name": "a b; rm -rf"}).status_code == 422

def test_delete():
    assert c.delete("/api/models/mock:1b").status_code == 200
    assert c.delete("/api/models/finnes:ikke").status_code == 404

def test_live_library():
    r = c.get("/api/library", params={"q": "qwen"}).json()
    if r["ok"]:
        assert len(r["models"]) > 3
        t = c.get("/api/library/qwen2.5/tags").json()
        assert t["ok"] and len(t["tags"]) > 3

if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f(); print("OK", n)
