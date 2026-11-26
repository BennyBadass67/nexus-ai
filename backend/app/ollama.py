"""Tynn klient mot Ollama. Alt går til lokal Ollama, ingen cloud."""
import json
from typing import AsyncIterator

import httpx

from . import config


async def tags() -> list[dict]:
    async with httpx.AsyncClient(timeout=5) as c:
        r = await c.get(f"{config.OLLAMA_URL}/api/tags")
        r.raise_for_status()
        return r.json().get("models", [])


async def version() -> str | None:
    try:
        async with httpx.AsyncClient(timeout=3) as c:
            r = await c.get(f"{config.OLLAMA_URL}/api/version")
            r.raise_for_status()
            return r.json().get("version")
    except Exception:
        return None


async def chat_stream(model: str, messages: list[dict]) -> AsyncIterator[tuple[str, object]]:
    """Gir ("token", tekst) underveis og til slutt ("stats", {tokens, seconds})."""
    # Begrenset kontekst gir mindre minnebruk (viktig på 4 GB GPU / 8 GB RAM). keep_alive holder modellen varm.
    payload = {"model": model, "messages": messages, "stream": True, "keep_alive": "10m",
               "options": {"num_ctx": 4096}}
    async with httpx.AsyncClient(timeout=httpx.Timeout(600, connect=5)) as c:
        async with c.stream("POST", f"{config.OLLAMA_URL}/api/chat", json=payload) as r:
            if r.status_code != 200:
                body = (await r.aread()).decode("utf-8", "replace")
                try:
                    body = json.loads(body).get("error", body)
                except Exception:
                    pass
                raise RuntimeError(body or f"Ollama svarte {r.status_code}")
            async for line in r.aiter_lines():
                if not line.strip():
                    continue
                obj = json.loads(line)
                if "error" in obj:
                    raise RuntimeError(obj["error"])
                piece = obj.get("message", {}).get("content", "")
                if piece:
                    yield "token", piece
                if obj.get("done"):
                    n, ns = obj.get("eval_count"), obj.get("eval_duration")
                    if n and ns:
                        yield "stats", {"tokens": n, "seconds": round(ns / 1e9, 2)}
                    break


async def pull_stream(name: str) -> AsyncIterator[dict]:
    """Strømmer nedlastingsfremdrift: {status, total?, completed?}."""
    async with httpx.AsyncClient(timeout=httpx.Timeout(None, connect=5)) as c:
        async with c.stream("POST", f"{config.OLLAMA_URL}/api/pull",
                            json={"model": name, "stream": True}) as r:
            if r.status_code != 200:
                body = (await r.aread()).decode("utf-8", "replace")
                try:
                    body = json.loads(body).get("error", body)
                except Exception:
                    pass
                raise RuntimeError(body or f"Ollama svarte {r.status_code}")
            async for line in r.aiter_lines():
                if line.strip():
                    obj = json.loads(line)
                    if "error" in obj:
                        raise RuntimeError(obj["error"])
                    yield obj


async def delete(name: str) -> None:
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.request("DELETE", f"{config.OLLAMA_URL}/api/delete", json={"model": name})
        if r.status_code == 404:
            raise FileNotFoundError(name)
        r.raise_for_status()


BENCH_PROMPT = "Skriv en kort fortelling om en robot som lærer å spille piano. Bruk ca. 80 ord."


async def bench(model: str) -> dict:
    """Måler lastetid og tokens/sek med et fast prompt (maks 96 tokens)."""
    async with httpx.AsyncClient(timeout=httpx.Timeout(300, connect=5)) as c:
        r = await c.post(f"{config.OLLAMA_URL}/api/generate", json={
            "model": model, "prompt": BENCH_PROMPT, "stream": False,
            "options": {"num_predict": 96, "temperature": 0.2}})
        if r.status_code != 200:
            raise RuntimeError(r.json().get("error", f"Ollama svarte {r.status_code}"))
        o = r.json()
    n, ns = o.get("eval_count", 0), o.get("eval_duration", 0)
    if not n or not ns:
        raise RuntimeError("Fikk ikke målbart svar fra modellen")
    return {"model": model, "tokens": n, "tps": round(n / (ns / 1e9), 1),
            "load_s": round(o.get("load_duration", 0) / 1e9, 1)}
