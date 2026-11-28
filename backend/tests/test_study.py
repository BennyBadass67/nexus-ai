import os, sys, tempfile
os.environ["NEXUS_DB"] = os.path.join(tempfile.mkdtemp(), "t.db")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import json
from fastapi.testclient import TestClient
from app import ollama, study
from app.main import app

client = TestClient(app)
TEXT = "Fotosyntese er prosessen der planter bruker lys, vann og CO2 til å lage sukker og oksygen. Den skjer i kloroplastene. " * 2


def fake(cards):
    async def f(model, msgs):
        return json.dumps(cards)
    return f


def test_parse_variants():
    assert study.parse_cards('{"cards":[{"front":"A","back":"B"}]}') == [{"front": "A", "back": "B"}]
    assert study.parse_cards('[{"question":"Q","answer":"S"}]')[0]["front"] == "Q"
    assert study.parse_cards('tekst før {"kort":[{"spørsmål":"Q","svar":"S"}]} etter')[0]["back"] == "S"
    assert study.parse_cards("ikke json") == []
    assert study.parse_cards('{"cards":[{"front":"","back":"x"},5,{"front":"a"}]}') == []


def test_copycat_cards_are_rejected(monkeypatch):
    sent = "Norge ble forent av Harald Hårfagre rundt år 872 etter slaget ved Hafrsfjord."
    monkeypatch.setattr(ollama, "chat_json", fake({"cards": [{"front": sent, "back": sent},
                                                             {"front": "Hvem forente Norge?", "back": "Harald Hårfagre"},
                                                             {"front": "Uten spørsmålstegn", "back": "x"}]}))
    r = client.post("/api/study/generate", json={"model": "m", "text": TEXT + "copycat", "n": 5}).json()
    assert r["added"] == 1 and r["cards"][0]["back"] == "Harald Hårfagre"


def test_generate_dedupe_and_deck(monkeypatch):
    monkeypatch.setattr(ollama, "chat_json", fake({"cards": [{"front": "Hva er fotosyntese?", "back": "Planter lager sukker av lys."},
                                                             {"front": "hva er fotosyntese?", "back": "dup"},
                                                             {"front": "Hvor skjer det?", "back": "Kloroplastene"}]}))
    r = client.post("/api/study/generate", json={"model": "m", "text": TEXT, "title": "Biologi", "n": 5}).json()
    assert r["added"] == 2 and r["deck_id"]
    d = [x for x in client.get("/api/study/decks").json() if x["id"] == r["deck_id"]][0]
    assert d["total"] == 2 and d["due"] == 2 and d["title"] == "Biologi"


def test_generate_errors(monkeypatch):
    assert client.post("/api/study/generate", json={"model": "m"}).status_code == 422
    assert client.post("/api/study/generate", json={"model": "m", "text": "kort"}).status_code == 422
    assert client.post("/api/study/generate", json={"model": "m", "note_id": 99999}).status_code == 404
    monkeypatch.setattr(ollama, "chat_json", fake({"cards": []}))
    assert client.post("/api/study/generate", json={"model": "m", "text": TEXT}).status_code == 422
    async def boom(m, x): raise RuntimeError("modell mangler")
    monkeypatch.setattr(ollama, "chat_json", boom)
    assert client.post("/api/study/generate", json={"model": "m", "text": TEXT}).status_code == 502


def test_generate_from_note_and_chunking(monkeypatch):
    calls = []
    async def f(model, msgs):
        calls.append(msgs[0]["content"]); return json.dumps({"cards": [{"front": f"Spørsmål {len(calls)}?", "back": "A"}]})
    monkeypatch.setattr(ollama, "chat_json", f)
    from app import db
    with db.conn() as c:
        nid = c.execute("INSERT INTO notes(text,created_at) VALUES(?,1)", (("Avsnitt om historie. " * 60 + "\n\n") * 6,)).lastrowid
    r = client.post("/api/study/generate", json={"model": "m", "note_id": nid, "n": 6}).json()
    assert len(calls) >= 2 and r["added"] >= 2                      # lang tekst deles i flere kall
    assert all(len(c) < study.MAX_SRC + 600 for c in calls)


def test_sm2_schedule():
    e, iv, reps, lap = study.schedule(2.5, 0, 0, 0, 2); assert (iv, reps) == (1.0, 1)
    e, iv, reps, lap = study.schedule(e, iv, reps, lap, 2); assert (iv, reps) == (3.0, 2)
    e, iv2, reps, lap = study.schedule(e, iv, reps, lap, 2); assert iv2 == 7.5 and reps == 3
    e2, iv3, reps, lap = study.schedule(e, iv2, reps, lap, 0); assert (iv3, reps, lap) == (0.0, 0, 1) and e2 < e
    assert study.schedule(1.3, 0, 0, 0, 1)[0] == 1.3                # ease går ikke under 1.3


def test_review_flow_and_due(monkeypatch):
    did = client.post("/api/study/generate", json={"model": "m", "text": TEXT, "title": "T"}).json() if False else None
    monkeypatch.setattr(ollama, "chat_json", fake({"cards": [{"front": "A?", "back": "B"}, {"front": "C?", "back": "D"}]}))
    did = client.post("/api/study/generate", json={"model": "m", "text": TEXT + " ekstra"}).json()["deck_id"]
    cards = client.get(f"/api/study/decks/{did}/cards", params={"due": True}).json()
    assert len(cards) == 2
    r = client.post(f"/api/study/cards/{cards[0]['id']}/review", json={"grade": 2}).json()
    assert r["interval_days"] == 1.0
    assert len(client.get(f"/api/study/decks/{did}/cards", params={"due": True}).json()) == 1      # ett kort er utsatt
    r = client.post(f"/api/study/cards/{cards[1]['id']}/review", json={"grade": 0}).json()
    assert r["due"] > 0 and r["interval_days"] == 0
    assert client.post(f"/api/study/cards/{cards[0]['id']}/review", json={"grade": 9}).status_code == 422
    assert client.post("/api/study/cards/99999/review", json={"grade": 1}).status_code == 404
    cid = client.post(f"/api/study/decks/{did}/cards", json={"front": "Egen?", "back": "Ja"}).json()["id"]
    client.delete(f"/api/study/cards/{cid}")
    assert client.post("/api/study/decks/99999/cards", json={"front": "a", "back": "b"}).status_code == 404
    client.delete(f"/api/study/decks/{did}")
    assert client.get(f"/api/study/decks/{did}/cards").status_code == 404


def test_transform_streams_and_validates():
    r = client.post("/api/write/transform", json={"model": "mock:1b", "action": "summarize", "text": "Hei verden"})
    assert r.status_code == 200 and "Hei" in r.text and "mock" in r.text
    assert client.post("/api/write/transform", json={"model": "mock:1b", "action": "hack", "text": "x"}).status_code == 422
    assert client.post("/api/write/transform", json={"model": "mock:1b", "action": "fix", "text": ""}).status_code == 422
    r = client.post("/api/write/transform", json={"model": "finnes-ikke", "action": "fix", "text": "x"})
    assert "Feil" in r.text
    assert "summarize" in client.get("/api/write/actions").json()


def test_generate_end_to_end_with_mock_ollama():
    r = client.post("/api/study/generate", json={"model": "mock:1b", "text": TEXT, "title": "E2E", "n": 3})
    assert r.status_code == 200 and r.json()["added"] == 3


def test_ask_documents(tmp_path, monkeypatch):
    seen = []
    orig = ollama.chat_stream
    async def spy(model, msgs):
        seen.append(msgs)
        async for x in orig(model, msgs):
            yield x
    monkeypatch.setattr(ollama, "chat_stream", spy)
    from app import tools
    (tmp_path / "ferie.md").write_text("Vi skal til Lofoten i juli. Husk telt og fiskestang.", "utf-8")
    tools.set_roots([str(tmp_path)])
    client.post("/api/knowledge/index")
    r = client.post("/api/knowledge/ask", json={"model": "mock:1b", "q": "Hvor skal vi i juli Lofoten?"})
    assert r.status_code == 200 and "ferie.md" in json.loads(r.headers["x-sources"])[0] and "mock" in r.text
    assert "fiskestang" in seen[0][0]["content"] and "KUN ut fra utdragene" in seen[0][0]["content"]   # utdraget nådde modellen
    r = client.post("/api/knowledge/ask", json={"model": "mock:1b", "q": "kvantefysikk bananer"})
    assert "Fant ikke" in r.text and json.loads(r.headers["x-sources"]) == [] and len(seen) == 1     # ingen treff: modellen kalles ikke
    assert client.post("/api/knowledge/ask", json={"model": "mock:1b", "q": "x"}).status_code == 422


def test_generate_ollama_down(monkeypatch):
    import httpx
    async def down(m, x): raise httpx.ConnectError("nei")
    monkeypatch.setattr(ollama, "chat_json", down)
    r = client.post("/api/study/generate", json={"model": "m", "text": TEXT})
    assert r.status_code == 503 and "Ollama" in r.json()["detail"]


def _conv(title, msgs):
    from app import db
    with db.conn() as c:
        cid = c.execute("INSERT INTO conversations(title,model,created_at,updated_at) VALUES(?,?,1,1)", (title, "m")).lastrowid
        for r, t in msgs:
            c.execute("INSERT INTO messages(conversation_id,role,content,created_at) VALUES(?,?,?,1)", (cid, r, t))
    return cid


def test_clean_title():
    assert study.clean_title('Tittel: "Reise til Lofoten".') == "Reise til Lofoten"
    assert study.clean_title("**Matte-lekser**\nforklaring") == "Matte-lekser"
    assert study.clean_title("") == ""


def test_autotitle(monkeypatch):
    async def fake_stream(model, msgs):
        yield "token", '"Planlegger '
        yield "token", 'Lofoten-tur"'
    monkeypatch.setattr(ollama, "chat_stream", fake_stream)
    cid = _conv("Jeg vil planlegge en tur til Lofoten", [("user", "Jeg vil planlegge en tur til Lofoten"), ("assistant", "Gjerne!")])
    r = client.post(f"/api/conversations/{cid}/autotitle", json={"model": "m"}).json()
    assert r == {"title": "Planlegger Lofoten-tur", "changed": True}
    assert client.post(f"/api/conversations/{cid}/autotitle", json={"model": "m"}).json()["changed"] is False   # allerede satt: ikke overskriv
    own = _conv("Mitt eget navn", [("user", "hei"), ("assistant", "hei")])
    assert client.post(f"/api/conversations/{own}/autotitle", json={"model": "m"}).json()["changed"] is False   # brukerens navn beholdes
    assert client.post("/api/conversations/99999/autotitle", json={"model": "m"}).status_code == 404
    async def boom(model, msgs):
        raise RuntimeError("x"); yield
    monkeypatch.setattr(ollama, "chat_stream", boom)
    c2 = _conv("hei der", [("user", "hei der"), ("assistant", "hei")])
    assert client.post(f"/api/conversations/{c2}/autotitle", json={"model": "m"}).json()["changed"] is False     # feil gir ikke 500


def test_suggest(monkeypatch):
    monkeypatch.setattr(ollama, "chat_json", fake({"suggestions": ["Hva koster det?", {"q": "Når er best å reise?"}, "Hva koster det?", "x", 5]}))
    cid = _conv("t", [("user", "Lofoten?"), ("assistant", "Fint sted.")])
    assert client.post(f"/api/conversations/{cid}/suggest", json={"model": "m"}).json()["suggestions"] == ["Hva koster det?", "Når er best å reise?"]
    monkeypatch.setattr(ollama, "chat_json", fake("tull"))
    assert client.post(f"/api/conversations/{cid}/suggest", json={"model": "m"}).json()["suggestions"] == []
    empty = _conv("e", [])
    assert client.post(f"/api/conversations/{empty}/suggest", json={"model": "m"}).status_code == 422


def test_complete_stream_and_errors():
    r = client.post("/api/complete", json={"model": "mock:1b", "prompt": "Hei"})
    assert r.status_code == 200 and "Hei" in r.text
    assert "Feil" in client.post("/api/complete", json={"model": "nope", "prompt": "Hei"}).text
    assert client.post("/api/complete", json={"model": "mock:1b", "prompt": ""}).status_code == 422
    assert client.post("/api/complete", json={"model": "mock:1b", "prompt": "x" * 4001}).status_code == 422


def test_quick_deck_parses_and_creates():
    text = "hovedstaden i Norge = Oslo\n# kommentar\nfire pluss fire - 8\nH2O|vann\nDarlig linje uten separator\nsol;solen\n\n"
    r = client.post("/api/study/decks/quick", json={"title": "Blandet", "text": text})
    assert r.status_code == 201
    body = r.json()
    assert body["added"] == 4
    cards = client.get(f"/api/study/decks/{body['deck_id']}/cards").json()
    fronts = [c["front"] for c in cards]
    assert "hovedstaden i Norge" in fronts and "H2O" in fronts and "sol" in fronts
    assert all(c["back"] for c in cards)


def test_quick_deck_append_and_errors():
    r = client.post("/api/study/decks/quick", json={"title": "", "text": "a = b"})
    did = r.json()["deck_id"]
    r2 = client.post("/api/study/decks/quick", json={"text": "c = d", "deck_id": did})
    assert r2.status_code == 201 and r2.json()["added"] == 1 and r2.json()["deck_id"] == did
    assert client.post("/api/study/decks/quick", json={"text": "ingen separator her"}).status_code == 422
    assert client.post("/api/study/decks/quick", json={"text": "x = y", "deck_id": 999999}).status_code == 404
