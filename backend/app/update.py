"""Oppdatering i appen: sjekk latest.json, last ned installeren, verifiser den og start den.
Installeren (NSIS) avslutter NEXUS, bytter filene og starter appen på nytt. Alle feil vises for brukeren."""
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException

router = APIRouter()
APP_VERSION = os.environ.get("NEXUS_VERSION", "dev")
UPDATE_URL = os.environ.get("NEXUS_UPDATE_URL", "https://github.com/BennyBadass67/nexus-ai/releases/latest/download/latest.json")
ALLOWED_PREFIX = os.environ.get("NEXUS_UPDATE_ALLOW", "https://github.com/BennyBadass67/nexus-ai/releases/download/")
MIN_SIZE = int(os.environ.get("NEXUS_UPDATE_MIN_BYTES", str(5_000_000)))

STATE = {"state": "idle", "done": 0, "total": 0, "error": None, "path": None, "version": None}
_lock = threading.Lock()


def _vt(v: str):
    return tuple(int(x) for x in re.findall(r"\d+", v or "")[:3])


def _set(**kw):
    with _lock:
        STATE.update(kw)


async def fetch_latest() -> dict:
    out = {"current": APP_VERSION, "latest": None, "available": False, "url": None, "notes": "", "error": None}
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=10) as c:
            r = await c.get(UPDATE_URL)
            r.raise_for_status()
            j = r.json()
        out["latest"] = j.get("version")
        out["notes"] = (j.get("notes") or "")[:500]
        plat = (j.get("platforms") or {}).get("windows-x86_64") or {}
        out["url"] = plat.get("url")
        if APP_VERSION != "dev" and out["latest"]:
            out["available"] = _vt(out["latest"]) > _vt(APP_VERSION)
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"[:300]
    return out


@router.get("/api/update")
async def update_check():
    return await fetch_latest()


@router.get("/api/update/status")
def update_status():
    with _lock:
        return dict(STATE)


def launch_installer(path: Path) -> None:
    """Starter installeren uten at den blir barn av backend-prosessen (installeren dreper nexus-backend med taskkill /T)."""
    if sys.platform != "win32":
        raise RuntimeError("Installasjon i appen virker bare på Windows")
    # cmd /c start løsriver installeren fra prosesstreet vårt. /P = passiv (viser fremdrift), /R = start appen på nytt etterpå.
    subprocess.Popen(["cmd", "/c", "start", "", str(path), "/P", "/R"], creationflags=0x08000000, close_fds=True)


def _download(url: str, version: str) -> None:
    dest_dir = Path(tempfile.gettempdir()) / "nexus-update"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"NEXUS_AI_{version}_setup.exe"
    part = dest.with_suffix(".part")
    try:
        _set(state="downloading", done=0, total=0, error=None, path=None, version=version)
        with httpx.stream("GET", url, follow_redirects=True, timeout=httpx.Timeout(20, read=30)) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length") or 0)
            _set(total=total)
            got = 0
            with open(part, "wb") as f:
                for chunk in r.iter_bytes(256 * 1024):
                    f.write(chunk)
                    got += len(chunk)
                    _set(done=got)
        if total and got != total:
            raise RuntimeError(f"Nedlastingen ble avbrutt ({got} av {total} byte). Prøv igjen.")
        if got < MIN_SIZE:
            raise RuntimeError(f"Filen er for liten ({got} byte), ikke en gyldig installer.")
        with open(part, "rb") as f:
            if f.read(2) != b"MZ":
                raise RuntimeError("Filen er ikke en Windows-installer.")
        os.replace(part, dest)
        _set(state="launching", path=str(dest))
        launch_installer(dest)
        _set(state="started")
    except Exception as e:
        try:
            part.unlink(missing_ok=True)
        except OSError:
            pass
        msg = str(e) or type(e).__name__
        if isinstance(e, httpx.HTTPStatusError):
            msg = f"Serveren svarte {e.response.status_code}. Prøv igjen senere."
        elif isinstance(e, httpx.HTTPError):
            msg = "Nedlastingen ble avbrutt (nettverksfeil). Sjekk internett og prøv igjen. " + msg[:120]
        if state_path := STATE.get("path"):
            msg += f" Filen ligger her og kan kjøres manuelt: {state_path}"
        _set(state="error", error=msg[:400])


@router.post("/api/update/install")
async def update_install():
    with _lock:
        if STATE["state"] in ("downloading", "launching"):
            raise HTTPException(409, "Oppdatering pågår allerede")
    info = await fetch_latest()
    if info["error"]:
        raise HTTPException(502, "Kunne ikke sjekke oppdatering: " + info["error"])
    if not info["available"]:
        raise HTTPException(400, "Ingen nyere versjon å installere")
    url = info["url"] or ""
    if not url.startswith(ALLOWED_PREFIX) or not url.lower().endswith(".exe"):
        raise HTTPException(400, "Nedlastingsadressen er ikke fra NEXUS sin GitHub-release, avbrutt")
    _set(state="downloading", done=0, total=0, error=None, path=None, version=info["latest"])
    threading.Thread(target=_download, args=(url, info["latest"]), daemon=True).start()
    return {"ok": True, "version": info["latest"]}
