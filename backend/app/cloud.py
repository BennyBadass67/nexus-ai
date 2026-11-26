"""v1.2: Sky-KI (valgfritt, av som standard). Kun gratisnivåer, OpenAI-kompatible endepunkter.
- Nøkler ligger bare i den lokale databasen og sendes aldri tilbake til UI-et.
- Ingenting sendes til skyen før du har slått på en leverandør og krysset av at du forstår det.
- Kvoten omgås aldri: når gratiskvoten er brukt opp, stopper appen og sier fra."""
import json
import re
import time
from datetime import datetime, timezone
from typing import AsyncIterator
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import db

router = APIRouter()
PREFIX = "cloud:"
CLOUD_BUDGET = 6000      # tokens av samtalen som sendes (skymodeller har lengre kontekst enn 4096)

PROVIDERS: dict[str, dict] = {
    "cloudflare": {
        "label": "Cloudflare Workers AI", "base": "https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1",
        "needs_account": True, "free_only": False, "live_models": False,
        "models": ["@cf/meta/llama-3.3-70b-instruct-fp8-fast", "@cf/meta/llama-3.1-8b-instruct-fp8-fast", "@cf/meta/llama-4-scout-17b-16e-instruct",
                   "@cf/google/gemma-3-12b-it", "@cf/mistralai/mistral-small-3.1-24b-instruct"],
        "free": "Gratis: 10 000 neuroner per dag på Workers Free-planen. Når de er brukt opp, avvises forespørsler (ingen regning med mindre du selv oppgraderer til Workers Paid). Nullstilles 00:00 UTC.",
        "key_help": "Cloudflare-dashbordet > Workers AI > Use REST API > Create a Workers AI API token. Kontoen din (Account ID) står på samme side.",
        "key_url": "https://dash.cloudflare.com/?to=/:account/ai/workers-ai",
    },
    "openrouter": {
        "label": "OpenRouter (gratismodeller)", "base": "https://openrouter.ai/api/v1", "needs_account": False, "free_only": True, "live_models": True,
        "models": [], "free": "Gratis: kun modeller som slutter på «:free». Ca. 20 forespørsler i minuttet og 50 om dagen. NEXUS nekter å bruke betalte modeller.",
        "key_help": "openrouter.ai > Keys > Create key (ingen kort nødvendig for :free-modeller).", "key_url": "https://openrouter.ai/keys",
    },
    "groq": {
        "label": "Groq", "base": "https://api.groq.com/openai/v1", "needs_account": False, "free_only": False, "live_models": True,
        "models": ["openai/gpt-oss-20b", "openai/gpt-oss-120b"], "free": "Gratis nivå med grenser per minutt og dag (se console.groq.com/docs/rate-limits). Svært rask.",
        "key_help": "console.groq.com > API Keys > Create API Key.", "key_url": "https://console.groq.com/keys",
    },
    "gemini": {
        "label": "Google AI Studio (Gemini)", "base": "https://generativelanguage.googleapis.com/v1beta/openai", "needs_account": False, "free_only": False, "live_models": True,
        "models": ["gemini-3.5-flash"], "free": "Gratis nivå uten kort. Obs: på gratisnivået kan Google bruke innholdet til å forbedre produktene sine. Ikke send noe privat.",
        "key_help": "aistudio.google.com > Get API key.", "key_url": "https://aistudio.google.com/apikey",
    },
    "custom": {
        "label": "Egendefinert (OpenAI-kompatibel)", "base": "", "needs_account": False, "free_only": False, "live_models": True, "models": [],
        "free": "Egen URL (https). Nøkkel er valgfri. Du er selv ansvarlig for at tjenesten er gratis og at du stoler på den: den ser alt du sender.",
        "key_help": "Skriv inn base-URL som slutter på /v1.", "key_url": "",
    },
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS cloud_cfg (
  provider TEXT PRIMARY KEY, api_key TEXT NOT NULL DEFAULT '', account_id TEXT NOT NULL DEFAULT '',
  base_url TEXT NOT NULL DEFAULT '', enabled INTEGER NOT NULL DEFAULT 0, consent_at REAL,
  models TEXT NOT NULL DEFAULT '[]', custom_model TEXT NOT NULL DEFAULT '',
  day TEXT NOT NULL DEFAULT '', req_today INTEGER NOT NULL DEFAULT 0
);
"""
with db.conn() as _c:
    _c.executescript(SCHEMA)
    _cols = {r["name"] for r in _c.execute("PRAGMA table_info(cloud_cfg)").fetchall()}
    for _n, _t in (("tok_in", "INTEGER"), ("tok_out", "INTEGER"), ("neurons", "REAL")):
        if _n not in _cols:
            _c.execute(f"ALTER TABLE cloud_cfg ADD COLUMN {_n} {_t} NOT NULL DEFAULT 0")

# Cloudflare: neuroner per million tokens (inn, ut). Kilde: developers.cloudflare.com/workers-ai/platform/pricing/
CF_NEURONS = {
    "@cf/meta/llama-3.1-8b-instruct-fp8-fast": (4119, 34868), "@cf/meta/llama-3.3-70b-instruct-fp8-fast": (26668, 204805),
    "@cf/mistralai/mistral-small-3.1-24b-instruct": (31876, 50488), "@cf/meta/llama-3.1-8b-instruct-fp8": (13778, 26128),
    "@cf/meta/llama-4-scout-17b-16e-instruct": (24545, 77273), "@cf/google/gemma-3-12b-it": (31371, 50560),
}
CF_FALLBACK = (26668, 204805)   # ukjent modell: antar dyreste kjente (70B), så anslaget aldri er for lavt
# Kjente gratisgrenser per dag (leverandørens dokumentasjon). Groq og Gemini har grenser per modell: ingen felles tall, så vi viser bare forbruk.
DAILY_LIMITS = {"cloudflare": (10000, "neuroner"), "openrouter": (50, "forespørsler")}


class CloudError(RuntimeError):
    pass


def get_cfg(pid: str) -> dict:
    if pid not in PROVIDERS:
        raise HTTPException(404, "Ukjent leverandør")
    with db.conn() as c:
        r = c.execute("SELECT * FROM cloud_cfg WHERE provider=?", (pid,)).fetchone()
    return dict(r) if r else {"provider": pid, "api_key": "", "account_id": "", "base_url": "", "enabled": 0, "consent_at": None,
                              "models": "[]", "custom_model": "", "day": "", "req_today": 0}


def base_url(pid: str, cfg: dict) -> str:
    p = PROVIDERS[pid]
    if pid == "custom":
        u = cfg["base_url"].strip().rstrip("/")
    else:
        if p["needs_account"] and not re.fullmatch(r"[0-9a-fA-F]{32}", cfg["account_id"].strip()):
            raise CloudError("Mangler gyldig Account ID (32 tegn) for Cloudflare.")
        u = p["base"].format(account_id=cfg["account_id"].strip())
    return u


def valid_custom_url(u: str) -> bool:
    x = urlparse(u)
    return bool(x.hostname) and (x.scheme == "https" or (x.scheme == "http" and x.hostname in ("localhost", "127.0.0.1")))


def parse_model(name: str) -> tuple[str, str]:
    if not name.startswith(PREFIX):
        raise CloudError("Ikke en skymodell")
    rest = name[len(PREFIX):]
    pid, _, model = rest.partition(":")
    if pid not in PROVIDERS or not model:
        raise CloudError("Ugyldig skymodell: " + name)
    return pid, model


def is_cloud(name: str) -> bool:
    return isinstance(name, str) and name.startswith(PREFIX)


def free_ok(pid: str, model: str) -> bool:
    """OpenRouter: bare :free. Andre leverandører styres av kontoens gratisnivå."""
    return not PROVIDERS[pid]["free_only"] or model.endswith(":free")


def _bump(pid: str) -> None:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with db.conn() as c:
        c.execute("INSERT OR IGNORE INTO cloud_cfg(provider) VALUES(?)", (pid,))
        r = c.execute("SELECT day FROM cloud_cfg WHERE provider=?", (pid,)).fetchone()
        if r["day"] != today:
            c.execute("UPDATE cloud_cfg SET day=?, req_today=0, tok_in=0, tok_out=0, neurons=0 WHERE provider=?", (today, pid))
        c.execute("UPDATE cloud_cfg SET req_today=req_today+1 WHERE provider=?", (pid,))


def _err(pid: str, status: int, body: str) -> CloudError:
    label = PROVIDERS[pid]["label"]
    try:
        d = json.loads(body)
        msg = d.get("error", d)
        msg = msg.get("message", msg) if isinstance(msg, dict) else msg
        if isinstance(msg, list) and msg:
            msg = msg[0].get("message", msg[0]) if isinstance(msg[0], dict) else msg[0]
        msg = str(msg)
    except Exception:
        msg = body[:200]
    msg = msg[:300]
    if status in (401, 403):
        return CloudError(f"{label} avviste nøkkelen ({status}). Sjekk at den er riktig og har tilgang. {msg}")
    if status == 402:
        return CloudError(f"{label} krever betaling for dette. NEXUS bruker bare gratis nivå og stopper her.")
    if status == 429:
        return CloudError(f"Gratiskvoten hos {label} er brukt opp eller du sender for fort. NEXUS prøver ikke å omgå grensen. Vent litt, eller bruk en lokal modell.")
    if status == 404:
        return CloudError(f"{label}: modellen finnes ikke eller er fjernet. Velg en annen. {msg}")
    return CloudError(f"{label} svarte {status}: {msg}")


def est_tokens(messages: list[dict]) -> int:
    return max(1, int(sum(len(str(m.get("content") or "")) for m in messages) / 3.5))


def neurons_for(model: str, tin: int, tout: int) -> float:
    i, o = CF_NEURONS.get(model, CF_FALLBACK)
    return (tin * i + tout * o) / 1_000_000


def _add_usage(pid: str, model: str, tin: int, tout: int) -> None:
    nr = neurons_for(model, tin, tout) if pid == "cloudflare" else 0
    with db.conn() as c:
        c.execute("UPDATE cloud_cfg SET tok_in=tok_in+?, tok_out=tok_out+?, neurons=neurons+? WHERE provider=?", (tin, tout, nr, pid))


def _prep(name: str) -> tuple[str, str, dict, dict]:
    pid, model = parse_model(name)
    cfg = get_cfg(pid)
    if not cfg["enabled"] or not cfg["consent_at"]:
        raise CloudError(f"{PROVIDERS[pid]['label']} er ikke slått på. Slå den på under Settings > Sky-KI.")
    if not free_ok(pid, model):
        raise CloudError("Denne modellen er ikke gratis. NEXUS bruker bare gratis modeller (:free).")
    if not cfg["api_key"] and pid != "custom":
        raise CloudError(f"Mangler API-nøkkel for {PROVIDERS[pid]['label']}.")
    headers = {"Content-Type": "application/json"}
    if cfg["api_key"]:
        headers["Authorization"] = "Bearer " + cfg["api_key"]
    return pid, model, cfg, headers


async def stream(name: str, messages: list[dict], tools: list[dict] | None = None, json_mode: bool = False) -> AsyncIterator[tuple[str, object]]:
    from . import ollama
    pid, model, cfg, headers = _prep(name)
    url = base_url(pid, cfg) + "/chat/completions"
    payload: dict = {"model": model, "messages": ollama.fit_messages(messages, CLOUD_BUDGET), "stream": True, "temperature": 0.4, "max_tokens": 1500}
    if tools:
        payload["tools"] = tools
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    _bump(pid)
    t0 = time.time(); n = 0
    tin = est_tokens(payload["messages"])
    calls: dict[int, dict] = {}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(120, connect=8)) as c:
            async with c.stream("POST", url, json=payload, headers=headers) as r:
                if r.status_code != 200:
                    body = (await r.aread()).decode("utf-8", "replace")
                    if r.status_code == 400 and tools and "tool" in body.lower():
                        raise ollama.ToolsUnsupported(body[:200])
                    raise _err(pid, r.status_code, body)
                async for line in r.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        obj = json.loads(data)
                    except Exception:
                        continue
                    if "error" in obj:
                        raise CloudError(f"{PROVIDERS[pid]['label']}: {str(obj['error'])[:200]}")
                    for ch in obj.get("choices") or []:
                        d = ch.get("delta") or {}
                        if d.get("content"):
                            n += 1
                            yield "token", d["content"]
                        for tc in d.get("tool_calls") or []:
                            e = calls.setdefault(tc.get("index", 0), {"name": "", "args": ""})
                            fn = tc.get("function") or {}
                            e["name"] += fn.get("name") or ""
                            e["args"] += fn.get("arguments") or ""
    except httpx.ConnectError:
        _add_usage(pid, model, 0, 0)
        raise CloudError(f"Ingen kontakt med {PROVIDERS[pid]['label']}. Sjekk nettforbindelsen.")
    except httpx.TimeoutException:
        raise CloudError(f"{PROVIDERS[pid]['label']} svarte ikke i tide.")
    _add_usage(pid, model, tin, n)
    if calls:
        out = []
        for e in calls.values():
            try:
                a = json.loads(e["args"]) if e["args"].strip() else {}
            except Exception:
                a = {}
            out.append({"name": e["name"], "args": a if isinstance(a, dict) else {}})
        yield "tool_calls", out
    if n:
        yield "stats", {"tokens": n, "seconds": round(time.time() - t0, 2)}


async def chat_json(name: str, messages: list[dict]) -> str:
    out = ""
    async for kind, val in stream(name, messages, json_mode=True):
        if kind == "token":
            out += val
    return out


async def list_models(pid: str) -> list[str]:
    p, cfg = PROVIDERS[pid], get_cfg(pid)
    found: list[str] = []
    if p["live_models"] and cfg["api_key"] or (pid == "custom" and cfg["base_url"]):
        try:
            headers = {"Authorization": "Bearer " + cfg["api_key"]} if cfg["api_key"] else {}
            async with httpx.AsyncClient(timeout=httpx.Timeout(15, connect=6)) as c:
                r = await c.get(base_url(pid, cfg) + "/models", headers=headers)
            if r.status_code == 200:
                for m in r.json().get("data", []):
                    mid = str(m.get("id", "")).removeprefix("models/")
                    if mid and free_ok(pid, mid):
                        found.append(mid)
        except Exception:
            pass
    if pid == "gemini":
        found = [m for m in found if m.startswith("gemini")]
    return sorted(set(found))[:60] or list(p["models"])


def usage(pid: str, cfg: dict, today: str) -> dict:
    fresh = cfg["day"] == today
    reqs = cfg["req_today"] if fresh else 0
    tin, tout = (cfg["tok_in"], cfg["tok_out"]) if fresh else (0, 0)
    out = {"requests": reqs, "tokens_in": tin, "tokens_out": tout, "estimate": True, "resets": "00:00 UTC (01:00 norsk tid om vinteren)"}
    if pid in DAILY_LIMITS:
        lim, unit = DAILY_LIMITS[pid]
        used = round(cfg["neurons"] if fresh else 0) if pid == "cloudflare" else reqs
        out.update({"limit": lim, "unit": unit, "used": used, "remaining": max(0, lim - used), "pct": min(100, round(100 * used / lim))})
        out["note"] = ("Anslag: tokens telles ca. (tegn / 3,5) og regnes om med Cloudflares oppgitte neuron-priser. Cloudflares eget tall i dashbordet er fasit."
                       if pid == "cloudflare" else "Gratis :free-modeller har ca. 50 forespørsler per dag og 20 per minutt uten kreditt. Tallet er ditt eget tellerverk.")
    else:
        out["note"] = "Denne leverandøren har grenser per modell og konto, uten ett felles tall. Se grensene i leverandørens konsoll. Her vises bare det du har brukt via NEXUS."
    return out


def status(pid: str) -> dict:
    p, cfg = PROVIDERS[pid], get_cfg(pid)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        models = json.loads(cfg["models"] or "[]")
    except Exception:
        models = []
    return {"id": pid, "label": p["label"], "free": p["free"], "key_help": p["key_help"], "key_url": p["key_url"],
            "needs_account": p["needs_account"], "custom": pid == "custom",
            "has_key": bool(cfg["api_key"]), "key_hint": ("…" + cfg["api_key"][-4:]) if len(cfg["api_key"]) >= 8 else ("satt" if cfg["api_key"] else ""),
            "account_id": cfg["account_id"], "base_url": cfg["base_url"], "custom_model": cfg["custom_model"], "enabled": bool(cfg["enabled"] and cfg["consent_at"]),
            "models": models or list(p["models"]), "requests_today": cfg["req_today"] if cfg["day"] == today else 0, "usage": usage(pid, cfg, today)}


def enabled_models() -> list[dict]:
    out = []
    for pid, p in PROVIDERS.items():
        s = status(pid)
        if not s["enabled"]:
            continue
        ms = list(s["models"])
        cm = get_cfg(pid)["custom_model"].strip()
        if cm and cm not in ms:
            ms.insert(0, cm)
        for m in ms:
            if free_ok(pid, m):
                out.append({"name": f"{PREFIX}{pid}:{m}", "size": 0, "params": "sky", "quant": None, "cloud": True, "provider": p["label"]})
    return out


class CfgIn(BaseModel):
    api_key: str | None = Field(default=None, max_length=300)
    account_id: str | None = Field(default=None, max_length=64)
    base_url: str | None = Field(default=None, max_length=300)
    custom_model: str | None = Field(default=None, max_length=120)
    enabled: bool | None = None
    consent: bool = False


@router.get("/api/cloud/providers")
def providers():
    return [status(p) for p in PROVIDERS]


@router.put("/api/cloud/providers/{pid}")
def configure(pid: str, b: CfgIn):
    cfg = get_cfg(pid)
    if b.api_key is not None:
        k = b.api_key.strip()
        if re.search(r"\s", k):
            raise HTTPException(422, "Nøkkelen kan ikke inneholde mellomrom")
        cfg["api_key"] = k
    if b.account_id is not None:
        cfg["account_id"] = b.account_id.strip()
    if b.base_url is not None:
        u = b.base_url.strip().rstrip("/")
        if u and not valid_custom_url(u):
            raise HTTPException(422, "URL må starte med https:// (http er bare tillatt for localhost)")
        cfg["base_url"] = u
    if b.custom_model is not None:
        cfg["custom_model"] = b.custom_model.strip()
    if b.enabled is True:
        if not b.consent and not cfg["consent_at"]:
            raise HTTPException(422, "Du må krysse av for at du forstår at meldingene sendes ut av PC-en.")
        if not cfg["api_key"] and pid != "custom":
            raise HTTPException(422, "Legg inn API-nøkkel først.")
        if pid == "custom" and not cfg["base_url"]:
            raise HTTPException(422, "Legg inn base-URL først.")
        if pid == "cloudflare" and not re.fullmatch(r"[0-9a-fA-F]{32}", cfg["account_id"]):
            raise HTTPException(422, "Account ID skal være 32 tegn (heksadesimalt).")
        cfg["enabled"] = 1
        cfg["consent_at"] = cfg["consent_at"] or time.time()
    elif b.enabled is False:
        cfg["enabled"] = 0
    with db.conn() as c:
        c.execute("""INSERT INTO cloud_cfg(provider,api_key,account_id,base_url,enabled,consent_at,custom_model) VALUES(?,?,?,?,?,?,?)
                     ON CONFLICT(provider) DO UPDATE SET api_key=excluded.api_key, account_id=excluded.account_id, base_url=excluded.base_url,
                     enabled=excluded.enabled, consent_at=excluded.consent_at, custom_model=excluded.custom_model""",
                  (pid, cfg["api_key"], cfg["account_id"], cfg["base_url"], cfg["enabled"], cfg["consent_at"], cfg["custom_model"]))
    return status(pid)


@router.delete("/api/cloud/providers/{pid}")
def forget(pid: str):
    get_cfg(pid)
    with db.conn() as c:
        c.execute("DELETE FROM cloud_cfg WHERE provider=?", (pid,))
    return status(pid)


@router.post("/api/cloud/providers/{pid}/test")
async def test(pid: str):
    """Én liten forespørsel (teller mot gratiskvoten) som sjekker nøkkel og tilkobling, og henter modellisten."""
    cfg = get_cfg(pid)
    if not (cfg["api_key"] or (pid == "custom" and cfg["base_url"])):
        raise HTTPException(422, "Legg inn nøkkel først.")
    models = await list_models(pid)
    model = (cfg["custom_model"] or (models[0] if models else "")).strip()
    if not model:
        raise HTTPException(422, "Fant ingen modell å teste med. Skriv inn modellnavn.")
    if not free_ok(pid, model):
        raise HTTPException(422, "Modellen er ikke gratis.")
    # direkte kall (ikke via _prep): testen krever ikke at leverandøren er slått på
    headers = {"Content-Type": "application/json"}
    if cfg["api_key"]:
        headers["Authorization"] = "Bearer " + cfg["api_key"]
    try:
        url = base_url(pid, cfg) + "/chat/completions"
        async with httpx.AsyncClient(timeout=httpx.Timeout(40, connect=8)) as c:
            r = await c.post(url, headers=headers, json={"model": model, "messages": [{"role": "user", "content": "Svar med ett ord: OK"}], "max_tokens": 8})
    except CloudError as e:
        return {"ok": False, "error": str(e)}
    except httpx.HTTPError as e:
        return {"ok": False, "error": f"Ingen kontakt: {type(e).__name__}"}
    _bump(pid)
    if r.status_code != 200:
        return {"ok": False, "error": str(_err(pid, r.status_code, r.text))}
    with db.conn() as c:
        c.execute("UPDATE cloud_cfg SET models=? WHERE provider=?", (json.dumps(models), pid))
    reply = ""
    try:
        reply = r.json()["choices"][0]["message"]["content"][:40]
    except Exception:
        pass
    return {"ok": True, "model": model, "reply": reply, "models": models}
