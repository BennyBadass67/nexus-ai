"""Bla i Ollamas offentlige modellbibliotek (ollama.com). Henter og tolker HTML-sidene.
Ollama har ikke et offisielt søke-API, så tolkingen kan gå i stykker hvis siden endres.
Appen kan da fortsatt laste ned ved å skrive modellnavn manuelt."""
import html
import re
import time

import httpx

BASE = "https://ollama.com"
_cache: dict[str, tuple[float, object]] = {}
TTL = 600


def _strip(s: str) -> str:
    s = re.sub(r"<svg.*?</svg>", "", s, flags=re.S)
    return re.sub(r"\s+", " ", s).strip()


def parse_search(page: str) -> list[dict]:
    out = []
    for li in re.findall(r"<li\s[^>]*>(.*?)</li>", page, flags=re.S):
        m = re.search(r'href="/library/([^"/]+)"', li)
        if not m:
            continue
        li = _strip(li)
        desc = re.search(r'<p class="[^"]*">(.*?)</p>', li)
        dl = re.search(r'title="([\d,]+) downloads"', li)
        sizes = re.findall(r'bg-\[#ddf4ff\][^>]*>([^<]+)</span>', li)
        caps = re.findall(r'bg-indigo-50[^>]*>([^<]+)</span>', li)
        pulls = re.search(r"([\d.]+)([KMB]?)\s*</span>\s*<span[^>]*>(?:&nbsp;|\s)*Pulls", li)
        mult = {"": 1, "K": 1e3, "M": 1e6, "B": 1e9}
        out.append({
            "name": m.group(1),
            "pulls": int(float(pulls.group(1)) * mult[pulls.group(2)]) if pulls else 0,
            "description": html.unescape(desc.group(1)) if desc else "",
            "downloads": int(dl.group(1).replace(",", "")) if dl else 0,
            "sizes": sizes, "capabilities": caps,
        })
    return out


def _to_gb(txt: str) -> float:
    n = float(re.sub(r"[^\d.]", "", txt) or 0)
    return n / 1000 if txt.strip().upper().endswith("MB") else n


def parse_tags(page: str, model: str) -> list[dict]:
    seen: dict[str, dict] = {}
    pat = re.compile(r'href="/library/(' + re.escape(model) + r':[^"]+)".*?([\d.]+\s?[MG]B)', re.S)
    for chunk in page.split('<div class="group px-4 py-3">')[1:]:
        m = pat.search(chunk)
        if m and m.group(1) not in seen:
            seen[m.group(1)] = {"tag": m.group(1), "size_gb": round(_to_gb(m.group(2)), 2)}
    return sorted(seen.values(), key=lambda t: t["size_gb"])


async def _get(path: str) -> str:
    async with httpx.AsyncClient(timeout=15, follow_redirects=True,
                                 headers={"User-Agent": "NEXUS-AI/0.1"}) as c:
        r = await c.get(BASE + path)
        r.raise_for_status()
        return r.text


async def search(q: str) -> list[dict]:
    key = "s:" + q.lower()
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < TTL:
        return hit[1]  # type: ignore
    res = parse_search(await _get("/search?q=" + httpx.QueryParams({"q": q})["q"]))
    # kun lokale modeller (ikke skybaserte "cloud"-oppføringer)
    res = [m for m in res if "cloud" not in [s.lower() for s in m["sizes"]]
           and "cloud" not in [c.lower() for c in m["capabilities"]]]
    _cache[key] = (time.time(), res)
    return res


async def tags(model: str) -> list[dict]:
    key = "t:" + model
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < TTL:
        return hit[1]  # type: ignore
    res = [t for t in parse_tags(await _get(f"/library/{model}/tags"), model)
           if "cloud" not in t["tag"]]
    _cache[key] = (time.time(), res)
    return res


# ---- kategorier, utledet fra ekte data fra Ollama-registeret (egenskaper, beskrivelse, størrelser) ----
CATEGORIES = [("chat", "Chat"), ("koding", "Koding"), ("bilde", "Bilder"), ("verktoy", "Verktøy/agent"), ("resonnering", "Resonnering"),
              ("flerspraklig", "Flerspråklig"), ("liten", "Liten (≤4B)"), ("embedding", "Embedding")]
_KW = {
    "koding": r"\b(code|coding|coder|programming|developer|software)\b",
    "flerspraklig": r"\b(multilingual|languages|translation)\b",
    "chat": r"\b(chat|conversational|instruction|assistant|general[- ]purpose|general)\b",
}


def _bparams(label: str) -> float | None:
    m = re.fullmatch(r"(?:e)?(\d+(?:\.\d+)?)([bm])", label.strip().lower())
    if not m:
        return None
    return float(m.group(1)) * (1 if m.group(2) == "b" else 0.001)


def categorize(m: dict) -> list[str]:
    caps = {c.lower() for c in m.get("capabilities", [])}
    text = (m.get("name", "") + " " + m.get("description", "")).lower()
    out = []
    if "embedding" in caps:
        out.append("embedding")
    else:
        if re.search(_KW["chat"], text) or not caps - {"tools"}:
            out.append("chat")
        if re.search(_KW["koding"], text):
            out.append("koding")
        if re.search(_KW["flerspraklig"], text):
            out.append("flerspraklig")
    if "vision" in caps:
        out.append("bilde")
    if "tools" in caps:
        out.append("verktoy")
    if "thinking" in caps:
        out.append("resonnering")
    sizes = [x for x in (_bparams(s) for s in m.get("sizes", [])) if x is not None]
    if sizes and min(sizes) <= 4 and "embedding" not in caps:
        out.append("liten")
    return out


async def browse(q: str = "") -> list[dict]:
    """Hele det lokale biblioteket fra ollama.com/library (sortert etter popularitet) når q er tom, ellers søk."""
    if q.strip():
        return await search(q)
    key = "all"
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < TTL:
        return hit[1]  # type: ignore
    res = parse_search(await _get("/library?sort=popular"))
    res = [m for m in res if m["sizes"] and "cloud" not in [s.lower() for s in m["sizes"]]
           and "cloud" not in [c.lower() for c in m["capabilities"]]]
    _cache[key] = (time.time(), res)
    return res
