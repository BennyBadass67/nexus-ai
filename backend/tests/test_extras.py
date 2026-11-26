import os, sys, tempfile
os.environ["NEXUS_DB"] = os.path.join(tempfile.mkdtemp(), "t.db")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from app import db, extras, tools
from app.main import app

client = TestClient(app)


def test_search_all_finds_everywhere():
    with db.conn() as c:
        cid = c.execute("INSERT INTO conversations(title,model,created_at,updated_at) VALUES('Ferieplaner','m',1,1)").lastrowid
        c.execute("INSERT INTO messages(conversation_id,role,content,created_at) VALUES(?,?,?,1)", (cid, "user", "Jeg vil reise til Trondheim i sommer", ))
    client.post("/api/memory", json={"content": "Benjamin elsker Trondheim", "kind": "fact"})
    client.post("/api/notes", json={"text": "Bestill tog til Trondheim"})
    client.post("/api/agents", json={"name": "Reiseguide", "role": "Trondheim-ekspert", "prompt": "", "tools": []})
    r = client.get("/api/search", params={"q": "trondheim"}).json()
    assert r["conversations"] and r["conversations"][0]["id"] == cid and "Trondheim" in r["conversations"][0]["snippet"]
    assert r["memories"] and r["notes"] and r["agents"]
    assert client.get("/api/search", params={"q": "x"}).json()["conversations"] == []        # for kort
    assert client.get("/api/search", params={"q": "100%_"}).status_code == 200                  # jokertegn gir ikke feil


def test_notes_crud_and_agent_tool():
    nid = client.post("/api/notes", json={"text": "Kjøp melk"}).json()["id"]
    assert client.post("/api/notes", json={"text": "Kjøp melk"}).json()["duplicate"] is True
    client.patch(f"/api/notes/{nid}", json={"done": True})
    assert [n for n in client.get("/api/notes").json() if n["id"] == nid][0]["done"] is True
    assert "lagret" in tools.run_tool("add_note", {"text": "Ring tannlegen", "due": "2026-12-01"})
    assert "Ring tannlegen (frist 2026-12-01)" in tools.run_tool("list_notes", {})
    assert "Kjøp melk" not in tools.run_tool("list_notes", {})                                   # ferdige skjules for agenten
    assert client.patch("/api/notes/99999", json={"done": True}).status_code == 404
    assert client.post("/api/notes", json={"text": ""}).status_code == 422
    client.delete(f"/api/notes/{nid}")


def test_templates():
    i = client.post("/api/templates", json={"title": "Oppsummer", "body": "Oppsummer teksten under i 3 punkter."}).json()["id"]
    assert any(t["id"] == i for t in client.get("/api/templates").json())
    client.delete(f"/api/templates/{i}")
    assert not any(t["id"] == i for t in client.get("/api/templates").json())


def test_export_markdown():
    with db.conn() as c:
        cid = c.execute("INSERT INTO conversations(title,model,created_at,updated_at) VALUES('Test: æøå?','m',1,1)").lastrowid
        c.execute("INSERT INTO messages(conversation_id,role,content,model,created_at) VALUES(?,?,?,?,1)", (cid, "user", "Hei", None))
        c.execute("INSERT INTO messages(conversation_id,role,content,model,created_at) VALUES(?,?,?,?,2)", (cid, "assistant", "Hallo!", "qwen2.5:3b"))
    r = client.get(f"/api/conversations/{cid}/export")
    assert r.status_code == 200 and "# Test: æøå?" in r.text and "**NEXUS (qwen2.5:3b)**" in r.text and "Hallo!" in r.text
    assert "attachment" in r.headers["content-disposition"]
    assert client.get("/api/conversations/99999/export").status_code == 404


def test_backup_and_restore_roundtrip():
    client.post("/api/memory", json={"content": "UNIKT-FAKTUM-123", "kind": "fact"})
    data = client.get("/api/backup").content
    assert data.startswith(b"SQLite format 3")
    for m in client.get("/api/memory").json()["items"]:
        client.delete(f"/api/memory/{m['id']}")
    assert not any("UNIKT-FAKTUM-123" in m["content"] for m in client.get("/api/memory").json()["items"])
    r = client.post("/api/backup/restore", content=data, headers={"content-type": "application/octet-stream"})
    assert r.status_code == 200 and r.json()["ok"] and Path(r.json()["safety_copy"]).exists()
    assert any("UNIKT-FAKTUM-123" in m["content"] for m in client.get("/api/memory").json()["items"])


def test_restore_rejects_garbage():
    for bad in (b"hello", b"SQLite format 3\x00" + b"\x00" * 50):
        assert client.post("/api/backup/restore", content=bad).status_code == 400
    import sqlite3
    p = os.path.join(tempfile.mkdtemp(), "x.db"); s = sqlite3.connect(p); s.execute("create table foo(a)"); s.commit(); s.close()
    r = client.post("/api/backup/restore", content=Path(p).read_bytes())
    assert r.status_code == 400 and "mangler" in r.json()["detail"]


@pytest.mark.skipif(not os.path.exists("/proc/stat"), reason="bare Linux-test")
def test_sysmon():
    extras.sysmon(); import time; time.sleep(0.4)
    r = client.get("/api/sysmon").json()
    assert 0 <= r["ram_pct"] <= 100 and r["ram_total_gb"] > 0 and r["cpu_pct"] is not None and "loaded" in r


def test_knowledge_index_and_search(tmp_path):
    (tmp_path / "ferie.md").write_text("# Ferie\n\nVi skal til Lofoten i juli. Husk telt og fiskestang.\n\nBilen må på service før turen.")
    (tmp_path / "jobb.txt").write_text("Møtereferat: budsjettet for 2027 ble vedtatt. Prosjekt Nexus får tre nye utviklere.")
    (tmp_path / "bilde.png").write_bytes(b"\x89PNG\x00\x00")
    (tmp_path / "node_modules").mkdir(); (tmp_path / "node_modules" / "x.js").write_text("lofoten lofoten")
    r = extras.index_folders([str(tmp_path)])
    assert r["added"] == 2 and r["files"] == 2
    hits = extras.knowledge_search("Hvor skal vi på ferie? Lofoten")
    assert hits and hits[0]["path"].endswith("ferie.md")
    assert extras.knowledge_search("budsjett")[0]["path"].endswith("jobb.txt")           # prefiks: budsjettet
    assert extras.knowledge_search("zzzqqq") == []
    again = extras.index_folders([str(tmp_path)])
    assert again["added"] == 0 and again["updated"] == 0                                  # uendret = ingen jobb
    (tmp_path / "jobb.txt").write_text("Helt nytt innhold om katter.")
    os.utime(tmp_path / "jobb.txt", (1, 1))
    assert extras.index_folders([str(tmp_path)])["updated"] == 1
    assert extras.knowledge_search("katter")[0]["path"].endswith("jobb.txt")
    (tmp_path / "ferie.md").unlink()
    assert extras.index_folders([str(tmp_path)])["removed"] == 1
    assert "Ingen treff" in tools.run_tool("search_knowledge", {"query": "lofoten"})


def test_knowledge_tool_and_api(tmp_path, monkeypatch):
    (tmp_path / "a.txt").write_text("Passordet til wifi står i skapet.")
    monkeypatch.setattr(tools, "get_roots", lambda: [str(tmp_path)])
    assert client.post("/api/knowledge/index").json()["files"] >= 1
    out = tools.run_tool("search_knowledge", {"query": "wifi"})
    assert "a.txt" in out and "skapet" in out
    assert client.get("/api/knowledge/search", params={"q": "wifi"}).json()[0]["path"].endswith("a.txt")
    client.delete("/api/knowledge")
    assert client.get("/api/knowledge/status").json()["files"] == 0
