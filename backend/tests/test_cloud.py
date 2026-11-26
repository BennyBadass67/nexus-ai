import os, sys, tempfile, json
os.environ["NEXUS_DB"] = os.path.join(tempfile.mkdtemp(), "t.db")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import httpx
import pytest
from fastapi.testclient import TestClient
from app import cloud, ollama
from app.main import app
from tests import mock_cloud

client = TestClient(app)
KEY = "testkey1234"
REAL = httpx.AsyncClient


@pytest.fixture(autouse=True)
def fake_net(monkeypatch):
    class C(REAL):
        def __init__(self, *a, **k):
            k.pop("transport", None)
            super().__init__(*a, transport=httpx.ASGITransport(app=mock_cloud.app), **k)
    monkeypatch.setattr(cloud.httpx, "AsyncClient", C)
    mock_cloud.SEEN.clear()


def setup_custom(enabled=True, key=KEY):
    r = client.put("/api/cloud/providers/custom", json={"api_key": key, "base_url": "http://127.0.0.1:9/v1", "custom_model": "free-a"})
    assert r.status_code == 200
    if enabled:
        r = client.put("/api/cloud/providers/custom", json={"enabled": True, "consent": True})
        assert r.status_code == 200
    return r.json()


async def collect(model, msgs=None, **k):
    out, ev = "", []
    async for kind, val in ollama.chat_stream(model, msgs or [{"role": "user", "content": "hei"}]):
        ev.append(kind); out += val if kind == "token" else ""
    return out, ev


def test_off_by_default_and_consent_required():
    assert all(not p["enabled"] for p in client.get("/api/cloud/providers").json())
    assert not [m for m in client.get("/api/models").json()["models"] if m.get("cloud")]
    client.put("/api/cloud/providers/custom", json={"api_key": KEY, "base_url": "http://127.0.0.1:9/v1"})
    r = client.put("/api/cloud/providers/custom", json={"enabled": True})                 # uten avkrysning
    assert r.status_code == 422 and "forstår" in r.json()["detail"]
    assert client.put("/api/cloud/providers/groq", json={"enabled": True, "consent": True}).status_code == 422   # uten nøkkel
    assert client.put("/api/cloud/providers/cloudflare", json={"api_key": "x" * 20, "enabled": True, "consent": True}).status_code == 422  # ugyldig Account ID
    client.delete("/api/cloud/providers/custom"); client.delete("/api/cloud/providers/cloudflare")


def test_key_never_returned_and_masked():
    s = setup_custom()
    assert s["enabled"] and s["has_key"] and s["key_hint"] == "…1234"
    assert KEY not in json.dumps(client.get("/api/cloud/providers").json())
    assert KEY not in client.get("/api/models").text and KEY not in client.get("/api/settings").text
    assert client.put("/api/cloud/providers/custom", json={"api_key": "has space"}).status_code == 422
    client.put("/api/cloud/providers/custom", json={"api_key": KEY})


def test_url_validation():
    assert client.put("/api/cloud/providers/custom", json={"base_url": "http://evil.example/v1"}).status_code == 422
    assert client.put("/api/cloud/providers/custom", json={"base_url": "ftp://x/v1"}).status_code == 422
    assert client.put("/api/cloud/providers/custom", json={"base_url": "https://ok.example/v1"}).status_code == 200
    client.put("/api/cloud/providers/custom", json={"base_url": "http://127.0.0.1:9/v1"})


def test_models_list_and_stream():
    setup_custom()
    names = [m["name"] for m in client.get("/api/models").json()["models"] if m.get("cloud")]
    assert "cloud:custom:free-a" in names
    import asyncio
    out, ev = asyncio.run(collect("cloud:custom:free-a"))
    assert out == "Sky svar: hei" and ev[-1] == "stats"
    assert mock_cloud.SEEN[-1]["auth"] == "Bearer " + KEY


def test_chat_endpoint_with_cloud_model():
    setup_custom()
    r = client.post("/api/chat", json={"message": "Hallo verden", "model": "cloud:custom:free-a"})
    evs = [json.loads(l) for l in r.text.splitlines() if l.strip()]
    assert r.status_code == 200 and "".join(e["text"] for e in evs if e["type"] == "token") == "Sky svar: Hallo verden"
    assert evs[0]["provider"] == "cloud" and evs[-1]["type"] == "done"


def test_tool_calls_assembled():
    setup_custom()
    import asyncio
    async def run():
        calls = []
        async for kind, val in ollama.chat_tools_stream("cloud:custom:free-a", [{"role": "user", "content": "x"}], [{"type": "function", "function": {"name": "list_no"}}]):
            if kind == "tool_calls": calls = val
        return calls
    assert asyncio.run(run()) == [{"name": "list_no", "args": {"path": "/x"}}]


def test_json_mode():
    setup_custom()
    import asyncio
    assert json.loads(asyncio.run(ollama.chat_json("cloud:custom:free-a", [{"role": "user", "content": "x"}]))) == {"ok": True}
    assert mock_cloud.SEEN[-1]["body"]["response_format"] == {"type": "json_object"}


def test_quota_and_paywall_stop_without_retry():
    setup_custom()
    import asyncio
    for model, word in (("limit", "brukt opp"), ("paywall", "bare gratis")):
        mock_cloud.SEEN.clear()
        with pytest.raises(cloud.CloudError) as e:
            asyncio.run(collect(f"cloud:custom:{model}"))
        assert word in str(e.value) and len(mock_cloud.SEEN) == 1          # ett forsøk: ingen omgåelse


def test_bad_key_and_disabled():
    import asyncio
    setup_custom(key="wrong")
    with pytest.raises(cloud.CloudError, match="avviste nøkkelen"):
        asyncio.run(collect("cloud:custom:free-a"))
    client.put("/api/cloud/providers/custom", json={"api_key": KEY, "enabled": False})
    with pytest.raises(cloud.CloudError, match="ikke slått på"):
        asyncio.run(collect("cloud:custom:free-a"))
    assert not [m for m in client.get("/api/models").json()["models"] if m.get("cloud")]


def test_openrouter_paid_models_are_refused():
    import asyncio
    client.put("/api/cloud/providers/openrouter", json={"api_key": "sk-or-xxxxxxxx", "enabled": True, "consent": True})
    with pytest.raises(cloud.CloudError, match="ikke gratis"):
        asyncio.run(collect("cloud:openrouter:openai/gpt-4o"))
    assert not mock_cloud.SEEN                                              # ingenting sendt
    assert cloud.free_ok("openrouter", "meta-llama/llama-3.3-70b-instruct:free") and not cloud.free_ok("openrouter", "x/y")
    client.delete("/api/cloud/providers/openrouter")


def test_test_endpoint_and_counter():
    client.put("/api/cloud/providers/custom", json={"api_key": KEY, "base_url": "http://127.0.0.1:9/v1", "custom_model": "free-a"})
    r = client.post("/api/cloud/providers/custom/test").json()
    assert r["ok"] and r["models"] == ["free-a", "free-b"] and r["reply"] == "OK"
    assert client.get("/api/cloud/providers").json()[-1]["requests_today"] >= 1
    client.put("/api/cloud/providers/custom", json={"api_key": "wrong"})
    r = client.post("/api/cloud/providers/custom/test").json()
    assert r["ok"] is False and "avviste" in r["error"]
    assert client.post("/api/cloud/providers/nope/test").status_code == 404
    assert client.post("/api/cloud/providers/groq/test").status_code == 422       # ingen nøkkel


def test_forget_removes_key():
    setup_custom()
    s = client.delete("/api/cloud/providers/custom").json()
    assert not s["has_key"] and not s["enabled"]


def test_cloudflare_url_needs_account():
    with pytest.raises(cloud.CloudError):
        cloud.base_url("cloudflare", {"account_id": "abc"})
    assert cloud.base_url("cloudflare", {"account_id": "a" * 32}).endswith("/accounts/" + "a" * 32 + "/ai/v1")
