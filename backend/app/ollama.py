"""Tynn klient mot Ollama. Alt går til lokal Ollama, ingen cloud."""
import json
from typing import AsyncIterator

import httpx

from . import config


CTX = 4096
PROMPT_BUDGET = 2900      # tokens igjen til samtalen; resten er plass til svaret


def est_tokens(text: str) -> int:
    return len(text) // 3 + 4


def fit_messages(messages: list[dict], budget: int = PROMPT_BUDGET) -> list[dict]:
    """Holder prompten innenfor kontekstvinduet. Ollama kutter ellers stille fra starten, og kan miste systemprompten.
    Beholder systemmeldingen(e) og de nyeste meldingene, og korter ned den nyeste hvis den alene er for stor."""
    sysm = [m for m in messages if m.get("role") == "system"]
    rest = [m for m in messages if m.get("role") != "system"]
    used = sum(est_tokens(str(m.get("content", ""))) for m in sysm)
    if used > budget // 2:        # lang systemprompt: kort den ned så samtalen får plass
        keep = max(200, budget // 2) * 3
        sysm = [{**m, "content": str(m["content"])[:keep]} if m is sysm[0] else m for m in sysm]
        used = sum(est_tokens(str(m.get("content", ""))) for m in sysm)
    out: list[dict] = []
    for m in reversed(rest):
        t = est_tokens(str(m.get("content", "")))
        if used + t > budget:
            if not out:                       # nyeste melding må alltid med, men avkortet
                room = max(100, budget - used) * 3
                out.append({**m, "content": str(m["content"])[-room:]})
            break
        out.append(m); used += t
    return sysm + list(reversed(out))


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
    if model.startswith("cloud:"):
        from . import cloud
        async for x in cloud.stream(model, messages):
            yield x
        return
    # Begrenset kontekst gir mindre minnebruk (viktig på 4 GB GPU / 8 GB RAM). keep_alive holder modellen varm.
    payload = {"model": model, "messages": fit_messages(messages), "stream": True, "keep_alive": "10m",
               "options": {"num_ctx": CTX}}
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


class ToolsUnsupported(RuntimeError):
    pass


async def chat_tools_stream(model: str, messages: list[dict], tools: list[dict] | None) -> AsyncIterator[tuple[str, object]]:
    """Som chat_stream, men støtter Ollamas verktøykall. Gir ("token", tekst), ("tool_calls", liste), ("stats", ..)."""
    if model.startswith("cloud:"):
        from . import cloud
        async for x in cloud.stream(model, messages, tools):
            yield x
        return
    payload: dict = {"model": model, "messages": fit_messages(messages), "stream": True, "keep_alive": "10m",
                     "options": {"num_ctx": 4096, "temperature": 0.3, "num_predict": 900}}
    if tools:
        payload["tools"] = tools
    async with httpx.AsyncClient(timeout=httpx.Timeout(600, connect=5)) as c:
        async with c.stream("POST", f"{config.OLLAMA_URL}/api/chat", json=payload) as r:
            if r.status_code != 200:
                body = (await r.aread()).decode("utf-8", "replace")
                try:
                    body = json.loads(body).get("error", body)
                except Exception:
                    pass
                if "does not support tools" in str(body):
                    raise ToolsUnsupported(body)
                raise RuntimeError(body or f"Ollama svarte {r.status_code}")
            calls: list[dict] = []
            async for line in r.aiter_lines():
                if not line.strip():
                    continue
                obj = json.loads(line)
                if "error" in obj:
                    if "does not support tools" in str(obj["error"]):
                        raise ToolsUnsupported(obj["error"])
                    raise RuntimeError(obj["error"])
                msg = obj.get("message", {})
                if msg.get("content"):
                    yield "token", msg["content"]
                for tc in msg.get("tool_calls") or []:
                    fn = tc.get("function", {})
                    calls.append({"name": fn.get("name", ""), "args": fn.get("arguments") or {}})
                if obj.get("done"):
                    n, ns = obj.get("eval_count"), obj.get("eval_duration")
                    if calls:
                        yield "tool_calls", calls
                    if n and ns:
                        yield "stats", {"tokens": n, "seconds": round(ns / 1e9, 2)}
                    break


async def chat_json(model: str, messages: list[dict]) -> str:
    """Ett svar som må være gyldig JSON (Ollama sitt format-json). Brukes til å la modellen foreslå strukturerte ting."""
    if model.startswith("cloud:"):
        from . import cloud
        return await cloud.chat_json(model, messages)
    payload = {"model": model, "messages": fit_messages(messages), "stream": False, "format": "json", "keep_alive": "10m",
               "options": {"num_ctx": 4096, "temperature": 0.3, "num_predict": 900}}
    async with httpx.AsyncClient(timeout=httpx.Timeout(300, connect=5)) as c:
        r = await c.post(f"{config.OLLAMA_URL}/api/chat", json=payload)
        if r.status_code != 200:
            try:
                msg = r.json().get("error", r.text)
            except Exception:
                msg = r.text
            raise RuntimeError(msg or f"Ollama svarte {r.status_code}")
        return r.json().get("message", {}).get("content", "")
