"""Skjermstyring (fase 3): se skjermen og styre mus og tastatur. ALT er lokalt, ingenting sendes ut.

Sikkerhet:
- Av som standard. Må slås på i Innstillinger (pref screen_control = on).
- Hver handling krever godkjenning i appen (risk "screen" / "control").
- Nødstopp: står musepekeren i øvre venstre hjørne avbrytes alt (som pyautogui sitt failsafe).
- Grenser: maks 30 handlinger i minuttet, tekst maks 500 tegn, koordinater må ligge på skjermen.
- Blokkerte taster: alt med Windows-tasten, Alt+F4, Ctrl+Alt+Delete.
- Skriving og museklikk nektes når det aktive vinduet ser ut som passord-, BankID- eller innloggingsvindu.
- Skjermbildet beskrives av en lokal visjonsmodell i Ollama og lagres bare lokalt (~/.nexus-ai/screens/last.png).
"""
import base64
import ctypes
import json
import sys
import time
import zlib
from collections import deque
from pathlib import Path

import httpx

from . import config, db


class ScreenError(Exception):
    pass


MAX_PER_MIN = 30
MAX_TEXT = 500
SENSITIVE = ("passord", "password", "passkey", "bankid", "vipps", "pin-kode", "sign in", "logg inn", "credential")
VISION_MODELS = ("moondream", "llava-phi3", "llava", "minicpm-v", "gemma3", "llama3.2-vision")

_times: deque = deque()
_backend = None


def enabled() -> bool:
    with db.conn() as c:
        r = c.execute("SELECT value FROM settings WHERE key='pref:screen_control'").fetchone()
    return bool(r and r["value"] == "on")


# ---------- validering (ren logikk, testes på alle plattformer) ----------

MODS = {"ctrl", "alt", "shift"}
NAMED = {"enter", "tab", "esc", "space", "backspace", "delete", "up", "down", "left", "right", "home", "end", "pageup", "pagedown"}


def parse_key(spec: str) -> list[str]:
    """«ctrl+c» -> ["ctrl", "c"]. Kaster ScreenError for ukjente eller blokkerte taster."""
    parts = [p.strip().lower() for p in str(spec).replace(" ", "").split("+") if p.strip()]
    if not parts or len(parts) > 4:
        raise ScreenError("Ugyldig tastekombinasjon")
    if len(set(parts)) != len(parts):
        raise ScreenError("Ugyldig tastekombinasjon")
    for p in parts:
        if p in ("win", "windows", "meta", "super", "cmd"):
            raise ScreenError("Windows-tasten er blokkert av sikkerhetsgrunner")
        ok = p in MODS or p in NAMED or (len(p) == 1 and p.isalnum()) or (p[0] == "f" and p[1:].isdigit() and 1 <= int(p[1:]) <= 12)
        if not ok:
            raise ScreenError(f"Ukjent tast: {p}")
    keys = [p for p in parts if p not in MODS]
    if len(keys) != 1:
        raise ScreenError("Bruk modifikatorer (ctrl, alt, shift) pluss nøyaktig én tast")
    s = set(parts)
    if s >= {"alt", "f4"}:
        raise ScreenError("Alt+F4 er blokkert")
    if "delete" in s and {"ctrl", "alt"} <= s:
        raise ScreenError("Ctrl+Alt+Delete er blokkert")
    return parts


def check_text(text: str) -> str:
    t = str(text)
    if not t:
        raise ScreenError("Ingen tekst å skrive")
    if len(t) > MAX_TEXT:
        raise ScreenError(f"Teksten er for lang (maks {MAX_TEXT} tegn)")
    if any(ord(ch) < 32 and ch not in "\n\t" for ch in t):
        raise ScreenError("Teksten inneholder kontrolltegn")
    return t


def check_point(x, y, size: tuple[int, int]) -> tuple[int, int]:
    try:
        xi, yi = int(x), int(y)
    except (TypeError, ValueError):
        raise ScreenError("x og y må være heltall")
    w, h = size
    if not (0 <= xi < w and 0 <= yi < h):
        raise ScreenError(f"Punktet ({xi},{yi}) ligger utenfor skjermen ({w}x{h})")
    return xi, yi


def is_sensitive(title: str) -> bool:
    t = (title or "").lower()
    return any(s in t for s in SENSITIVE)


def rate_limit(now: float | None = None) -> None:
    now = time.time() if now is None else now
    while _times and now - _times[0] > 60:
        _times.popleft()
    if len(_times) >= MAX_PER_MIN:
        raise ScreenError(f"For mange handlinger (maks {MAX_PER_MIN} per minutt). Vent litt.")
    _times.append(now)


# ---------- plattform ----------

def get_backend():
    global _backend
    if _backend is None:
        if sys.platform != "win32":
            raise ScreenError("Skjermstyring støttes bare på Windows")
        _backend = Win32Backend()
    return _backend


def set_backend(b) -> None:
    global _backend
    _backend = b


def _guard_control(b, need_safe_window: bool = True) -> None:
    if not enabled():
        raise ScreenError("Skjermstyring er av. Slå den på i Innstillinger først.")
    if b.cursor_pos() == (0, 0):
        raise ScreenError("Nødstopp: musepekeren står i øvre venstre hjørne. Flytt den bort for å fortsette.")
    if need_safe_window and is_sensitive(b.active_title()):
        raise ScreenError("Det aktive vinduet ser ut som passord/innlogging. Agenten rører det ikke. Gjør det selv.")
    rate_limit()


def _png(rgb: bytes, w: int, h: int) -> bytes:
    import struct
    raw = b"".join(b"\x00" + rgb[y * w * 3:(y + 1) * w * 3] for y in range(h))
    def chunk(t: bytes, d: bytes) -> bytes:
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b"")


def screens_dir() -> Path:
    d = Path.home() / ".nexus-ai" / "screens"
    d.mkdir(parents=True, exist_ok=True)
    return d


def last_path() -> Path:
    return screens_dir() / "last.png"


class Win32Backend:
    """Ren ctypes mot user32/gdi32. Ingen ekstra pakker. IKKE testet på ekte Windows ennå."""

    def __init__(self):
        from ctypes import wintypes
        self.w = wintypes
        self.u = ctypes.windll.user32
        self.g = ctypes.windll.gdi32
        try:
            self.u.SetProcessDPIAware()
        except Exception:
            pass

    # --- info
    def size(self) -> tuple[int, int]:
        return self.u.GetSystemMetrics(0), self.u.GetSystemMetrics(1)

    def cursor_pos(self) -> tuple[int, int]:
        p = self.w.POINT()
        self.u.GetCursorPos(ctypes.byref(p))
        return p.x, p.y

    def active_title(self) -> str:
        h = self.u.GetForegroundWindow()
        n = self.u.GetWindowTextLengthW(h)
        buf = ctypes.create_unicode_buffer(n + 1)
        self.u.GetWindowTextW(h, buf, n + 1)
        return buf.value

    def windows(self) -> list[str]:
        out: list[str] = []
        CB = ctypes.WINFUNCTYPE(ctypes.c_bool, self.w.HWND, self.w.LPARAM)

        def cb(h, _):
            if self.u.IsWindowVisible(h):
                n = self.u.GetWindowTextLengthW(h)
                if n:
                    buf = ctypes.create_unicode_buffer(n + 1)
                    self.u.GetWindowTextW(h, buf, n + 1)
                    out.append(buf.value)
            return True
        self.u.EnumWindows(CB(cb), 0)
        return out

    def focus(self, title: str) -> str:
        found: list = []
        CB = ctypes.WINFUNCTYPE(ctypes.c_bool, self.w.HWND, self.w.LPARAM)

        def cb(h, _):
            if self.u.IsWindowVisible(h):
                n = self.u.GetWindowTextLengthW(h)
                buf = ctypes.create_unicode_buffer(n + 1)
                self.u.GetWindowTextW(h, buf, n + 1)
                if n and title.lower() in buf.value.lower():
                    found.append((h, buf.value))
                    return False
            return True
        self.u.EnumWindows(CB(cb), 0)
        if not found:
            raise ScreenError(f"Fant ikke noe vindu med «{title}»")
        self.u.ShowWindow(found[0][0], 9)  # SW_RESTORE
        self.u.SetForegroundWindow(found[0][0])
        return found[0][1]

    # --- skjermbilde (GDI, nedskalert til maks 1024 bred av Windows selv)
    def screenshot(self, max_w: int = 1024) -> tuple[bytes, int, int]:
        W, H = self.size()
        tw = min(W, max_w)
        th = max(1, int(H * tw / W))
        hdc = self.u.GetDC(0)
        mdc = self.g.CreateCompatibleDC(hdc)
        bmp = self.g.CreateCompatibleBitmap(hdc, tw, th)
        old = self.g.SelectObject(mdc, bmp)
        self.g.SetStretchBltMode(mdc, 4)  # HALFTONE
        self.g.StretchBlt(mdc, 0, 0, tw, th, hdc, 0, 0, W, H, 0x00CC0020)  # SRCCOPY

        class BIH(ctypes.Structure):
            _fields_ = [("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_int32), ("biHeight", ctypes.c_int32),
                        ("biPlanes", ctypes.c_uint16), ("biBitCount", ctypes.c_uint16), ("biCompression", ctypes.c_uint32),
                        ("biSizeImage", ctypes.c_uint32), ("biXPelsPerMeter", ctypes.c_int32), ("biYPelsPerMeter", ctypes.c_int32),
                        ("biClrUsed", ctypes.c_uint32), ("biClrImportant", ctypes.c_uint32)]
        bi = BIH(ctypes.sizeof(BIH), tw, -th, 1, 24, 0, 0, 0, 0, 0, 0)
        stride = (tw * 3 + 3) & ~3
        buf = ctypes.create_string_buffer(stride * th)
        self.g.GetDIBits(mdc, bmp, 0, th, buf, ctypes.byref(bi), 0)
        self.g.SelectObject(mdc, old)
        self.g.DeleteObject(bmp)
        self.g.DeleteDC(mdc)
        self.u.ReleaseDC(0, hdc)
        raw = buf.raw
        rgb = bytearray(tw * th * 3)
        for y in range(th):
            bgr = raw[y * stride:y * stride + tw * 3]
            o = y * tw * 3
            rgb[o:o + tw * 3:3] = bgr[2::3]
            rgb[o + 1:o + tw * 3:3] = bgr[1::3]
            rgb[o + 2:o + tw * 3:3] = bgr[0::3]
        return _png(bytes(rgb), tw, th), tw, th

    # --- input (SendInput)
    def _send(self, *inputs) -> None:
        arr = (INPUT * len(inputs))(*inputs)
        if self.u.SendInput(len(inputs), arr, ctypes.sizeof(INPUT)) != len(inputs):
            raise ScreenError("Windows avviste tastatur-/museinput (kanskje et program med administratorrettigheter er i fokus)")

    def move(self, x: int, y: int) -> None:
        self.u.SetCursorPos(int(x), int(y))

    def click(self, x: int, y: int, button: str = "left", double: bool = False) -> None:
        self.move(x, y)
        time.sleep(0.05)
        down, up = {"left": (0x2, 0x4), "right": (0x8, 0x10)}[button]
        for _ in range(2 if double else 1):
            self._send(_mouse(down), _mouse(up))
            time.sleep(0.06)

    def scroll(self, amount: int) -> None:
        self._send(_mouse(0x800, amount * 120))

    def type_text(self, text: str) -> None:
        for ch in text.replace("\r\n", "\n"):
            if ch == "\n":
                self.press(["enter"]); continue
            if ch == "\t":
                self.press(["tab"]); continue
            units = [int.from_bytes(ch.encode("utf-16-le")[i:i + 2], "little") for i in range(0, len(ch.encode("utf-16-le")), 2)]
            for u in units:
                self._send(_key(0, u, 0x4), _key(0, u, 0x4 | 0x2))
            time.sleep(0.01)

    VK = {"enter": 0x0D, "tab": 0x09, "esc": 0x1B, "space": 0x20, "backspace": 0x08, "delete": 0x2E, "up": 0x26, "down": 0x28,
          "left": 0x25, "right": 0x27, "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
          "ctrl": 0x11, "alt": 0x12, "shift": 0x10}

    def _vk(self, k: str) -> int:
        if k in self.VK:
            return self.VK[k]
        if len(k) == 1:
            return ord(k.upper())
        return 0x70 + int(k[1:]) - 1  # F1..F12

    def press(self, parts: list[str]) -> None:
        vks = [self._vk(p) for p in parts]
        for v in vks:
            self._send(_key(v, 0, 0))
        for v in reversed(vks):
            self._send(_key(v, 0, 0x2))


# ctypes-strukturer for SendInput (definert på toppnivå, brukes bare på Windows)
class _MI(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long), ("mouseData", ctypes.c_ulong), ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong), ("dwExtraInfo", ctypes.c_void_p)]


class _KI(ctypes.Structure):
    _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort), ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong),
                ("dwExtraInfo", ctypes.c_void_p)]


class _IU(ctypes.Union):
    _fields_ = [("mi", _MI), ("ki", _KI)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong), ("u", _IU)]


def _mouse(flags: int, data: int = 0) -> INPUT:
    return INPUT(0, _IU(mi=_MI(0, 0, data & 0xFFFFFFFF, flags, 0, None)))


def _key(vk: int, scan: int, flags: int) -> INPUT:
    return INPUT(1, _IU(ki=_KI(vk, scan, flags, 0, None)))


# ---------- verktøyene ----------

def _installed_vision() -> str | None:
    try:
        r = httpx.get(f"{config.OLLAMA_URL}/api/tags", timeout=5)
        names = [m["name"] for m in r.json().get("models", [])]
    except Exception:
        return None
    for pref in VISION_MODELS:
        for n in names:
            if n.split(":")[0] == pref or n.startswith(pref):
                return n
    return None


def screen_look(a: dict) -> str:
    b = get_backend()
    if not enabled():
        raise ScreenError("Skjermstyring er av. Slå den på i Innstillinger først.")
    if is_sensitive(b.active_title()):
        raise ScreenError("Det aktive vinduet ser ut som passord/innlogging. Agenten tar ikke skjermbilde av det.")
    rate_limit()
    png, w, h = b.screenshot()
    last_path().write_bytes(png)
    W, H = b.size()
    wins = b.windows()[:25]
    head = f"Skjermen er {W}x{H}. Aktivt vindu: «{b.active_title()}». Åpne vinduer: " + "; ".join(wins)
    model = _installed_vision()
    if not model:
        return head + "\n(Ingen visjonsmodell er installert i Ollama, så skjermbildet kan ikke beskrives. Last ned moondream under Models.)"
    q = str(a.get("question") or "Beskriv hva som vises på skjermen, og nevn knapper, felt og tekst du ser.")[:300]
    try:
        r = httpx.post(f"{config.OLLAMA_URL}/api/chat", timeout=300, json={
            "model": model, "stream": False, "keep_alive": "5m", "options": {"num_ctx": 2048, "temperature": 0.2, "num_predict": 400},
            "messages": [{"role": "user", "content": q, "images": [base64.b64encode(png).decode()]}]})
        r.raise_for_status()
        desc = r.json().get("message", {}).get("content", "").strip()
    except Exception as e:
        raise ScreenError(f"Visjonsmodellen {model} feilet: {e}")
    return f"{head}\nSkjermbildet er nedskalert til {w}x{h}; koordinatene du bruker må være i hele skjermens {W}x{H}.\nBeskrivelse fra {model}: {desc}"


def focus_window(a: dict) -> str:
    b = get_backend()
    _guard_control(b, need_safe_window=False)
    t = str(a.get("title", "")).strip()
    if len(t) < 2:
        raise ScreenError("Oppgi minst 2 tegn av vindustittelen")
    return "Satte fokus på «" + b.focus(t) + "»"


def mouse_click(a: dict) -> str:
    b = get_backend()
    _guard_control(b)
    x, y = check_point(a.get("x"), a.get("y"), b.size())
    btn = str(a.get("button") or "left").lower()
    if btn not in ("left", "right"):
        raise ScreenError("button må være left eller right")
    b.click(x, y, btn, bool(a.get("double")))
    return f"Klikket {btn}{' (dobbelt)' if a.get('double') else ''} på ({x},{y})"


def scroll(a: dict) -> str:
    b = get_backend()
    _guard_control(b)
    try:
        n = max(-20, min(20, int(a.get("amount", 0))))
    except (TypeError, ValueError):
        raise ScreenError("amount må være et heltall")
    b.scroll(n)
    return f"Rullet {n}"


def type_text(a: dict) -> str:
    b = get_backend()
    _guard_control(b)
    t = check_text(a.get("text", ""))
    b.type_text(t)
    return f"Skrev {len(t)} tegn"


def press_key(a: dict) -> str:
    b = get_backend()
    parts = parse_key(a.get("keys", ""))
    _guard_control(b)
    b.press(parts)
    return "Trykket " + "+".join(parts)


def describe(name: str, a: dict) -> str:
    return {"screen_look": "Ta et skjermbilde og beskrive det med en lokal modell (lagres bare på PC-en)",
            "focus_window": f"Bytte til vinduet «{a.get('title')}»",
            "mouse_click": f"Klikke {a.get('button') or 'venstre'} på ({a.get('x')},{a.get('y')})",
            "scroll": f"Rulle {a.get('amount')}",
            "type_text": f"Skrive «{str(a.get('text', ''))[:60]}»{'…' if len(str(a.get('text', ''))) > 60 else ''}",
            "press_key": f"Trykke {a.get('keys')}"}.get(name, name)
