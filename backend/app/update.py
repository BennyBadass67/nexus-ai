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


def ulog(msg: str) -> None:
    """Logg til ~/.nexus-ai/updater.log (samme fil som appen bruker), så feil kan leses i ettertid."""
    try:
        d = Path.home() / ".nexus-ai"
        d.mkdir(parents=True, exist_ok=True)
        with open(d / "updater.log", "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + "backend: " + msg + "\n")
    except OSError:
        pass


def _spawn_detached(path: Path) -> bool:
    """Starter installeren via WMI (Win32_Process.Create), så den ikke er barn av backend/appen.
    Installerens egen taskkill /T mot nexus-ai/nexus-backend (og en jobb som lukkes med appen) kan ellers drepe selve installeren midt i."""
    import subprocess
    cmd = f'"{path}" /P /R'.replace("'", "''")
    ps = ("$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create "
          f"-Arguments @{{CommandLine='{cmd}'; CurrentDirectory='{str(path.parent)}'}}; "
          "if ($r.ReturnValue -ne 0) { exit 3 }; Write-Output $r.ProcessId")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], capture_output=True, text=True,
                             timeout=20, creationflags=0x0800_0000)
        ulog(f"WMI-start {path} -> rc={out.returncode} pid={out.stdout.strip()} err={out.stderr.strip()[:200]}")
        return out.returncode == 0
    except Exception as e:  # noqa: BLE001
        ulog(f"WMI-start feilet: {e}")
        return False


def launch_installer(path: Path) -> None:
    """Starter installeren frikoblet fra appen (WMI), med ShellExecute som reserve.
    /P = passiv (viser fremdrift), /R = start appen på nytt etterpå. Feil kastes, så de vises for brukeren."""
    if sys.platform != "win32":
        raise RuntimeError("Installasjon i appen virker bare på Windows")
    if _spawn_detached(path):
        return
    import ctypes
    ctypes.windll.shell32.ShellExecuteW.restype = ctypes.c_void_p
    rc = ctypes.windll.shell32.ShellExecuteW(None, "open", str(path), "/P /R", str(path.parent), 1)
    rc = rc or 0
    ulog(f"ShellExecute {path} -> {rc}")
    if rc <= 32:
        raise RuntimeError(f"Windows kunne ikke starte installasjonsfilen (kode {rc}). Dobbeltklikk filen manuelt: {path}")


def _download(url: str, version: str, launch: bool = True) -> None:
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
        if not launch:
            _set(state="ready", path=str(dest))
            ulog(f"lastet ned {dest} ({got} byte) i bakgrunnen, venter på at brukeren starter installasjonen")
            return
        _set(state="launching", path=str(dest))
        ulog(f"lastet ned {dest} ({got} byte), starter installer")
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
        ready = STATE["state"] == "ready" and STATE.get("path") and Path(STATE["path"]).exists()
        rpath, rver = STATE.get("path"), STATE.get("version")
    if ready:
        info = await fetch_latest()
        if info.get("available") and info["latest"] == rver:
            try:
                _set(state="launching")
                launch_installer(Path(rpath))
                _set(state="started")
            except Exception as e:
                _set(state="error", error=str(e)[:400])
                raise HTTPException(500, str(e)[:400])
            return {"ok": True, "version": rver}
        _set(state="idle", path=None)
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


def autoupdate_on() -> bool:
    from . import db
    with db.conn() as c:
        r = c.execute("SELECT value FROM settings WHERE key='pref:autoupdate'").fetchone()
    return (r["value"] if r else "on") != "off"


async def auto_tick() -> str:
    """Én runde av automatisk oppdatering: sjekk, og last ned i bakgrunnen (uten å starte installeren)."""
    if APP_VERSION == "dev" or not autoupdate_on():
        return "off"
    with _lock:
        cur = STATE["state"]
        if cur in ("downloading", "launching", "started"):
            return cur
        have = STATE.get("version") if cur == "ready" and STATE.get("path") and Path(STATE["path"]).exists() else None
    info = await fetch_latest()
    if info["error"] or not info["available"]:
        return "none"
    if have and have == info["latest"]:
        return "ready"
    url = info["url"] or ""
    if not url.startswith(ALLOWED_PREFIX) or not url.lower().endswith(".exe"):
        ulog("auto: ugyldig nedlastingsadresse, hopper over")
        return "bad-url"
    _set(state="downloading", done=0, total=0, error=None, path=None, version=info["latest"])
    threading.Thread(target=_download, args=(url, info["latest"], False), daemon=True).start()
    return "downloading"


async def auto_loop() -> None:
    import asyncio
    await asyncio.sleep(int(os.environ.get("NEXUS_AUTO_FIRST_DELAY", "20")))
    while True:
        try:
            await auto_tick()
        except Exception as e:  # aldri la bakgrunnssjekken ta ned appen
            ulog(f"auto: feil {e}")
        await asyncio.sleep(6 * 3600)
