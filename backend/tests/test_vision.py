import os, sys, tempfile
os.environ["NEXUS_DB"] = os.path.join(tempfile.mkdtemp(), "v.db")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import base64, json
from fastapi.testclient import TestClient
from app import ollama, vision
from app.main import app

client = TestClient(app)
SEEN = []
PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 50).decode()


def fake():
    async def f(model, messages, *a, **k):
        SEEN.append(messages)
        yield "token", "Jeg ser en katt."
    return f


def post(model, images, msg="Hva er dette?"):
    return client.post("/api/chat", json={"message": msg, "model": model, "images": images})


def test_vision_detection():
    assert vision.is_vision("moondream:latest") and vision.is_vision("qwen2.5vl:3b") and vision.is_vision("llava-phi3")
    assert not vision.is_vision("qwen2.5:1.5b") and not vision.is_vision("cloud:cloudflare:@cf/meta/llama-3.1-8b-instruct-fp8-fast")


def test_image_reaches_model_and_is_not_stored(monkeypatch):
    monkeypatch.setattr(ollama, "chat_stream", fake())
    r = post("moondream", [PNG])
    assert r.status_code == 200 and "Jeg ser en katt." in r.text
    last = SEEN[-1][-1]
    assert last["images"] == [PNG] and last["content"] == "Hva er dette?"
    cid = json.loads(r.text.splitlines()[0])["conversation_id"]
    stored = client.get(f"/api/conversations/{cid}").json()["messages"][0]["content"]
    assert PNG not in stored and "1 bilde" in stored


def test_rejections(monkeypatch):
    monkeypatch.setattr(ollama, "chat_stream", fake())
    n = len(SEEN)
    assert "kan ikke se bilder" in post("qwen2.5:1.5b", [PNG]).json()["detail"]
    assert "ikke til skyen" in post("cloud:groq:x", [PNG]).json()["detail"]
    assert post("moondream", ["ikke base64!!"]).status_code == 422
    assert "PNG, JPEG" in post("moondream", [base64.b64encode(b"hello world").decode()]).json()["detail"]
    assert post("moondream", [PNG] * 4).status_code == 422
    big = base64.b64encode(b"\xff\xd8\xff" + b"0" * 4_100_000).decode()
    assert "for stort" in post("moondream", [big]).json()["detail"]
    assert len(SEEN) == n                                   # ingenting nådde modellen
    assert post("qwen2.5:1.5b", None).status_code == 200    # vanlig chat urørt


def test_payload_to_ollama_keeps_images(monkeypatch):
    import asyncio, httpx
    seen = {}

    class R:
        status_code = 200
        async def aiter_lines(self):
            yield json.dumps({"message": {"content": "ok"}, "done": True})
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False

    class C:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        def stream(self, method, url, json=None, **k):
            seen["url"], seen["json"] = url, json
            return R()

    monkeypatch.setattr(ollama.httpx, "AsyncClient", C)
    msgs = [{"role": "system", "content": "s"}, {"role": "user", "content": "q", "images": [PNG]}]

    async def go():
        return [x async for x in ollama.chat_stream("moondream", msgs)]
    asyncio.run(go())
    assert seen["url"].endswith("/api/chat") and seen["json"]["messages"][-1]["images"] == [PNG]
