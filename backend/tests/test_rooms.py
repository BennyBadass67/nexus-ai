import json, os, sys, tempfile
os.environ["NEXUS_DB"] = os.path.join(tempfile.mkdtemp(), "t.db")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import httpx, pytest
from app import ollama, rooms, tools
from app.main import app

BASE = ""


@pytest.fixture(scope="module", autouse=True)
def live():
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


def api(method, path, **kw):
    return httpx.request(method, BASE + path, timeout=10, **kw)


def events(rid, msg="Hva bør vi lage?", model="m"):
    out = []
    with httpx.stream("POST", f"{BASE}/api/rooms/{rid}/run", json={"message": msg, "default_model": model}, timeout=30) as r:
        for line in r.iter_lines():
            if line:
                out.append(json.loads(line))
    return out


@pytest.fixture()
def team():
    ids = [api("POST", "/api/agents", json={"name": n, "role": r, "prompt": "", "tools": t}).json()["id"]
           for n, r, t in [("Anna", "idéviser", []), ("Bjørn", "kritiker", []), ("Cato", "oppsummerer", [])]]
    return ids


def fake_chat(monkeypatch, replies=None, seen=None):
    """Hver tur svarer med replikk basert på hvem som snakker (navnet står i systemprompten)."""
    async def fake(model, messages):
        if seen is not None:
            seen.append((model, messages))
        who = next(n for n in ("Anna", "Bjørn", "Cato") if f"Du er {n}" in messages[0]["content"])
        text = (replies or {}).get(who, f"{who} sier noe.")
        for w in text.split(" "):
            yield "token", w + " "
    monkeypatch.setattr(ollama, "chat_stream", fake)


def test_agent_crud_and_validation():
    a = api("POST", "/api/agents", json={"name": "Test", "role": "r", "prompt": "p", "tools": ["read_file"]}).json()
    assert a["tools"] == ["read_file"]
    assert api("POST", "/api/agents", json={"name": "X", "tools": ["rm_rf"]}).status_code == 422
    assert api("POST", "/api/agents", json={"name": ""}).status_code == 422
    assert api("PUT", f"/api/agents/{a['id']}", json={"name": "Nytt", "tools": []}).json()["name"] == "Nytt"
    assert api("DELETE", f"/api/agents/{a['id']}").json()["ok"]


def test_room_validation(team):
    assert api("POST", "/api/rooms", json={"title": "x", "agent_ids": [99999]}).status_code == 422
    assert api("POST", "/api/rooms", json={"title": "x", "agent_ids": team, "max_rounds": 99}).status_code == 422
    assert api("POST", "/api/rooms", json={"title": "x", "agent_ids": []}).status_code == 422


def test_round_robin_order_and_shared_log(team, monkeypatch):
    seen = []
    fake_chat(monkeypatch, seen=seen)
    rid = api("POST", "/api/rooms", json={"title": "R", "agent_ids": team, "max_rounds": 2}).json()["id"]
    ev = events(rid)
    starts = [e["agent"] for e in ev if e["type"] == "turn_start"]
    assert starts == ["Anna", "Bjørn", "Cato", "Anna", "Bjørn", "Cato"]
    assert ev[-1]["type"] == "done"
    # den tredje agenten ser hva de to første sa (felles logg)
    third_prompt = seen[2][1][1]["content"]
    assert "[Du]: Hva bør vi lage?" in third_prompt and "[Anna]: Anna sier noe." in third_prompt and "[Bjørn]: Bjørn sier noe." in third_prompt
    room = api("GET", f"/api/rooms/{rid}").json()
    assert [m["author"] for m in room["messages"]] == ["Du"] + ["Anna", "Bjørn", "Cato"] * 2


def test_each_agent_can_use_own_model(team, monkeypatch):
    seen = []
    fake_chat(monkeypatch, seen=seen)
    api("PUT", f"/api/agents/{team[1]}", json={"name": "Bjørn", "role": "kritiker", "model": "stor:7b", "tools": []})
    rid = api("POST", "/api/rooms", json={"title": "R", "agent_ids": team, "max_rounds": 1}).json()["id"]
    events(rid, model="liten:1b")
    assert [m for m, _ in seen] == ["liten:1b", "stor:7b", "liten:1b"]


def test_done_marker_ends_early_and_is_removed(team, monkeypatch):
    fake_chat(monkeypatch, replies={"Bjørn": "Vi er enige [FERDIG]"})
    rid = api("POST", "/api/rooms", json={"title": "R", "agent_ids": team, "max_rounds": 3}).json()["id"]
    ev = events(rid)
    assert [e["agent"] for e in ev if e["type"] == "turn_start"] == ["Anna", "Bjørn"]
    msgs = api("GET", f"/api/rooms/{rid}").json()["messages"]
    assert msgs[-1]["content"] == "Vi er enige" and "FERDIG" not in json.dumps(msgs)


def test_max_rounds_cap_prevents_runaway(team, monkeypatch):
    fake_chat(monkeypatch)
    rid = api("POST", "/api/rooms", json={"title": "R", "agent_ids": team, "max_rounds": 1}).json()["id"]
    assert sum(e["type"] == "turn_start" for e in events(rid)) == 3


def test_leader_mode_follows_choice_and_falls_back(team, monkeypatch):
    calls = {"leader": 0}
    async def fake(model, messages):
        sys_ = messages[0]["content"]
        if sys_.startswith("Du leder"):
            calls["leader"] += 1
            ans = ["Cato", "ukjent svar uten navn", "FERDIG"][calls["leader"] - 1]
            yield "token", ans
        else:
            who = next(n for n in ("Anna", "Bjørn", "Cato") if f"Du er {n}" in sys_)
            yield "token", f"{who} her."
    monkeypatch.setattr(ollama, "chat_stream", fake)
    rid = api("POST", "/api/rooms", json={"title": "R", "agent_ids": team, "max_rounds": 3, "mode": "leader"}).json()["id"]
    ev = events(rid)
    starts = [e["agent"] for e in ev if e["type"] == "turn_start"]
    assert starts[0] == "Cato"                                      # lederen velger hvem som svarer brukeren først
    assert starts[1] == "Bjørn" and len(starts) == 2                # uleselig svar => rund-og-rund, så FERDIG
    assert any(e["type"] == "notice" for e in ev)


def test_pick_leader_choice():
    ms = [{"name": "Anna"}, {"name": "Bjørn"}]
    assert rooms.pick_leader_choice("Bjørn", ms, "Anna") == "Bjørn"
    assert rooms.pick_leader_choice("Neste er Anna, deretter Bjørn", ms, "Anna") == "Bjørn"
    assert rooms.pick_leader_choice("FERDIG", ms, None) == "FERDIG"
    assert rooms.pick_leader_choice("hmm", ms, None) is None


def test_stop_halts_the_conversation(team, monkeypatch):
    import asyncio
    async def slow(model, messages):
        for i in range(200):
            await asyncio.sleep(0.02)
            yield "token", "ord "
    monkeypatch.setattr(ollama, "chat_stream", slow)
    rid = api("POST", "/api/rooms", json={"title": "R", "agent_ids": team, "max_rounds": 3}).json()["id"]
    ev = []
    with httpx.stream("POST", f"{BASE}/api/rooms/{rid}/run", json={"message": "gå", "default_model": "m"}, timeout=30) as r:
        for line in r.iter_lines():
            if not line:
                continue
            e = json.loads(line); ev.append(e)
            if e["type"] == "meta":
                run_id = e["run_id"]
            if e["type"] == "token" and sum(x["type"] == "token" for x in ev) == 3:
                api("POST", f"/api/agent/{run_id}/stop")
    assert any(e["type"] == "stopped" for e in ev) and ev[-1]["type"] == "done"
    assert sum(e["type"] == "turn_start" for e in ev) == 1


def test_agent_with_tools_uses_only_allowed_and_approval(team, monkeypatch, tmp_path):
    root = tmp_path / "D"; root.mkdir(); (root / "a.txt").write_text("innhold"); tools.set_roots([str(root)])
    api("PUT", f"/api/agents/{team[0]}", json={"name": "Anna", "role": "idéviser", "tools": ["read_file"]})
    fake_chat(monkeypatch)
    step = {"n": 0}
    async def fake_tools(model, messages, tl):
        if tl is not None and step["n"] == 0:
            step["n"] = 1
            assert [t["function"]["name"] for t in tl] == ["read_file"]          # bare tillatt verktøy tilbys
            yield "tool_calls", [{"name": "delete_path", "args": {"path": "a.txt"}}]   # prøver et ikke-tillatt verktøy
        else:
            yield "token", "Anna ferdig."
    monkeypatch.setattr(ollama, "chat_tools_stream", fake_tools)
    rid = api("POST", "/api/rooms", json={"title": "R", "agent_ids": [team[0]], "max_rounds": 1}).json()["id"]
    ev = events(rid)
    tr = [e for e in ev if e["type"] == "tool_result"]
    assert tr and tr[0]["status"] == "error" and (root / "a.txt").exists()      # ikke slettet, ingen godkjenning engang
    assert not any(e["type"] == "approval" for e in ev)


def test_example_room_and_cascade():
    ex = api("POST", "/api/rooms/example").json()
    assert ex["title"] == "Idémyldring" and len(ex["agent_ids"]) == 3
    for aid in ex["agent_ids"]:
        api("DELETE", f"/api/agents/{aid}")
    assert api("GET", f"/api/rooms/{ex['id']}").status_code == 404      # tomt rom slettes


def test_turn_messages_put_user_question_first():
    ag = {"name": "Anna", "role": "matematiker", "prompt": "Du elsker tall."}
    ms = [ag, {"name": "Bjørn", "role": "", "prompt": ""}]
    log = [{"author": "Du", "content": "Hva er hovedstaden i Frankrike?"}]
    m = rooms.turn_messages(ag, ms, log)
    assert "Svar først og fremst direkte" in m[0]["content"] and "Din stil og ekspertise: Du elsker tall." in m[0]["content"]
    assert "Hva er hovedstaden i Frankrike?" in m[1]["content"].split("Brukerens siste melding")[1]


def test_leader_cannot_end_before_first_answer(team, monkeypatch):
    async def fake(model, messages):
        yield "token", "FERDIG" if messages[0]["content"].startswith("Du leder") else "Svar."
    monkeypatch.setattr(ollama, "chat_stream", fake)
    rid = api("POST", "/api/rooms", json={"title": "R2", "agent_ids": team, "max_rounds": 2, "mode": "leader"}).json()["id"]
    starts = [e["agent"] for e in events(rid) if e["type"] == "turn_start"]
    assert len(starts) == 1
