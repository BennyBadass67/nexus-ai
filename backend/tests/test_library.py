import re
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


def _lib():
    return library.parse_search(open(f"{F}/library.html").read())


def test_parse_full_library_page():
    r = _lib()
    assert len(r) >= 100 and all(m["name"] and m["description"] for m in r)
    assert any(m["pulls"] > 1_000_000 for m in r)
    assert any("vision" in m["capabilities"] for m in r)


def test_categories_come_from_registry_data():
    r = _lib()
    cats = {m["name"]: library.categorize(m) for m in r}
    coders = [n for n, c in cats.items() if "koding" in c]
    assert coders and all(re.search(r"cod|dev|program", (n + next(m["description"] for m in r if m["name"] == n)).lower()) for n in coders)
    assert all("bilde" in cats[m["name"]] for m in r if "vision" in m["capabilities"])
    assert all(cats[m["name"]] == ["embedding"] for m in r if "embedding" in m["capabilities"])
    assert any("liten" in c for c in cats.values())
    assert library.categorize({"name": "x", "description": "A coding model", "capabilities": [], "sizes": ["70b"]}) == ["chat", "koding"]
    assert "liten" not in library.categorize({"name": "x", "description": "", "capabilities": [], "sizes": ["8b", "70b"]})


def test_library_endpoint_has_categories_counts_and_fits(monkeypatch):
    async def fake(q=""):
        return [dict(m) for m in _lib()[:40]]
    monkeypatch.setattr(library, "browse", fake)
    j = c.get("/api/library").json()
    assert j["ok"] and len(j["models"]) == 40 and j["source"] == "ollama.com/library"
    assert all("categories" in m and "fits" in m for m in j["models"])
    tot = {x["id"]: x["count"] for x in j["categories"]}
    assert tot["bilde"] == sum(1 for m in j["models"] if "bilde" in m["categories"])
    assert isinstance(j["fits_count"], int)


def test_installed_list_is_live_from_ollama_each_call(monkeypatch):
    from app import ollama
    state = {"items": [{"name": "a:1b", "size": 1}]}
    async def tags(): return state["items"]
    monkeypatch.setattr(ollama, "tags", tags)
    assert [m["name"] for m in c.get("/api/models").json()["models"]] == ["a:1b"]
    state["items"] = [{"name": "b:2b", "size": 2}]       # a slettet, b ny
    assert [m["name"] for m in c.get("/api/models").json()["models"]] == ["b:2b"]
