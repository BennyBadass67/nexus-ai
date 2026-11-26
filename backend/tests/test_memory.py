import os, sys, tempfile
os.environ["NEXUS_DB"] = os.path.join(tempfile.mkdtemp(), "m.db")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from fastapi.testclient import TestClient
from app import db, tools, memory
from app.main import app, build_system_prompt, get_prefs

db.init()
c = TestClient(app)


def test_memory_crud_search_pin():
    a = c.post("/api/memory", json={"content": "Jeg liker kort svar", "kind": "preference"}).json()
    b = c.post("/api/memory", json={"content": "Prosjekt Alfa leveres fredag", "kind": "project", "pinned": True}).json()
    items = c.get("/api/memory").json()["items"]
    assert items[0]["id"] == b["id"] and items[0]["pinned"]
    assert [x["id"] for x in c.get("/api/memory", params={"q": "kort"}).json()["items"]] == [a["id"]]
    assert c.patch(f"/api/memory/{a['id']}", json={"content": "Jeg liker lange svar"}).status_code == 200
    assert "lange" in c.get("/api/memory", params={"q": "lange"}).json()["items"][0]["content"]
    assert c.post("/api/memory", json={"content": "jeg liker lange svar"}).json()["duplicate"] is True
    assert c.post("/api/memory", json={"content": "", "kind": "fact"}).status_code == 422
    assert c.post("/api/memory", json={"content": "x", "kind": "bogus"}).status_code == 422
    assert c.patch("/api/memory/9999", json={"pinned": True}).status_code == 404
    c.delete(f"/api/memory/{a['id']}")
    assert all(x["id"] != a["id"] for x in c.get("/api/memory").json()["items"])


def test_memory_in_system_prompt_and_toggle():
    c.post("/api/memory", json={"content": "Favorittfarge er grønn"})
    assert "Favorittfarge er grønn" in build_system_prompt(get_prefs())
    c.put("/api/memory/enabled", json={"enabled": False})
    assert "Favorittfarge" not in build_system_prompt(get_prefs())
    c.put("/api/memory/enabled", json={"enabled": True})
    assert "Favorittfarge" in build_system_prompt(get_prefs())


def test_context_cap_and_clear():
    for i in range(80):
        memory.add(f"Fakta nummer {i} " + "x" * 60)
    assert len(memory.context()) < memory.MEM_CHARS + 300
    assert c.delete("/api/memory").status_code == 400
    assert c.delete("/api/memory", params={"confirm": True}).status_code == 200
    assert c.get("/api/memory").json()["items"] == [] and memory.context() == ""


def test_remember_tool_no_approval_and_logged_in_list():
    assert not tools.TOOLS["remember"].needs_approval
    assert "Lagret" in tools.run_tool("remember", {"text": "Bor i Oslo", "kind": "fact"})
    assert "Husket allerede" in tools.run_tool("remember", {"text": "Bor i Oslo"})
    it = c.get("/api/memory").json()["items"][0]
    assert it["source"] == "agent" and it["content"] == "Bor i Oslo"


def test_workspace_sandbox(tmp_path):
    root = tmp_path / "ws"; root.mkdir(); (root / "a.txt").write_text("hei"); (root / "sub").mkdir()
    (tmp_path / "secret.txt").write_text("hemmelig")
    tools.set_roots([str(root)])
    l = c.get("/api/workspace/list", params={"path": str(root)}).json()
    assert [i["name"] for i in l["items"]] == ["sub", "a.txt"] and l["parent"] is None
    assert c.get("/api/workspace/read", params={"path": str(root / "a.txt")}).json()["text"] == "hei"
    assert c.get("/api/workspace/read", params={"path": str(tmp_path / "secret.txt")}).status_code == 403
    assert c.get("/api/workspace/list", params={"path": str(root / "..")}).status_code == 403
    (root / "b.bin").write_bytes(b"\x00\x01\x02" * 10)
    assert c.get("/api/workspace/read", params={"path": str(root / "b.bin")}).json()["binary"] is True
    assert c.get("/api/workspace/list", params={"path": str(root / "sub")}).json()["parent"] == str(root)
    assert c.put("/api/workspace/roots", json={"roots": ["/finnes/ikke"]}).status_code == 422
