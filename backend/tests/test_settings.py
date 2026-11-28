import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("NEXUS_DB", str(tmp_path / "t.db"))
    from app import main
    return TestClient(main.app), main


def test_defaults_and_roundtrip(client):
    c, _ = client
    assert c.get("/api/settings").json()["agent_name"] == "NEXUS"
    r = c.put("/api/settings", json={"agent_name": "Jarvis", "accent": "#ff7a59", "persona": "Vær sarkastisk."})
    assert r.json()["agent_name"] == "Jarvis"
    assert c.get("/api/settings").json()["accent"] == "#ff7a59"


def test_validation(client):
    c, _ = client
    assert c.put("/api/settings", json={"accent": "red"}).status_code == 422
    assert c.put("/api/settings", json={"theme": "neon"}).status_code == 422
    assert c.put("/api/settings", json={"hack": "x"}).status_code == 422
    assert c.put("/api/settings", json={"agent_name": "  "}).status_code == 422


def test_system_prompt_uses_prefs(client):
    c, main = client
    c.put("/api/settings", json={"agent_name": "Jarvis", "persona": "Snakk som en pirat."})
    p = main.build_system_prompt(main.get_prefs())
    assert "Jarvis" in p and "pirat" in p and "Benjamin" in p


def test_glass_theme_and_intro_prefs(client=None):
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    assert c.put("/api/settings", json={"theme": "glass", "intro": "off"}).status_code == 200
    assert c.get("/api/settings").json()["theme"] == "glass"
    assert c.put("/api/settings", json={"intro": "maybe"}).status_code == 422
    c.put("/api/settings", json={"theme": "dark", "intro": "on"})


def test_focus_goal_pref(client):
    c, _ = client
    r = c.put("/api/settings", json={"focus_goal": "300"})
    assert r.status_code == 200 and r.json()["focus_goal"] == "300"
    assert c.get("/api/settings").json()["focus_goal"] == "300"
    assert c.put("/api/settings", json={"focus_goal": "123"}).status_code == 422
    r = c.put("/api/settings", json={"focus_goal": "off"})
    assert r.status_code == 200 and r.json()["focus_goal"] == "off"
