import os, sys, tempfile
os.environ["NEXUS_DB"] = os.path.join(tempfile.mkdtemp(), "p.db")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import json
from fastapi.testclient import TestClient
from app import ollama
from app.main import app

client = TestClient(app)
SEEN = []


def fake_stream():
    async def f(model, messages, *a, **k):
        SEEN.append(messages)
        yield "token", "ok"
    return f


def test_project_crud_and_assign(monkeypatch):
    monkeypatch.setattr(ollama, "chat_stream", fake_stream())
    pid = client.post("/api/projects", json={"name": "Matte", "instructions": "Svar alltid med et eksempel."}).json()["id"]
    assert client.post("/api/projects", json={"name": ""}).status_code == 422
    r = client.post("/api/chat", json={"message": "hei", "model": "m", "project_id": pid})
    cid = json.loads(r.text.splitlines()[0])["conversation_id"]
    assert "Matte" in SEEN[-1][0]["content"] and "Svar alltid med et eksempel." in SEEN[-1][0]["content"]
    convs = client.get("/api/conversations").json()
    assert next(c for c in convs if c["id"] == cid)["project_id"] == pid
    assert client.get("/api/projects").json()[0]["chats"] == 1
    # fortsatt med i oppfølging, og fjernes ved avtilordning
    client.post("/api/chat", json={"message": "mer", "model": "m", "conversation_id": cid})
    assert "Svar alltid med et eksempel." in SEEN[-1][0]["content"]
    assert client.put(f"/api/conversations/{cid}/project", json={"project_id": None}).status_code == 200
    client.post("/api/chat", json={"message": "igjen", "model": "m", "conversation_id": cid})
    assert "eksempel" not in SEEN[-1][0]["content"]


def test_patch_delete_keeps_chats(monkeypatch):
    monkeypatch.setattr(ollama, "chat_stream", fake_stream())
    pid = client.post("/api/projects", json={"name": "A", "instructions": "x"}).json()["id"]
    cid = json.loads(client.post("/api/chat", json={"message": "hei", "model": "m", "project_id": pid}).text.splitlines()[0])["conversation_id"]
    assert client.patch(f"/api/projects/{pid}", json={"instructions": "ny"}).status_code == 200
    client.post("/api/chat", json={"message": "x", "model": "m", "conversation_id": cid})
    assert "ny" in SEEN[-1][0]["content"]
    assert client.patch("/api/projects/9999", json={"name": "z"}).status_code == 404
    assert client.put(f"/api/conversations/{cid}/project", json={"project_id": 9999}).status_code == 404
    client.delete(f"/api/projects/{pid}")
    c = next(c for c in client.get("/api/conversations").json() if c["id"] == cid)
    assert c["project_id"] is None
