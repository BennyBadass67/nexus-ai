import os, sys, tempfile
os.environ["NEXUS_DB"] = os.path.join(tempfile.mkdtemp(), "t.db")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import pytest
from fastapi.testclient import TestClient
from app import db, screen, tools, agent
from app.main import app

client = TestClient(app)


class Fake:
    def __init__(self):
        self.log = []; self.cursor = (500, 400); self.title = "Notisblokk"
    def size(self): return (1920, 1080)
    def cursor_pos(self): return self.cursor
    def active_title(self): return self.title
    def windows(self): return ["Notisblokk", "Chrome"]
    def screenshot(self, max_w=1024): return screen._png(bytes([200, 100, 50]) * 16 * 9, 16, 9), 16, 9
    def focus(self, t): self.log.append(("focus", t)); return "Notisblokk"
    def click(self, x, y, b="left", d=False): self.log.append(("click", x, y, b, d))
    def scroll(self, n): self.log.append(("scroll", n))
    def type_text(self, t): self.log.append(("type", t))
    def press(self, p): self.log.append(("press", p))


@pytest.fixture()
def fake():
    f = Fake(); screen.set_backend(f); screen._times.clear()
    client.put("/api/settings", json={"screen_control": "on"})
    yield f
    client.put("/api/settings", json={"screen_control": "off"})
    screen.set_backend(None)


def test_off_by_default_and_hidden():
    assert client.get("/api/settings").json()["screen_control"] == "off"
    assert not tools.TOOLS["mouse_click"].available
    with pytest.raises(tools.ToolError):
        tools.run_tool("mouse_click", {"x": 1, "y": 1})
    assert "mouse_click" not in [s["function"]["name"] for s in [t.schema() for t in tools.TOOLS.values() if t.available]]


def test_all_need_approval():
    for n in ("screen_look", "focus_window", "mouse_click", "scroll", "type_text", "press_key"):
        assert tools.TOOLS[n].needs_approval


def test_click_and_bounds(fake):
    assert "Klikket" in tools.run_tool("mouse_click", {"x": 100, "y": 200})
    assert fake.log[-1] == ("click", 100, 200, "left", False)
    for bad in ({"x": 5000, "y": 1}, {"x": -1, "y": 1}, {"x": "a", "y": 1}, {"x": 1, "y": 1, "button": "middle"}):
        with pytest.raises(tools.ToolError):
            tools.run_tool("mouse_click", bad)
    assert len([l for l in fake.log if l[0] == "click"]) == 1


def test_keys(fake):
    tools.run_tool("press_key", {"keys": "ctrl+c"})
    assert fake.log[-1] == ("press", ["ctrl", "c"])
    tools.run_tool("press_key", {"keys": "Ctrl + Shift + N"})
    for bad in ("win+r", "alt+f4", "ctrl+alt+delete", "ctrl", "ctrl+a+b", "foo", "f13", ""):
        with pytest.raises(tools.ToolError):
            tools.run_tool("press_key", {"keys": bad})
    assert len(fake.log) == 2


def test_text_limits(fake):
    tools.run_tool("type_text", {"text": "hei æøå\nneste"})
    assert fake.log[-1] == ("type", "hei æøå\nneste")
    for bad in ("", "x" * 501, "a\x07b"):
        with pytest.raises(tools.ToolError):
            tools.run_tool("type_text", {"text": bad})


def test_sensitive_window_blocked(fake):
    fake.title = "Logg inn med BankID - Chrome"
    for n, a in (("type_text", {"text": "x"}), ("mouse_click", {"x": 1, "y": 1}), ("press_key", {"keys": "enter"}), ("screen_look", {})):
        with pytest.raises(tools.ToolError, match="passord"):
            tools.run_tool(n, a)
    assert fake.log == []
    fake.title = "Min Passord-liste"
    with pytest.raises(tools.ToolError):
        tools.run_tool("type_text", {"text": "x"})


def test_failsafe_corner(fake):
    fake.cursor = (0, 0)
    with pytest.raises(tools.ToolError, match="Nødstopp"):
        tools.run_tool("mouse_click", {"x": 10, "y": 10})
    assert fake.log == []


def test_rate_limit(fake):
    for _ in range(screen.MAX_PER_MIN):
        tools.run_tool("scroll", {"amount": 1})
    with pytest.raises(tools.ToolError, match="For mange"):
        tools.run_tool("scroll", {"amount": 1})


def test_focus_and_scroll_clamp(fake):
    assert "Notisblokk" in tools.run_tool("focus_window", {"title": "note"})
    tools.run_tool("scroll", {"amount": 999})
    assert fake.log[-1] == ("scroll", 20)
    with pytest.raises(tools.ToolError):
        tools.run_tool("focus_window", {"title": "a"})


def test_screen_look_no_vision_model(fake, monkeypatch):
    monkeypatch.setattr(screen, "_installed_vision", lambda: None)
    out = tools.run_tool("screen_look", {})
    assert "1920x1080" in out and "Notisblokk" in out and "moondream" in out
    r = client.get("/api/screen/last")
    assert r.status_code == 200 and r.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_screen_look_with_vision(fake, monkeypatch):
    import httpx
    monkeypatch.setattr(screen, "_installed_vision", lambda: "moondream:latest")
    seen = {}
    class R:
        def raise_for_status(self): pass
        def json(self): return {"message": {"content": "Et tekstvindu med en knapp"}}
    def post(url, json=None, timeout=None):
        seen.update(json); return R()
    monkeypatch.setattr(httpx, "post", post)
    out = tools.run_tool("screen_look", {"question": "Hva ser du?"})
    assert "Et tekstvindu med en knapp" in out and seen["model"] == "moondream:latest" and seen["messages"][0]["images"]


def test_png_valid():
    import zlib, struct
    p = screen._png(bytes([1, 2, 3]) * 4, 2, 2)
    assert p[:8] == b"\x89PNG\r\n\x1a\n"
    n = struct.unpack(">I", p[8:12])[0]
    assert p[12:16] == b"IHDR" and n == 13


def test_non_windows_error():
    screen.set_backend(None)
    if sys.platform != "win32":
        client.put("/api/settings", json={"screen_control": "on"})
        with pytest.raises(tools.ToolError, match="Windows"):
            tools.run_tool("scroll", {"amount": 1})
        client.put("/api/settings", json={"screen_control": "off"})
