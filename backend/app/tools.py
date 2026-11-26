"""Verktøyene agenten kan bruke. Alt går via godkjente mapper, og sletting/skriving krever godkjenning.

Det finnes bevisst INGEN generell terminal/kommandolinje-tool og ingen installasjon eller admin-handlinger.
"""
import datetime
import ipaddress
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import time
import webbrowser
from dataclasses import dataclass
from html import unescape
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from . import db


class ToolError(Exception):
    """Feil som sendes tilbake til modellen i klartekst så den kan prøve på nytt."""


# ---------- godkjente mapper ----------

def default_roots() -> list[str]:
    home = Path.home()
    found = [str(home / n) for n in ("Documents", "Dokumenter", "Desktop", "Skrivebord", "Downloads", "Nedlastinger") if (home / n).is_dir()]
    return found or [str(home)]


def get_roots() -> list[str]:
    with db.conn() as c:
        r = c.execute("SELECT value FROM settings WHERE key='agent:roots'").fetchone()
    if r:
        try:
            v = [x for x in json.loads(r["value"]) if isinstance(x, str)]
            if v:
                return v
        except Exception:
            pass
    return default_roots()


def set_roots(roots: list[str]) -> list[str]:
    clean = []
    for x in roots:
        p = Path(os.path.expandvars(os.path.expanduser(x.strip()))) if x.strip() else None
        if not p or not p.is_absolute() or not p.is_dir():
            raise ToolError(f"Mappen finnes ikke: {x}")
        if p.parent == p:
            raise ToolError("Hele disken kan ikke velges. Velg en mappe.")
        clean.append(str(p))
    if not clean:
        raise ToolError("Minst én mappe må velges")
    with db.conn() as c:
        c.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('agent:roots',?)", (json.dumps(clean),))
    return clean


def _norm(p: Path) -> str:
    return os.path.normcase(str(p))


def resolve_safe(path: str, roots: list[str] | None = None) -> Path:
    roots = roots if roots is not None else get_roots()
    if not roots:
        raise ToolError("Ingen godkjente mapper")
    if not path or "\x00" in path:
        raise ToolError("Ugyldig sti")
    raw = Path(os.path.expanduser(path))
    if not raw.is_absolute():
        raw = Path(roots[0]) / raw
    p = raw.resolve()            # løser opp .. og symlenker før sjekken
    for r in roots:
        rr = Path(r).resolve()
        if _norm(p) == _norm(rr) or _norm(rr) in [_norm(x) for x in p.parents]:
            return p
    raise ToolError("Stien ligger utenfor mappene du har gitt tilgang til: " + ", ".join(roots))


# ---------- verktøy ----------

def current_time(_: dict) -> str:
    return datetime.datetime.now().strftime("%A %d.%m.%Y %H:%M")


def system_info(_: dict) -> str:
    from . import system
    hw = system.hardware()
    return json.dumps({"os": hw.os, "cpu": hw.cpu, "ram_gb": hw.ram_gb, "gpu": hw.gpu, "vram_gb": hw.vram_gb}, ensure_ascii=False)


def list_dir(a: dict) -> str:
    p = resolve_safe(str(a.get("path", "")) or get_roots()[0])
    if not p.is_dir():
        raise ToolError("Dette er ikke en mappe")
    rows = []
    for e in sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))[:100]:
        try:
            rows.append(("[mappe] " if e.is_dir() else "[fil]   ") + e.name + ("" if e.is_dir() else f"  ({e.stat().st_size} byte)"))
        except OSError:
            continue
    return f"{p}\n" + ("\n".join(rows) or "(tom mappe)")


def read_file(a: dict) -> str:
    p = resolve_safe(str(a.get("path", "")))
    if not p.is_file():
        raise ToolError("Filen finnes ikke")
    data = p.read_bytes()[:60000]
    if b"\x00" in data[:2000]:
        raise ToolError("Dette ser ut som en binærfil, ikke tekst")
    text = data.decode("utf-8", "replace")
    return text[:20000] + ("\n[… avkortet]" if len(text) > 20000 or p.stat().st_size > 60000 else "")


def remember(a: dict) -> str:
    from . import memory
    kind = str(a.get("kind") or "fact")
    r = memory.add(str(a.get("text", "")), kind if kind in memory.KINDS else "fact", "agent")
    return "Husket allerede" if r.get("duplicate") else "Lagret i minnet (brukeren kan se og slette det på Memory-siden)"


_SKIP = {"node_modules", ".git", "__pycache__", "AppData", "$RECYCLE.BIN"}


def search_files(a: dict) -> str:
    q = str(a.get("query", "")).strip().lower()
    if len(q) < 2:
        raise ToolError("Søkeord må ha minst 2 tegn")
    roots = [str(resolve_safe(a["folder"]))] if a.get("folder") else get_roots()
    hits, t0 = [], time.time()
    for r in roots:
        for dp, dns, fns in os.walk(r):
            dns[:] = [d for d in dns if d not in _SKIP]
            for n in dns + fns:
                if q in n.lower():
                    hits.append(os.path.join(dp, n))
            if len(hits) >= 30 or time.time() - t0 > 6:
                break
    return "\n".join(hits[:30]) or "Ingen treff"


def write_file(a: dict) -> str:
    p = resolve_safe(str(a.get("path", "")))
    content = str(a.get("content", ""))
    if len(content) > 200_000:
        raise ToolError("Innholdet er for stort")
    if p.exists() and not a.get("overwrite"):
        raise ToolError("Filen finnes allerede. Sett overwrite=true hvis den skal erstattes.")
    if p.is_dir():
        raise ToolError("Dette er en mappe")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"Skrev {len(content)} tegn til {p}"


def _to_trash(p: Path) -> None:
    if sys.platform == "win32":
        kind = "DeleteDirectory" if p.is_dir() else "DeleteFile"
        esc = str(p).replace("'", "''")
        script = ("Add-Type -AssemblyName Microsoft.VisualBasic; "
                  f"[Microsoft.VisualBasic.FileIO.FileSystem]::{kind}('{esc}','OnlyErrorDialogs','SendToRecycleBin')")
        r = subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            raise ToolError("Kunne ikke flytte til papirkurven: " + (r.stderr.strip()[:200] or "ukjent feil"))
    else:
        trash = Path.home() / ".nexus-ai" / "trash"
        trash.mkdir(parents=True, exist_ok=True)
        shutil.move(str(p), str(trash / f"{int(time.time())}-{p.name}"))


def delete_path(a: dict) -> str:
    p = resolve_safe(str(a.get("path", "")))
    if any(_norm(p) == _norm(Path(r).resolve()) for r in get_roots()):
        raise ToolError("Selve den godkjente mappen kan ikke slettes")
    if not p.exists():
        raise ToolError("Finnes ikke")
    _to_trash(p)
    return f"Flyttet til papirkurven: {p}"


_BLOCKED_EXT = {".exe", ".bat", ".cmd", ".ps1", ".msi", ".vbs", ".vbe", ".js", ".jse", ".wsf", ".lnk", ".scr", ".com", ".reg", ".dll", ".jar", ".hta", ".cpl"}


def _launch(target: str) -> None:
    if sys.platform == "win32":
        os.startfile(target)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", target])
    else:
        subprocess.Popen(["xdg-open", target])


def open_path(a: dict) -> str:
    p = resolve_safe(str(a.get("path", "")))
    if not p.exists():
        raise ToolError("Finnes ikke")
    if p.is_file() and p.suffix.lower() in _BLOCKED_EXT:
        raise ToolError("Kjørbare filer åpnes ikke av agenten. Bruk open_app for kjente programmer.")
    _launch(str(p))
    return f"Åpnet {p}"


APPS = {"notepad": "notepad.exe", "notisblokk": "notepad.exe", "kalkulator": "calc.exe", "calculator": "calc.exe",
        "paint": "mspaint.exe", "utforsker": "explorer.exe", "explorer": "explorer.exe",
        "oppgavebehandling": "taskmgr.exe", "task manager": "taskmgr.exe", "klipp": "snippingtool.exe"}


def open_app(a: dict) -> str:
    name = str(a.get("name", "")).strip().lower()
    if name not in APPS:
        raise ToolError("Ukjent program. Tillatte: " + ", ".join(sorted(set(APPS))))
    if sys.platform == "win32":
        subprocess.Popen([APPS[name]])
    else:
        raise ToolError("Programmer kan bare åpnes på Windows")
    return f"Åpnet {name}"


def _http_url(u: str) -> str:
    pr = urlparse(u)
    if pr.scheme not in ("http", "https") or not pr.hostname:
        raise ToolError("Bare http(s)-adresser er tillatt")
    return u


def open_url(a: dict) -> str:
    u = _http_url(str(a.get("url", "")))
    webbrowser.open(u)
    return f"Åpnet {u} i nettleseren"


def _public_host(host: str) -> None:
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        raise ToolError("Fant ikke nettstedet")
    for i in infos:
        ip = ipaddress.ip_address(i[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise ToolError("Adresser på det lokale nettverket er blokkert")


def _strip_html(h: str) -> str:
    h = re.sub(r"(?is)<(script|style|noscript|svg).*?</\1>", " ", h)
    h = re.sub(r"(?s)<[^>]+>", " ", h)
    return re.sub(r"\s+", " ", unescape(h)).strip()


def fetch_url(a: dict) -> str:
    u = _http_url(str(a.get("url", "")))
    _public_host(urlparse(u).hostname or "")
    try:
        r = httpx.get(u, timeout=15, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0 NEXUS-AI"})
    except httpx.HTTPError as e:
        raise ToolError(f"Kunne ikke hente siden: {e}")
    _public_host(urlparse(str(r.url)).hostname or "")
    ct = r.headers.get("content-type", "")
    if "text" not in ct and "json" not in ct:
        raise ToolError("Siden er ikke tekst")
    return _strip_html(r.text)[:6000]


def parse_ddg(html: str) -> list[dict]:
    out = []
    for m in re.finditer(r'(?s)<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>(.*?)(?=<a[^>]+class="result__a"|$)', html):
        href, title, rest = m.group(1), _strip_html(m.group(2)), m.group(3)
        if "uddg=" in href:
            href = unquote(parse_qs(urlparse(href if href.startswith("http") else "https:" + href).query).get("uddg", [href])[0])
        sn = re.search(r'(?s)class="result__snippet"[^>]*>(.*?)</a>', rest)
        out.append({"title": title, "url": href, "snippet": _strip_html(sn.group(1)) if sn else ""})
    return out


def web_search(a: dict) -> str:
    q = str(a.get("query", "")).strip()
    if not q:
        raise ToolError("Mangler søkeord")
    try:
        r = httpx.post("https://html.duckduckgo.com/html/", data={"q": q}, timeout=15,
                       headers={"User-Agent": "Mozilla/5.0 NEXUS-AI"})
        r.raise_for_status()
    except httpx.HTTPError as e:
        raise ToolError(f"Søket feilet: {e}")
    res = parse_ddg(r.text)[:6]
    if not res:
        return "Ingen treff"
    return "\n\n".join(f"{i+1}. {x['title']}\n{x['url']}\n{x['snippet']}" for i, x in enumerate(res))


# ---------- skjermstyring (fase 3) ----------

def _scr(name: str) -> Callable[[dict], str]:
    from . import screen

    def run(a: dict) -> str:
        try:
            return getattr(screen, name)(a)
        except screen.ScreenError as e:
            raise ToolError(str(e))
    return run


# ---------- register ----------

@dataclass
class Tool:
    name: str
    description: str
    params: dict          # navn -> (type, beskrivelse, påkrevd)
    risk: str             # read | open | write | delete
    fn: Callable[[dict], str]

    @property
    def needs_approval(self) -> bool:
        return self.risk in ("write", "delete", "screen", "control")

    @property
    def available(self) -> bool:
        if self.risk in ("screen", "control"):
            from . import screen
            return screen.enabled()
        return True

    def schema(self) -> dict:
        props = {k: {"type": v[0], "description": v[1]} for k, v in self.params.items()}
        req = [k for k, v in self.params.items() if v[2]]
        return {"type": "function", "function": {"name": self.name, "description": self.description,
                                                 "parameters": {"type": "object", "properties": props, "required": req}}}


S = "string"
TOOLS: dict[str, Tool] = {t.name: t for t in [
    Tool("current_time", "Gir dato og klokkeslett nå.", {}, "read", current_time),
    Tool("system_info", "Gir info om PC-en (CPU, RAM, GPU).", {}, "read", system_info),
    Tool("list_dir", "Lister filer og mapper i en mappe.", {"path": (S, "Mappesti", True)}, "read", list_dir),
    Tool("read_file", "Leser en tekstfil.", {"path": (S, "Filsti", True)}, "read", read_file),
    Tool("search_files", "Søker etter filer og mapper på navn i de godkjente mappene.",
         {"query": (S, "Del av filnavnet", True), "folder": (S, "Valgfri mappe å søke i", False)}, "read", search_files),
    Tool("web_search", "Søker på nettet og gir titler, lenker og utdrag.", {"query": (S, "Søkeord", True)}, "read", web_search),
    Tool("fetch_url", "Henter og leser teksten på en nettside.", {"url": (S, "Full adresse som starter med http", True)}, "read", fetch_url),
    Tool("open_url", "Åpner en nettadresse i brukerens nettleser.", {"url": (S, "Adresse", True)}, "open", open_url),
    Tool("open_path", "Åpner en fil eller mappe med standardprogrammet.", {"path": (S, "Sti", True)}, "open", open_path),
    Tool("open_app", "Åpner et kjent program: " + ", ".join(sorted(set(APPS))) + ".", {"name": (S, "Programnavn", True)}, "open", open_app),
    Tool("remember", "Lagrer et kort faktum, en preferanse eller en beslutning om brukeren i langtidsminnet. Bruk bare når brukeren ber om det eller sier noe varig viktig.",
         {"text": (S, "Det som skal huskes, en kort setning", True), "kind": (S, "fact, preference, decision eller project", False)}, "memory", remember),
    Tool("write_file", "Skriver en tekstfil. Krever brukerens godkjenning.",
         {"path": (S, "Filsti", True), "content": (S, "Innhold", True), "overwrite": ("boolean", "Erstatt hvis den finnes", False)}, "write", write_file),
    Tool("delete_path", "Flytter en fil eller mappe til papirkurven. Krever brukerens godkjenning.", {"path": (S, "Sti", True)}, "delete", delete_path),
    Tool("screen_look", "Tar et skjermbilde og beskriver det (lokal modell). Gir også skjermstørrelse og liste over åpne vinduer. Krever godkjenning.",
         {"question": (S, "Valgfritt spørsmål om skjermen", False)}, "screen", _scr("screen_look")),
    Tool("focus_window", "Bytter til et åpent vindu der tittelen inneholder teksten. Foretrekk dette og tastatur framfor museklikk. Krever godkjenning.",
         {"title": (S, "Del av vindustittelen", True)}, "control", _scr("focus_window")),
    Tool("mouse_click", "Klikker med musen på skjermkoordinat (x,y) i hele skjermens piksler. Krever godkjenning.",
         {"x": ("integer", "x-piksel", True), "y": ("integer", "y-piksel", True), "button": (S, "left eller right", False), "double": ("boolean", "Dobbeltklikk", False)}, "control", _scr("mouse_click")),
    Tool("scroll", "Ruller musehjulet (positivt opp, negativt ned, maks 20). Krever godkjenning.", {"amount": ("integer", "Antall steg", True)}, "control", _scr("scroll")),
    Tool("type_text", "Skriver tekst med tastaturet i det aktive vinduet (maks 500 tegn). Krever godkjenning.", {"text": (S, "Teksten", True)}, "control", _scr("type_text")),
    Tool("press_key", "Trykker en tast eller kombinasjon, f.eks. enter, tab, ctrl+c, alt+tab, ctrl+shift+n. Windows-tasten og Alt+F4 er blokkert. Krever godkjenning.",
         {"keys": (S, "Tastekombinasjon", True)}, "control", _scr("press_key")),
]}


def describe(name: str, args: dict) -> str:
    """Kort, ærlig beskrivelse av hva som skjer, vist i godkjenningsboksen."""
    a = args or {}
    if name in ("screen_look", "focus_window", "mouse_click", "scroll", "type_text", "press_key"):
        from . import screen
        return screen.describe(name, a)
    return {"write_file": f"Skrive filen {a.get('path')} ({len(str(a.get('content', '')))} tegn)",
            "delete_path": f"Flytte {a.get('path')} til papirkurven",
            "open_app": f"Åpne programmet {a.get('name')}", "open_url": f"Åpne {a.get('url')} i nettleseren",
            "open_path": f"Åpne {a.get('path')}", "list_dir": f"Liste mappen {a.get('path')}",
            "read_file": f"Lese filen {a.get('path')}", "search_files": f"Søke etter «{a.get('query')}»",
            "remember": f"Huske: {str(a.get('text', ''))[:80]}", "web_search": f"Søke på nettet etter «{a.get('query')}»", "fetch_url": f"Lese siden {a.get('url')}"}.get(name, name)


def run_tool(name: str, args) -> str:
    t = TOOLS.get(name)
    if t and not t.available:
        raise ToolError("Skjermstyring er av. Brukeren må slå den på i Innstillinger.")
    if not t:
        raise ToolError(f"Ukjent verktøy «{name}». Tilgjengelige: " + ", ".join(TOOLS))
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except Exception:
            raise ToolError("Argumentene må være gyldig JSON")
    if not isinstance(args, dict):
        raise ToolError("Argumentene må være et objekt")
    missing = [k for k, v in t.params.items() if v[2] and k not in args]
    if missing:
        raise ToolError("Mangler argument: " + ", ".join(missing))
    return t.fn(args)
