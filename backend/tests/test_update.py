import os, sys, tempfile, threading, time, json
os.environ["NEXUS_DB"] = os.path.join(tempfile.mkdtemp(), "u.db")
os.environ["NEXUS_VERSION"] = "0.1.0"
os.environ["NEXUS_UPDATE_MIN_BYTES"] = "1000"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from http.server import BaseHTTPRequestHandler, HTTPServer
import pytest
from fastapi.testclient import TestClient

GOOD = b"MZ" + b"\x00" * 5000
MODE = {"v": "good", "latest": "9.9.9", "dl_host": None}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        port = self.server.server_address[1]
        if self.path == "/latest.json":
            url = (MODE["dl_host"] or f"http://127.0.0.1:{port}/release/") + "setup.exe"
            body = json.dumps({"version": MODE["latest"], "notes": "n", "platforms": {"windows-x86_64": {"url": url}}}).encode()
            self.send_response(200); self.send_header("content-length", str(len(body))); self.end_headers(); self.wfile.write(body); return
        if MODE["v"] == "cut":
            self.send_response(200); self.send_header("content-length", "100000"); self.end_headers(); self.wfile.write(GOOD); self.wfile.flush(); return
        data = {"good": GOOD, "notexe": b"<html>" + b"x" * 5000, "tiny": b"MZ" + b"1" * 10}[MODE["v"]]
        self.send_response(200); self.send_header("content-length", str(len(data))); self.end_headers(); self.wfile.write(data)


@pytest.fixture(scope="module")
def srv():
    s = HTTPServer(("127.0.0.1", 0), H); threading.Thread(target=s.serve_forever, daemon=True).start()
    from app import update
    update.UPDATE_URL = f"http://127.0.0.1:{s.server_address[1]}/latest.json"
    update.ALLOWED_PREFIX = f"http://127.0.0.1:{s.server_address[1]}/release/"
    yield s
    s.shutdown()


@pytest.fixture()
def c(srv):
    from app.main import app
    from app import update
    update.APP_VERSION = "0.1.0"; update.MIN_SIZE = 1000
    update.STATE.update(state="idle", error=None, path=None)
    MODE.update(v="good", latest="9.9.9", dl_host=None)
    return TestClient(app)


def wait_done(c):
    for _ in range(100):
        s = c.get("/api/update/status").json()
        if s["state"] in ("started", "error"):
            return s
        time.sleep(0.05)
    raise AssertionError("tidsavbrudd")


def test_check_reports_newer(c):
    j = c.get("/api/update").json()
    assert j["available"] is True and j["latest"] == "9.9.9" and j["current"] == "0.1.0"
    MODE["latest"] = "0.1.0"
    assert c.get("/api/update").json()["available"] is False


def test_full_flow_downloads_verifies_and_launches(c, monkeypatch):
    from app import update
    launched = []
    monkeypatch.setattr(update, "launch_installer", lambda p: launched.append(p))
    assert c.post("/api/update/install").json()["ok"]
    s = wait_done(c)
    assert s["state"] == "started" and s["error"] is None
    assert len(launched) == 1 and launched[0].read_bytes() == GOOD and s["done"] == len(GOOD)


def test_interrupted_download_shows_error(c, monkeypatch):
    from app import update
    monkeypatch.setattr(update, "launch_installer", lambda p: pytest.fail("skal ikke starte"))
    MODE["v"] = "cut"
    c.post("/api/update/install")
    s = wait_done(c)
    assert s["state"] == "error" and "avbrutt" in s["error"]
    assert not list((update.Path(tempfile.gettempdir()) / "nexus-update").glob("*.part"))


@pytest.mark.parametrize("mode,word", [("notexe", "ikke en Windows-installer"), ("tiny", "for liten")])
def test_invalid_file_rejected(c, monkeypatch, mode, word):
    from app import update
    monkeypatch.setattr(update, "launch_installer", lambda p: pytest.fail("skal ikke starte"))
    MODE["v"] = mode
    c.post("/api/update/install")
    s = wait_done(c)
    assert s["state"] == "error" and word in s["error"]


def test_launch_failure_is_reported_with_manual_path(c, monkeypatch):
    from app import update
    def boom(p): raise RuntimeError("Installasjon feilet")
    monkeypatch.setattr(update, "launch_installer", boom)
    c.post("/api/update/install")
    s = wait_done(c)
    assert s["state"] == "error" and "Installasjon feilet" in s["error"] and "kan kjøres manuelt" in s["error"]


def test_foreign_host_and_uptodate_refused(c):
    MODE["dl_host"] = "https://evil.example/x/"
    r = c.post("/api/update/install"); assert r.status_code == 400 and "ikke fra NEXUS" in r.text
    MODE.update(dl_host=None, latest="0.1.0")
    r = c.post("/api/update/install"); assert r.status_code == 400 and "Ingen nyere" in r.text


def test_launch_installer_not_windows():
    from app import update
    if sys.platform != "win32":
        with pytest.raises(RuntimeError):
            update.launch_installer(update.Path("x.exe"))


def _wait_state(c, want):
    for _ in range(100):
        s = c.get("/api/update/status").json()
        if s["state"] in want:
            return s
        time.sleep(0.05)
    raise AssertionError("tidsavbrudd")


def test_auto_downloads_in_background_without_launching(c, monkeypatch):
    import asyncio
    from app import update
    launched = []
    monkeypatch.setattr(update, "launch_installer", lambda p: launched.append(p))
    c.put("/api/settings", json={"autoupdate": "on"})
    assert asyncio.run(update.auto_tick()) == "downloading"
    s = _wait_state(c, ("ready", "error"))
    assert s["state"] == "ready" and s["version"] == "9.9.9" and os.path.exists(s["path"])
    assert launched == []                                   # ingenting startes uten at brukeren sier ja
    assert asyncio.run(update.auto_tick()) == "ready"       # ingen ny nedlasting
    r = c.post("/api/update/install")                       # brukeren trykker "Start på nytt og installer"
    assert r.status_code == 200 and len(launched) == 1 and launched[0].exists()
    assert c.get("/api/update/status").json()["state"] == "started"


def test_auto_respects_off_switch_and_up_to_date(c):
    import asyncio
    from app import update
    c.put("/api/settings", json={"autoupdate": "off"})
    assert asyncio.run(update.auto_tick()) == "off"
    assert c.get("/api/update/status").json()["state"] == "idle"
    c.put("/api/settings", json={"autoupdate": "on"})
    MODE["latest"] = "0.1.0"
    assert asyncio.run(update.auto_tick()) == "none"
    assert c.get("/api/update/status").json()["state"] == "idle"


def test_auto_rejects_bad_host_and_bad_file(c):
    import asyncio
    from app import update
    c.put("/api/settings", json={"autoupdate": "on"})
    MODE["dl_host"] = "http://evil.example/"
    assert asyncio.run(update.auto_tick()) == "bad-url"
    MODE["dl_host"] = None; MODE["v"] = "notexe"
    assert asyncio.run(update.auto_tick()) == "downloading"
    s = _wait_state(c, ("ready", "error"))
    assert s["state"] == "error"


def test_autoupdate_pref_validation(c):
    assert c.put("/api/settings", json={"autoupdate": "maybe"}).status_code == 422
    assert c.get("/api/settings").json()["autoupdate"] in ("on", "off")


def test_installer_is_started_detached_via_wmi(monkeypatch, tmp_path):
    """Installeren må ikke være barn av appen (installerens taskkill /T ville drept den). Sjekker kommandoen vi sender til PowerShell."""
    import subprocess
    from app import update
    seen = {}
    class R:  # noqa: D401
        returncode = 0; stdout = "1234\n"; stderr = ""
    def fake_run(args, **kw):
        seen["args"] = args; seen["kw"] = kw
        return R()
    monkeypatch.setattr(subprocess, "run", fake_run)
    p = tmp_path / "NEXUS_AI_9.9.9_setup.exe"
    assert update._spawn_detached(p) is True
    cmd = seen["args"][-1]
    assert "Win32_Process" in cmd and "/P /R" in cmd and str(p) in cmd


def test_hooks_do_not_kill_process_tree():
    from pathlib import Path
    h = (Path(__file__).resolve().parents[2] / "src-tauri" / "windows" / "hooks.nsh").read_text(encoding="utf-8")
    assert "taskkill /F /T" not in h
