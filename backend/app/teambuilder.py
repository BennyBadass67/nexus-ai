"""Team-byggeren: brukeren beskriver hva de vil ha, den innebygde assistenten (en lokal modell) foreslår et agent-team.
Forslaget valideres strengt, vises for brukeren, og opprettes først når brukeren trykker «Opprett»."""
import asyncio
import json
import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import ollama, rooms, system, tools

router = APIRouter()
MAX_AGENTS = 5


class DesignIn(BaseModel):
    description: str = Field(min_length=5, max_length=1500)
    model: str = Field(min_length=1)


# Modeller som er gode nok (minst 3B) til å lage team som gyldig JSON. Velges ut fra PC-ens maskinvare, i denne rekkefølgen.
DESIGNER_CANDIDATES = [("qwen2.5:3b", 1.9), ("llama3.2:3b", 2.0)]
# Rolle -> modellkandidater (første som PC-en tåler grønt/gult velges). Ordet-lister avgjør hva agenten faktisk skal gjøre.
ROLE_MODELS = [
    ("koding", re.compile(r"\b(kode|koding|programmer|programmering|utvikler|debug|python|javascript|typescript|html|css|react|nettside|script|bug|sql)\w*", re.I),
     [("qwen2.5-coder:3b", 1.9), ("qwen2.5-coder:1.5b", 1.0)]),
    ("bilder", re.compile(r"\b(bilde|bilder|foto|skjermbilde|se på bilde|visuell|tegning)\w*", re.I),
     [("moondream", 1.7), ("llava-phi3", 2.9)]),
    ("norsk", re.compile(r"\b(norsk|norske|rettskriv|språk|oversett|skriver|tekst|forfatter|korrektur|brev|e-?post|stil)\w*", re.I),
     [("gemma3:4b", 3.3), ("qwen2.5:3b", 1.9)]),
    ("logikk", re.compile(r"\b(matte|matematikk|regn|logikk|analyse|analytiker|planlegg|beregn|data|statistikk)\w*", re.I),
     [("qwen2.5:3b", 1.9), ("llama3.2:3b", 2.0)]),
]


def choose_designer(hw) -> dict:
    """Velger designer-modellen: første kandidat som PC-en får til å kjøre grønt, ellers gult. Faller tilbake på den første."""
    rated = [(n, gb, system.rate(gb, hw, n)) for n, gb in DESIGNER_CANDIDATES]
    for lvl in ("green", "yellow"):
        for n, gb, r in rated:
            if r.get("level") == lvl:
                return {"model": n, "size_gb": gb, "level": lvl, "reason": r.get("reason", "")}
    n, gb, r = rated[0]
    return {"model": n, "size_gb": gb, "level": r.get("level", "red"), "reason": r.get("reason", "")}


def agent_model(a: dict, designer: str, hw) -> str:
    """Modell til en agent ut fra hva agenten skal gjøre OG hva PC-en tåler (grønn/gul etter målt eller estimert fart).
    Ingen treff eller ingen kandidat som passer: designer-modellen."""
    text = a.get("role", "") + " " + a.get("name", "") + " " + a.get("prompt", "")[:400]
    for _, rx, cands in ROLE_MODELS:
        if rx.search(text):
            for lvl in ("green", "yellow"):      # først en modell som går raskt på denne PC-en, ellers en som går tregt men fungerer
                for n, gb in cands:              # kandidatene står i rekkefølge etter hvor godt de passer rollen
                    if system.rate(gb, hw, n).get("level") == lvl:
                        return n
            break
    return designer


class AgentProp(BaseModel):
    model: str | None = Field(default=None, max_length=120)
    name: str = Field(min_length=1, max_length=30)
    role: str = Field(default="", max_length=200)
    prompt: str = Field(default="", max_length=2000)
    tools: list[str] = []


class Proposal(BaseModel):
    title: str = Field(min_length=1, max_length=80)
    agents: list[AgentProp] = Field(min_length=2, max_length=MAX_AGENTS)
    mode: str = Field(default="roundrobin", pattern="^(roundrobin|leader)$")
    max_rounds: int = Field(default=2, ge=1, le=rooms.MAX_ROUNDS_CAP)
    model: str = Field(min_length=1)


def _system_prompt() -> str:
    tl = "\n".join(f"- {t.name}: {t.description}" for t in tools.TOOLS.values() if t.name not in ("open_app", "open_path", "open_url"))
    return ("Du setter sammen et team av 2 til 5 KI-agenter som skal snakke sammen for å løse brukerens oppgave. "
            "Gi hver agent et kort navn (ett ord), en rolle (en setning) og en instruks (2-4 setninger om hvordan den skal oppføre seg og hva den skal levere). "
            "Agentene skal utfylle hverandre, ikke gjøre det samme. Svar på norsk. "
            "Svar KUN med JSON på denne formen: "
            '{"title": "kort teamnavn", "mode": "roundrobin", "max_rounds": 2, "agents": [{"name": "...", "role": "...", "prompt": "...", "tools": []}]}. '
            "mode er enten roundrobin (alle snakker i tur) eller leader (en leder velger hvem som snakker). "
            "tools er en liste med navn fra denne listen, og skal være tom hvis agenten ikke trenger verktøy:\n" + tl)


def normalize(obj, model: str) -> Proposal:
    """Gjør modellens JSON om til et gyldig forslag, eller kast en forståelig feil. Ingenting gjettes."""
    if not isinstance(obj, dict):
        raise ValueError("Svaret var ikke et JSON-objekt")
    raw = obj.get("agents")
    if not isinstance(raw, list):
        raise ValueError("Mangler agent-listen")
    agents, seen = [], set()
    for a in raw:
        if not isinstance(a, dict):
            continue
        name = re.sub(r"\s+", " ", str(a.get("name", ""))).strip()[:30]
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        tl = a.get("tools") if isinstance(a.get("tools"), list) else []
        agents.append({"name": name, "role": str(a.get("role", ""))[:200], "prompt": str(a.get("prompt", ""))[:2000],
                       "tools": [t for t in tl if isinstance(t, str) and t in tools.TOOLS]})
    if len(agents) < 2:
        raise ValueError("Fant færre enn to gyldige agenter")
    try:
        mr = int(obj.get("max_rounds", 2))
    except (TypeError, ValueError):
        mr = 2
    mode = obj.get("mode") if obj.get("mode") in ("roundrobin", "leader") else "roundrobin"
    return Proposal(title=str(obj.get("title") or "Nytt team")[:80], agents=agents[:MAX_AGENTS], mode=mode,
                    max_rounds=min(max(mr, 1), rooms.MAX_ROUNDS_CAP), model=model)


def pick_model(installed: list[dict], default: str, hw) -> str:
    """Velger blant de installerte modellene den største som PC-en faktisk holder til (grønn, ellers gul).
    Alle agentene bruker samme modell, så Ollama slipper å bytte modell mellom hver tur (8 GB RAM)."""
    best, best_gb = None, -1.0
    for lvl in ("green", "yellow"):
        for m in installed:
            gb = m.get("size", 0) / 1e9
            if system.rate(gb, hw, m["name"]).get("level") == lvl and gb > best_gb and "embed" not in m["name"]:
                best, best_gb = m["name"], gb
        if best:
            return best
    return default


@router.get("/api/teams/designer")
async def designer():
    """Hvilken modell appen bruker til team-design (valgt ut fra målt maskinvare), og om den er installert."""
    hw = await asyncio.to_thread(system.hardware)
    ch = choose_designer(hw)
    try:
        installed = {m["name"] for m in await ollama.tags()}
        online = True
    except Exception:
        installed, online = set(), False
    ch.update(installed=ch["model"] in installed or (":" not in ch["model"] and ch["model"] + ":latest" in installed), online=online,
              hardware=system.hw_dict(hw))
    return ch


@router.post("/api/teams/design")
async def design(d: DesignIn):
    try:
        installed = await ollama.tags()
    except Exception:
        raise HTTPException(503, "Ollama svarer ikke. Start Ollama først.")
    if not installed:
        raise HTTPException(400, "Ingen modeller installert. Last ned en under Models først.")
    hw = await asyncio.to_thread(system.hardware)
    names = [m["name"] for m in installed]
    ch = choose_designer(hw)
    warning = None
    if ch["model"] in names:
        model = ch["model"]
    else:
        model = pick_model(installed, d.model, hw) if pick_model(installed, d.model, hw) in names else d.model
        warning = f"Designer-modellen {ch['model']} er ikke lastet ned ennå, så {model} ble brukt. Små modeller lager ofte dårligere team."
    msgs = [{"role": "system", "content": _system_prompt()}, {"role": "user", "content": "Oppgave fra brukeren: " + d.description.strip()}]
    last_err = ""
    for attempt in range(2):
        try:
            text = await ollama.chat_json(model, msgs)
            prop = normalize(json.loads(text), model).model_dump()
            for a in prop["agents"]:
                a["model"] = agent_model(a, model, hw)
            need = sorted({a["model"] for a in prop["agents"]} - set(names))
            return {"proposal": prop, "model_used": model, "missing_models": need, "warning": warning}
        except (ValueError, json.JSONDecodeError) as e:
            last_err = str(e)
            msgs = msgs + [{"role": "user", "content": f"Svaret ditt var ugyldig ({last_err}). Svar på nytt med KUN gyldig JSON på formen over, minst to agenter."}]
        except RuntimeError as e:
            raise HTTPException(502, "Modellen feilet: " + str(e))
    raise HTTPException(422, f"Modellen ({model}) klarte ikke å lage et gyldig team ({last_err}). Små modeller er dårlige på dette: prøv en større modell, eller lag teamet manuelt.")


@router.post("/api/teams/create")
def create(p: Proposal):
    names = [a.name for a in p.agents]
    if len({n.lower() for n in names}) != len(names):
        raise HTTPException(422, "Agentnavn må være unike")
    ids = []
    for a in p.agents:
        ag = rooms.create_agent(rooms.AgentIn(name=a.name, role=a.role, prompt=a.prompt, model=a.model or p.model, tools=a.tools))
        ids.append(ag["id"])
    room = rooms.create_room(rooms.RoomIn(title=p.title, agent_ids=ids, max_rounds=p.max_rounds, mode=p.mode))
    return room
