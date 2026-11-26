"""Maskinvaredeteksjon, vurdering av modeller mot PC-en og anbefalinger per bruksområde."""
import asyncio
import os
import platform
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, asdict
from typing import Optional

from . import library

GB = 1024 ** 3


@dataclass
class Hardware:
    cpu: str
    cores: int
    ram_gb: float
    gpu: Optional[str]
    vram_gb: float          # 0 = ingen dedikert GPU funnet
    gpu_vendor: Optional[str]
    os: str


def _run(cmd: list[str], timeout: int = 6) -> str:
    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                              creationflags=flags).stdout.strip()
    except Exception:
        return ""


def parse_nvidia_smi(out: str) -> tuple[Optional[str], float]:
    """Linje: 'NVIDIA GeForce GTX 1650, 4096' (MiB). Tar GPU-en med mest VRAM."""
    best: tuple[Optional[str], float] = (None, 0.0)
    for line in out.splitlines():
        m = re.match(r"\s*(.+?),\s*(\d+)\s*$", line)
        if m and int(m.group(2)) / 1024 > best[1]:
            best = (m.group(1).strip(), round(int(m.group(2)) / 1024, 1))
    return best


def _ram_gb() -> float:
    if sys.platform == "win32":
        import ctypes

        class MS(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("sullAvailExtendedVirtual", ctypes.c_ulonglong)]
        s = MS(); s.dwLength = ctypes.sizeof(MS)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(s))  # type: ignore
        return round(s.ullTotalPhys / GB, 1)
    try:
        return round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / GB, 1)
    except Exception:
        return 8.0


def _cpu_name() -> str:
    if sys.platform == "win32":
        try:
            import winreg
            k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
            return winreg.QueryValueEx(k, "ProcessorNameString")[0].strip()
        except Exception:
            pass
    try:
        for l in open("/proc/cpuinfo"):
            if l.startswith("model name"):
                return l.split(":", 1)[1].strip()
    except Exception:
        pass
    return platform.processor() or "ukjent CPU"


def detect() -> Hardware:
    gpu, vram, vendor = None, 0.0, None
    if shutil.which("nvidia-smi"):
        gpu, vram = parse_nvidia_smi(_run(["nvidia-smi", "--query-gpu=name,memory.total",
                                           "--format=csv,noheader,nounits"]))
        if gpu:
            vendor = "nvidia"
    if not gpu and sys.platform == "win32":
        out = _run(["powershell", "-NoProfile", "-Command",
                    "(Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name) -join '|'"])
        names = [n for n in out.split("|") if n]
        discrete = [n for n in names if re.search(r"nvidia|radeon rx|geforce|arc", n, re.I)]
        gpu = (discrete or names or [None])[0]
        if gpu:
            vendor = "amd" if re.search(r"amd|radeon", gpu, re.I) else "other"
            # WMI gir ikke pålitelig VRAM (>4 GB kappes). Behandles som ukjent => forsiktig vurdering.
    return Hardware(_cpu_name(), os.cpu_count() or 1, _ram_gb(), gpu, vram, vendor, platform.system())


_hw: Optional[Hardware] = None


def hardware(refresh: bool = False) -> Hardware:
    global _hw
    if _hw is None or refresh:
        _hw = detect()
    return _hw


OVERHEAD = 1.25  # kontekst/KV-cache og runtime kommer oppå filstørrelsen


def rate(size_gb: float, hw: Hardware) -> dict:
    """green = passer og går raskt, yellow = går men tregt/tungt, red = for stor."""
    need = size_gb * OVERHEAD
    if hw.vram_gb > 0 and hw.gpu_vendor == "nvidia":
        if need <= hw.vram_gb * 0.92:
            return {"level": "green", "reason": f"Passer helt i GPU-minnet ({hw.vram_gb:g} GB). Raskt."}
        if need <= hw.vram_gb * 0.9 + hw.ram_gb * 0.4:
            return {"level": "yellow", "reason": "Deles mellom GPU og RAM. Fungerer, men tregere (ca. 3-8 tokens/sek)."}
        return {"level": "red", "reason": f"For stor for {hw.ram_gb:g} GB RAM. Kan krasje eller være ubrukelig treg."}
    # CPU-only (eller GPU uten Ollama-støtte vi kan stole på)
    if need <= hw.ram_gb * 0.25:
        return {"level": "green", "reason": "Liten nok til å gå greit på prosessoren."}
    if need <= hw.ram_gb * 0.55:
        return {"level": "yellow", "reason": "Går, men merkbart tregt uten kraftig GPU."}
    return {"level": "red", "reason": f"For stor for {hw.ram_gb:g} GB RAM."}


def est_size_from_params(label: str) -> Optional[float]:
    """'3b' -> ca. 2.0 GB (Q4). Brukes for størrelsesbrikker i søkelisten."""
    m = re.fullmatch(r"(?:e)?(\d+(?:\.\d+)?)([bm])", label.strip().lower())
    if not m:
        return None
    n = float(m.group(1)) / (1000 if m.group(2) == "m" else 1)
    return round(n * 0.62 + 0.25, 2)


# Bruksområder -> modellfamilier (rekkefølge = foretrukket). Tilgjengelighet sjekkes live mot ollama.com.
TOPICS = [
    {"id": "chat", "title": "Hverdag og chat", "desc": "Spørsmål, skriving, oppsummering",
     "families": ["qwen3", "gemma3", "llama3.2", "qwen2.5"]},
    {"id": "code", "title": "Koding", "desc": "Skrive og forklare kode",
     "families": ["qwen2.5-coder", "deepseek-coder", "codegemma"]},
    {"id": "reason", "title": "Tenking og logikk", "desc": "Matte, planlegging, steg-for-steg",
     "families": ["deepseek-r1", "qwen3", "phi4-mini-reasoning"]},
    {"id": "fast", "title": "Raskest mulig", "desc": "Små modeller som svarer nesten umiddelbart",
     "families": ["llama3.2", "gemma3", "qwen2.5", "smollm2"]},
    {"id": "vision", "title": "Forstå bilder", "desc": "Beskrive og lese bilder",
     "families": ["llava", "moondream", "gemma3", "minicpm-v"]},
]
_PLAIN = re.compile(r"^[a-z0-9.\-]+:(\d+(?:\.\d+)?[bm])$")


def pick(tags_by_family: dict[str, list[dict]], hw: Hardware) -> dict | None:
    """Beste modell som får grønn, ellers minste gule. Størrelse ~ kvalitet innen en liste."""
    cands = []
    for fam_rank, (fam, tags) in enumerate(tags_by_family.items()):
        for t in tags:
            if not _PLAIN.match(t["tag"]):
                continue
            r = rate(t["size_gb"], hw)
            cands.append({**t, **r, "family": fam, "fam_rank": fam_rank})
    greens = [c for c in cands if c["level"] == "green"]
    if greens:
        # Første familie som har noe grønt, største grønne modell i den. Mindre enn 1B er unødvendig svak.
        ranks = sorted({g["fam_rank"] for g in greens})[:2]   # de to foretrukne familiene med noe grønt
        pool = [g for g in greens if g["fam_rank"] in ranks]
        return max(pool, key=lambda c: (c["size_gb"], -c["fam_rank"]))
    yellows = [c for c in cands if c["level"] == "yellow"]
    return min(yellows, key=lambda c: c["size_gb"]) if yellows else None


async def recommendations(hw: Hardware) -> list[dict]:
    async def one(topic: dict) -> dict:
        tb: dict[str, list[dict]] = {}
        res = await asyncio.gather(*[library.tags(f) for f in topic["families"]], return_exceptions=True)
        for fam, r in zip(topic["families"], res):
            if isinstance(r, list) and r:
                tb[fam] = r
        best = pick(tb, hw)
        return {"id": topic["id"], "title": topic["title"], "desc": topic["desc"], "model": best}
    return await asyncio.gather(*[one(t) for t in TOPICS])


def hw_dict(hw: Hardware) -> dict:
    return asdict(hw)
