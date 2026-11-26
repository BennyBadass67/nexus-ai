"""Agentløkke: modellen foreslår verktøykall, vi kjører dem trygt, og sender resultatet tilbake til modellen."""
import asyncio
import json
import re
import uuid
from typing import AsyncIterator, Callable

import httpx

from . import db, ollama, tools

MAX_STEPS = 8
APPROVAL_TIMEOUT = 300


class Run:
    def __init__(self):
        self.id = uuid.uuid4().hex[:12]
        self.stop = asyncio.Event()
        self.pending: dict[str, asyncio.Future] = {}


RUNS: dict[str, Run] = {}


def log(run_id: str, kind: str, tool: str | None = None, detail: str = "", status: str = "", result: str = "") -> None:
    with db.conn() as c:
        c.execute("INSERT INTO activity(run_id,ts,kind,tool,detail,status,result) VALUES(?,?,?,?,?,?,?)",
                  (run_id, db.now(), kind, tool, detail[:500], status, result[:1500]))


def agent_system(base: str, roots: list[str], native: bool, allowed: set[str] | None = None) -> str:
    s = (base + "\n\nDu er en agent som kan hjelpe med oppgaver på brukerens PC ved hjelp av verktøy. "
         "Bruk verktøy bare når det trengs. Ikke gjett filstier: bruk list_dir eller search_files først. "
         "Du har kun tilgang til disse mappene: " + "; ".join(roots) + ". "
         "Å skrive filer og å slette krever at brukeren godkjenner, og brukeren kan avslå. "
         "Du kan ikke kjøre kommandoer, installere programmer eller endre systeminnstillinger. "
         "Når du har nok informasjon, svar brukeren kort og tydelig. Ikke finn på resultater du ikke har fått fra et verktøy.")
    if not native:
        spec = "\n".join(f"- {t.name}({', '.join(t.params)}): {t.description}" for t in tools.TOOLS.values() if allowed is None or t.name in allowed)
        s += ("\n\nVerktøy:\n" + spec + "\n\nFor å bruke et verktøy, svar med KUN én linje på formen:\n"
              'TOOL: {"name": "verktøynavn", "args": {"argument": "verdi"}}\n'
              "Du får resultatet tilbake. Når du er ferdig, svar med vanlig tekst uten TOOL:.")
    return s


_TOOL_RE = re.compile(r"TOOL:\s*(\{.*\})", re.S)


def parse_text_call(text: str) -> dict | None:
    m = _TOOL_RE.search(text)
    if not m:
        return None
    try:
        o = json.loads(m.group(1))
        if isinstance(o, dict) and isinstance(o.get("name"), str):
            return {"name": o["name"], "args": o.get("args") or {}}
    except Exception:
        return None
    return None


async def run_agent(run: Run, model: str, messages: list[dict], base_system: str,
                    force_text_mode: bool = False, allowed: set[str] | None = None) -> AsyncIterator[dict]:
    """Gir hendelser: token, tool_call, approval, tool_result, stats, error, final."""
    roots = tools.get_roots()
    native = not force_text_mode
    schemas = [t.schema() for t in tools.TOOLS.values() if allowed is None or t.name in allowed]
    convo = [{"role": "system", "content": agent_system(base_system, roots, native, allowed)}] + messages
    log(run.id, "run", detail=f"Start med {model}", status="start")

    for step in range(MAX_STEPS):
        if run.stop.is_set():
            yield {"type": "stopped"}; log(run.id, "run", status="stopped"); return
        text, calls = "", []
        try:
            async for kind, val in ollama.chat_tools_stream(model, convo, schemas if native else None):
                if run.stop.is_set():
                    break
                if kind == "token":
                    text += val  # type: ignore
                    if native:
                        yield {"type": "token", "text": val}
                elif kind == "tool_calls":
                    calls = val  # type: ignore
                elif kind == "stats":
                    yield {"type": "stats", **val}  # type: ignore
        except ollama.ToolsUnsupported:
            if native:
                native = False
                convo[0] = {"role": "system", "content": agent_system(base_system, roots, False, allowed)}
                yield {"type": "notice", "text": "Modellen støtter ikke verktøy direkte. Bruker tekstmodus (mindre pålitelig)."}
                continue
            raise
        except (httpx.ConnectError, httpx.ConnectTimeout):
            yield {"type": "error", "message": "Får ikke kontakt med Ollama. Er Ollama startet?"}; return
        except Exception as e:
            yield {"type": "error", "message": str(e)}; log(run.id, "run", status="error", result=str(e)); return

        if run.stop.is_set():
            yield {"type": "stopped"}; log(run.id, "run", status="stopped"); return
        if not native and not calls:
            c = parse_text_call(text)
            if c:
                calls = [c]
            else:
                yield {"type": "token", "text": text}
        if not calls:
            yield {"type": "final", "text": text}; log(run.id, "run", status="done"); return

        if native:
            convo.append({"role": "assistant", "content": text,
                          "tool_calls": [{"function": {"name": c["name"], "arguments": c["args"]}} for c in calls]})
        else:
            convo.append({"role": "assistant", "content": "TOOL: " + json.dumps(calls[0], ensure_ascii=False)})
        for c in calls[:3]:
            name, args = c["name"], c["args"]
            cid = uuid.uuid4().hex[:8]
            t = tools.TOOLS.get(name)
            if allowed is not None and name not in allowed:
                t = None          # verktøy utenfor agentens tillatte liste behandles som ukjent
            desc = tools.describe(name, args if isinstance(args, dict) else {})
            yield {"type": "tool_call", "call_id": cid, "tool": name, "args": args, "describe": desc,
                   "risk": t.risk if t else "unknown", "needs_approval": bool(t and t.needs_approval)}
            result, status = "", "ok"
            if t and t.needs_approval:
                fut = asyncio.get_event_loop().create_future()
                run.pending[cid] = fut
                yield {"type": "approval", "call_id": cid, "tool": name, "args": args, "describe": desc, "risk": t.risk}
                waiter = asyncio.ensure_future(asyncio.wait_for(asyncio.shield(fut), APPROVAL_TIMEOUT))
                stopper = asyncio.ensure_future(run.stop.wait())
                done, _ = await asyncio.wait({waiter, stopper}, return_when=asyncio.FIRST_COMPLETED)
                ok = False
                if waiter in done and not waiter.exception():
                    ok = waiter.result()
                for x in (waiter, stopper):
                    x.cancel()
                run.pending.pop(cid, None)
                if run.stop.is_set():
                    log(run.id, "tool", name, desc, "stopped"); yield {"type": "stopped"}; return
                if not ok:
                    result, status = "Brukeren avslo handlingen (eller svarte ikke i tide). Ikke prøv igjen uten å spørre.", "denied"
            if status == "ok":
                try:
                    if allowed is not None and name not in allowed:
                        raise tools.ToolError(f"Du har ikke tilgang til verktøyet «{name}»")
                    result = await asyncio.to_thread(tools.run_tool, name, args)
                except tools.ToolError as e:
                    result, status = f"Feil: {e}", "error"
                except Exception as e:
                    result, status = f"Uventet feil: {e}", "error"
            log(run.id, "tool", name, desc, status, result)
            yield {"type": "tool_result", "call_id": cid, "tool": name, "status": status, "result": result[:3000]}
            convo.append({"role": "tool", "content": result[:6000]} if native else
                         {"role": "user", "content": f"Resultat fra {name}:\n{result[:6000]}"})
    yield {"type": "final", "text": "Jeg nådde maks antall steg uten å bli ferdig. Si hva jeg skal gjøre videre."}
    log(run.id, "run", status="max_steps")
