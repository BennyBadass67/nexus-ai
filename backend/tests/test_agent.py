import asyncio, json, os, sys, tempfile
os.environ["NEXUS_DB"] = os.path.join(tempfile.mkdtemp(), "t.db")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from app import agent, ollama, tools
from app.main import app

client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def live():
    """Ekte server i en tråd: strømming og godkjenning kan ikke testes med bufret TestClient."""
    import socket, threading, time, uvicorn
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    th = threading.Thread(target=srv.run, daemon=True); th.start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.05)
    global BASE
    BASE = f"http://127.0.0.1:{port}"
    yield
    srv.should_exit = True; th.join(5)


import httpx


def post(path, **kw):
    return httpx.post(BASE + path, timeout=10, **kw)


def stream_events(body):
    with httpx.stream("POST", BASE + "/api/agent/run", json=body, timeout=30) as r:
        for line in r.iter_lines():
            if line:
                yield json.loads(line)


@pytest.fixture()
def root(tmp_path, monkeypatch):
    r = tmp_path / "Documents"; r.mkdir()
    (r / "notat.txt").write_text("hemmelig hei", encoding="utf-8")
    (r / "sub").mkdir(); (r / "sub" / "bilde.png").write_bytes(b"\x89PNG\x00\x00")
    out = tmp_path / "utenfor.txt"; out.write_text("ikke din")
    tools.set_roots([str(r)])
    return r


# ---------- sandbox ----------
def test_path_traversal_blocked(root):
    for bad in ["../utenfor.txt", str(root.parent / "utenfor.txt"), "sub/../../utenfor.txt", "/etc/passwd", "~/.ssh/id_rsa"]:
        with pytest.raises(tools.ToolError):
            tools.run_tool("read_file", {"path": bad})


def test_symlink_escape_blocked(root):
    link = root / "snarvei"
    try:
        link.symlink_to(root.parent / "utenfor.txt")
    except OSError:
        pytest.skip("symlink ikke støttet")
    with pytest.raises(tools.ToolError):
        tools.run_tool("read_file", {"path": str(link)})


def test_read_list_search(root):
    assert "hemmelig" in tools.run_tool("read_file", {"path": "notat.txt"})
    out = tools.run_tool("list_dir", {"path": str(root)})
    assert "notat.txt" in out and "[mappe] sub" in out
    assert "notat.txt" in tools.run_tool("search_files", {"query": "notat"})
    with pytest.raises(tools.ToolError):
        tools.run_tool("read_file", {"path": "sub/bilde.png"})   # binær


def test_write_needs_overwrite_and_stays_in_root(root):
    tools.run_tool("write_file", {"path": "ny.txt", "content": "hei"})
    assert (root / "ny.txt").read_text() == "hei"
    with pytest.raises(tools.ToolError):
        tools.run_tool("write_file", {"path": "ny.txt", "content": "x"})
    with pytest.raises(tools.ToolError):
        tools.run_tool("write_file", {"path": "../ute.txt", "content": "x"})


def test_delete_goes_to_trash_not_gone(root, monkeypatch, tmp_path):
    monkeypatch.setattr(tools.Path, "home", classmethod(lambda cls: tmp_path))
    tools.run_tool("delete_path", {"path": "notat.txt"})
    assert not (root / "notat.txt").exists()
    assert list((tmp_path / ".nexus-ai" / "trash").glob("*notat.txt"))
    with pytest.raises(tools.ToolError):
        tools.run_tool("delete_path", {"path": str(root)})   # selve rotmappen


def test_open_blocks_executables_and_bad_urls(root, monkeypatch):
    (root / "x.exe").write_bytes(b"MZ")
    monkeypatch.setattr(tools, "_launch", lambda t: None)
    with pytest.raises(tools.ToolError):
        tools.run_tool("open_path", {"path": "x.exe"})
    assert "Åpnet" in tools.run_tool("open_path", {"path": "notat.txt"})
    for bad in ["file:///etc/passwd", "javascript:alert(1)", "ftp://x.no"]:
        with pytest.raises(tools.ToolError):
            tools.run_tool("open_url", {"url": bad})
    with pytest.raises(tools.ToolError):
        tools.run_tool("open_app", {"name": "powershell"})


def test_fetch_blocks_local_addresses():
    for u in ["http://127.0.0.1:8765/api/settings", "http://localhost/x", "http://169.254.169.254/latest"]:
        with pytest.raises(tools.ToolError):
            tools.run_tool("fetch_url", {"url": u})


def test_unknown_tool_and_missing_args(root):
    with pytest.raises(tools.ToolError):
        tools.run_tool("format_disk", {})
    with pytest.raises(tools.ToolError):
        tools.run_tool("read_file", {})


def test_no_shell_tool_exists():
    assert not any(n in tools.TOOLS for n in ("run_command", "shell", "exec", "install"))


def test_parse_ddg():
    html = ('<a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fno.wikipedia.org%2Fwiki%2FOslo&rut=x">Oslo - Wikipedia</a>'
            '<a class="result__snippet" href="#">Oslo er <b>Norges</b> hovedstad</a>')
    r = tools.parse_ddg(html)
    assert r[0]["url"] == "https://no.wikipedia.org/wiki/Oslo" and "hovedstad" in r[0]["snippet"]


def test_text_call_parser():
    assert agent.parse_text_call('Tenker...\nTOOL: {"name": "list_dir", "args": {"path": "."}}')["name"] == "list_dir"
    assert agent.parse_text_call("vanlig svar") is None
    assert agent.parse_text_call("TOOL: {ødelagt") is None


# ---------- løkke med falsk modell ----------
def script(monkeypatch, steps):
    """steps: liste av lister med ('token'|'tool_calls', verdi) per modellkall."""
    it = iter(steps); seen = []
    async def fake(model, messages, tl):
        seen.append((messages, tl))
        for kind, val in next(it):
            yield kind, val
    monkeypatch.setattr(ollama, "chat_tools_stream", fake)
    return seen


def run(msg="hei"):
    return list(stream_events({"message": msg, "model": "m"}))


def test_loop_reads_file_then_answers(root, monkeypatch):
    seen = script(monkeypatch, [[("tool_calls", [{"name": "read_file", "args": {"path": "notat.txt"}}])],
                                [("token", "Filen sier: "), ("token", "hemmelig hei")]])
    ev = run("les notat")
    types = [e["type"] for e in ev]
    assert types[0] == "meta" and "tool_call" in types and "tool_result" in types and types[-1] == "done"
    assert [e for e in ev if e["type"] == "tool_result"][0]["status"] == "ok"
    assert [e for e in ev if e["type"] == "final"][0]["text"] == "Filen sier: hemmelig hei"
    # resultatet ble sendt tilbake til modellen
    assert any(m["role"] == "tool" and "hemmelig" in m["content"] for m in seen[1][0])
    cid = ev[0]["conversation_id"]
    assert httpx.get(BASE + f"/api/conversations/{cid}").json()["messages"][-1]["content"] == "Filen sier: hemmelig hei"


def test_tool_error_is_returned_to_model(root, monkeypatch):
    script(monkeypatch, [[("tool_calls", [{"name": "read_file", "args": {"path": "../utenfor.txt"}}])], [("token", "Kunne ikke.")]])
    ev = run()
    r = [e for e in ev if e["type"] == "tool_result"][0]
    assert r["status"] == "error" and "utenfor" in r["result"].lower()
    assert "ikke din" not in json.dumps(ev)


def test_unknown_tool_does_not_crash(root, monkeypatch):
    script(monkeypatch, [[("tool_calls", [{"name": "hack", "args": {}}])], [("token", "ok")]])
    ev = run()
    assert [e for e in ev if e["type"] == "tool_result"][0]["status"] == "error"
    assert ev[-1]["type"] == "done"


def test_max_steps(root, monkeypatch):
    script(monkeypatch, [[("tool_calls", [{"name": "current_time", "args": {}}])]] * 20)
    ev = run()
    assert sum(e["type"] == "tool_result" for e in ev) == agent.MAX_STEPS
    assert "maks" in [e for e in ev if e["type"] == "final"][0]["text"]


def approve_flow(monkeypatch, allow, root):
    script(monkeypatch, [[("tool_calls", [{"name": "write_file", "args": {"path": "ny.txt", "content": "hei"}}])], [("token", "ferdig")]])
    ev = []
    for e in stream_events({"message": "skriv", "model": "m"}):
        ev.append(e)
        if e["type"] == "meta":
            run_id = e["run_id"]
        if e["type"] == "approval":
            assert not (root / "ny.txt").exists()          # ikke skrevet før godkjenning
            assert post(f"/api/agent/{run_id}/approve", json={"call_id": e["call_id"], "allow": allow}).status_code == 200
    return ev


def test_write_requires_approval_allow(root, monkeypatch):
    ev = approve_flow(monkeypatch, True, root)
    assert (root / "ny.txt").read_text() == "hei"
    assert [e for e in ev if e["type"] == "tool_result"][0]["status"] == "ok"


def test_write_denied_not_executed(root, monkeypatch):
    ev = approve_flow(monkeypatch, False, root)
    assert not (root / "ny.txt").exists()
    assert [e for e in ev if e["type"] == "tool_result"][0]["status"] == "denied"


def test_stop_during_approval(root, monkeypatch):
    script(monkeypatch, [[("tool_calls", [{"name": "delete_path", "args": {"path": "notat.txt"}}])]])
    ev = []
    for e in stream_events({"message": "slett", "model": "m"}):
        ev.append(e)
        if e["type"] == "meta":
            run_id = e["run_id"]
        if e["type"] == "approval":
            post(f"/api/agent/{run_id}/stop")
    assert (root / "notat.txt").exists()
    assert any(e["type"] == "stopped" for e in ev) and ev[-1]["type"] == "done"


def test_text_mode_fallback(root, monkeypatch):
    calls = {"n": 0}
    async def fake(model, messages, tl):
        calls["n"] += 1
        if tl is not None:
            raise ollama.ToolsUnsupported("does not support tools")
        if calls["n"] == 2:
            yield "token", 'TOOL: {"name": "list_dir", "args": {"path": "."}}'
        else:
            yield "token", "Der er notat.txt"
    monkeypatch.setattr(ollama, "chat_tools_stream", fake)
    ev = run("hva er her")
    assert any(e["type"] == "notice" for e in ev)
    assert [e for e in ev if e["type"] == "tool_result"][0]["status"] == "ok"
    assert [e for e in ev if e["type"] == "final"][0]["text"] == "Der er notat.txt"


def test_activity_log_and_config(root, monkeypatch):
    script(monkeypatch, [[("tool_calls", [{"name": "current_time", "args": {}}])], [("token", "ok")]])
    run()
    acts = httpx.get(BASE + "/api/activity").json()
    assert any(a["tool"] == "current_time" and a["status"] == "ok" for a in acts)
    cfg = httpx.get(BASE + "/api/agent/config").json()
    assert cfg["roots"] == [str(root)] and not any(t["name"] == "run_command" for t in cfg["tools"])
    assert httpx.put(BASE + "/api/agent/config", json={"roots": ["/"]}).status_code == 422
    assert httpx.put(BASE + "/api/agent/config", json={"roots": ["/finnes/ikke"]}).status_code == 422
