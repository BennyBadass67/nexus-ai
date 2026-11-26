import json, os, sys, tempfile
os.environ["NEXUS_DB"] = os.path.join(tempfile.mkdtemp(), "tb.db")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import pytest
from fastapi.testclient import TestClient
from app import ollama, teambuilder, db
from app.main import app

c = TestClient(app)
GOOD = {"title": "Lekseteam", "mode": "leader", "max_rounds": 3, "agents": [
    {"name": "Lærer", "role": "forklarer", "prompt": "Forklar steg for steg.", "tools": ["web_search", "bogus_tool"]},
    {"name": "Quiz", "role": "tester", "prompt": "Lag spørsmål.", "tools": []}]}


def fake(monkeypatch, replies, installed=None):
    calls = []
    async def chat_json(model, messages):
        calls.append((model, messages)); return replies.pop(0)
    async def tags(): return installed if installed is not None else [{"name": "m:1b", "size": 500_000_000}]
    monkeypatch.setattr(ollama, "chat_json", chat_json); monkeypatch.setattr(ollama, "tags", tags)
    return calls


def test_design_returns_validated_proposal(monkeypatch):
    n0 = len(c.get("/api/agents").json())
    calls = fake(monkeypatch, [json.dumps(GOOD)])
    r = c.post("/api/teams/design", json={"description": "et team som hjelper meg med lekser", "model": "m:1b"}).json()
    p = r["proposal"]
    assert p["title"] == "Lekseteam" and p["mode"] == "leader" and p["max_rounds"] == 3 and len(p["agents"]) == 2
    assert p["agents"][0]["tools"] == ["web_search"]          # ukjent verktøy fjernet
    assert "lekser" in calls[0][1][1]["content"] and "web_search" in calls[0][1][0]["content"]
    assert len(c.get("/api/agents").json()) == n0                   # ingenting opprettet før brukeren sier ja


def test_retry_then_success_and_hard_failure(monkeypatch):
    calls = fake(monkeypatch, ["ikke json", json.dumps(GOOD)])
    assert c.post("/api/teams/design", json={"description": "hjelp med lekser", "model": "m:1b"}).status_code == 200 and len(calls) == 2
    fake(monkeypatch, ["{}", json.dumps({"agents": [{"name": "Alene"}]})])
    r = c.post("/api/teams/design", json={"description": "hjelp med lekser", "model": "m:1b"})
    assert r.status_code == 422 and "manuelt" in r.text


def test_normalize_clamps_and_dedupes():
    p = teambuilder.normalize({"title": "", "mode": "x", "max_rounds": 99, "agents": [{"name": "A"}, {"name": "a"}, {"name": "B", "tools": "no"}, 5, {"name": ""}]}, "m")
    assert [a.name for a in p.agents] == ["A", "B"] and p.mode == "roundrobin" and p.max_rounds == 6 and p.title == "Nytt team"
    with pytest.raises(ValueError): teambuilder.normalize([], "m")
    p6 = teambuilder.normalize({"agents": [{"name": f"N{i}"} for i in range(9)]}, "m"); assert len(p6.agents) == 5


def test_no_models_and_ollama_down(monkeypatch):
    fake(monkeypatch, [], installed=[])
    assert c.post("/api/teams/design", json={"description": "hjelp med lekser", "model": "x"}).status_code == 400
    async def boom(): raise RuntimeError("nede")
    monkeypatch.setattr(ollama, "tags", boom)
    assert c.post("/api/teams/design", json={"description": "hjelp med lekser", "model": "x"}).status_code == 503


def test_pick_model_uses_installed_and_hardware(monkeypatch):
    from app import system
    monkeypatch.setattr(system, "rate", lambda gb, hw, name=None: {"level": "green" if gb < 3 else "red"})
    inst = [{"name": "a:1b", "size": 1e9}, {"name": "b:3b", "size": 2.2e9}, {"name": "big:70b", "size": 40e9}, {"name": "nomic-embed", "size": 2.5e9}]
    assert teambuilder.pick_model(inst, "dflt", None) == "b:3b"
    assert teambuilder.pick_model([{"name": "big:70b", "size": 40e9}], "dflt", None) == "dflt"


def test_create_makes_agents_and_room(monkeypatch):
    p = teambuilder.normalize(GOOD, "m:1b").model_dump()
    n0 = len(c.get("/api/agents").json())
    room = c.post("/api/teams/create", json=p).json()
    ags = c.get("/api/agents").json()[n0:]
    assert [a["name"] for a in ags] == ["Lærer", "Quiz"] and all(a["model"] == "m:1b" for a in ags)
    assert room["agent_ids"] == [a["id"] for a in ags] and room["mode"] == "leader" and room["max_rounds"] == 3
    bad = {**p, "agents": [p["agents"][0], p["agents"][0]]}
    assert c.post("/api/teams/create", json=bad).status_code == 422


def test_designer_choice_and_agent_models(monkeypatch):
    from app import system
    hw = system.Hardware(cpu="Ryzen 5 5600H", cores=12, ram_gb=8.0, gpu="NVIDIA GeForce GTX 1650", vram_gb=4.0, gpu_vendor="nvidia", os="Windows")
    monkeypatch.setattr(system, "hardware", lambda refresh=False: hw)
    ch = teambuilder.choose_designer(hw)
    assert ch["model"] == "qwen2.5:3b" and ch["level"] in ("green", "yellow")
    assert teambuilder.agent_model({"name": "Koder", "role": "skriver Python-kode", "prompt": ""}, "qwen2.5:3b", hw) == "qwen2.5-coder:3b"
    assert teambuilder.agent_model({"name": "Lærer", "role": "forklarer", "prompt": ""}, "qwen2.5:3b", hw) == "qwen2.5:3b"
    assert teambuilder.agent_model({"name": "Skribent", "role": "skriver norsk tekst", "prompt": ""}, "qwen2.5:3b", hw) == "qwen2.5:3b"      # gemma3:4b er gul på 4 GB GPU, så den raske velges
    strong = system.Hardware(cpu="x", cores=16, ram_gb=32.0, gpu="NVIDIA RTX 4070", vram_gb=12.0, gpu_vendor="nvidia", os="Windows")
    assert teambuilder.agent_model({"name": "Skribent", "role": "skriver norsk tekst", "prompt": ""}, "qwen2.5:3b", strong) == "gemma3:4b"
    weak = system.Hardware(cpu="x", cores=2, ram_gb=4.0, gpu=None, vram_gb=0, gpu_vendor=None, os="Windows")
    assert teambuilder.agent_model({"name": "Skribent", "role": "skriver norsk tekst", "prompt": ""}, "qwen2.5:3b", weak) in ("qwen2.5:3b",)
    calls = fake(monkeypatch, [json.dumps(GOOD)], installed=[{"name": "qwen2.5:3b", "size": 1_900_000_000}])
    r = c.post("/api/teams/design", json={"description": "hjelp med lekser", "model": "m:1b"}).json()
    assert calls[0][0] == "qwen2.5:3b" and r["warning"] is None and r["missing_models"] == []
    assert all(a["model"] == "qwen2.5:3b" for a in r["proposal"]["agents"])
