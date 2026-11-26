"""Kjør: python -m pytest tests  (eller python tests/test_chat.py). Krever mock/ekte Ollama på OLLAMA_URL."""
import json, os, sys, tempfile
os.environ["NEXUS_DB"] = os.path.join(tempfile.mkdtemp(), "t.db")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from fastapi.testclient import TestClient
from app.main import app

MODEL = os.environ.get("TEST_MODEL", "mock:1b")
c = TestClient(app)

def events(r): return [json.loads(l) for l in r.text.splitlines() if l.strip()]

def test_health_and_models():
    h = c.get("/api/health").json()
    assert h["backend"] == "ok" and h["ollama_online"] is True
    m = c.get("/api/models").json()
    assert m["online"] and any(x["name"] == MODEL for x in m["models"])

def test_chat_persists_and_continues():
    ev = events(c.post("/api/chat", json={"message": "hallo", "model": MODEL}))
    assert ev[0]["type"] == "meta" and ev[-1]["type"] == "done"
    text = "".join(e["text"] for e in ev if e["type"] == "token")
    assert text.strip()
    cid = ev[0]["conversation_id"]
    ev2 = events(c.post("/api/chat", json={"message": "mer", "model": MODEL, "conversation_id": cid}))
    assert ev2[0]["conversation_id"] == cid
    conv = c.get(f"/api/conversations/{cid}").json()
    assert [m["role"] for m in conv["messages"]] == ["user", "assistant", "user", "assistant"]
    assert conv["messages"][1]["model"] == MODEL

def test_unknown_model_gives_error_event():
    ev = events(c.post("/api/chat", json={"message": "x", "model": "finnes-ikke:1"}))
    assert any(e["type"] == "error" for e in ev)

def test_rename_delete():
    cid = events(c.post("/api/chat", json={"message": "slett meg", "model": MODEL}))[0]["conversation_id"]
    assert c.patch(f"/api/conversations/{cid}", json={"title": "Nytt"}).status_code == 200
    assert c.delete(f"/api/conversations/{cid}").status_code == 200
    assert c.get(f"/api/conversations/{cid}").status_code == 404

def test_regenerate_replaces_last_answer():
    ev = events(c.post("/api/chat", json={"message": "regen", "model": MODEL}))
    cid = ev[0]["conversation_id"]
    events(c.post("/api/chat", json={"message": "regen", "model": MODEL, "conversation_id": cid, "regenerate": True}))
    conv = c.get(f"/api/conversations/{cid}").json()
    assert [m["role"] for m in conv["messages"]] == ["user", "assistant"]

def test_validation():
    assert c.post("/api/chat", json={"message": "", "model": MODEL}).status_code == 422

if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f(); print("OK", n)
