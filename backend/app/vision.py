"""v1.7: Bildevedlegg i chat. Bildene sendes bare til en lokal synsmodell i Ollama. De lagres ikke i databasen."""
import base64
import binascii

from fastapi import HTTPException

MAX_IMAGES = 3
MAX_BYTES = 4_000_000
VISION_HINTS = ("moondream", "llava", "minicpm-v", "gemma3", "llama3.2-vision", "qwen2.5vl", "qwen2-vl", "-vl", "bakllava", "granite3.2-vision")


def is_vision(model: str) -> bool:
    m = model.lower()
    return not m.startswith("cloud:") and any(h in m for h in VISION_HINTS)


def _kind(b: bytes) -> str | None:
    if b.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if b.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
        return "webp"
    if b[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    return None


def check(model: str, images: list[str] | None) -> list[str]:
    """Validerer og normaliserer (base64 uten data:-prefiks). Kaster 422 med klar norsk melding."""
    if not images:
        return []
    if model.lower().startswith("cloud:"):
        raise HTTPException(422, "Bilder sendes bare til lokale synsmodeller, ikke til skyen. Velg en lokal modell som moondream.")
    if not is_vision(model):
        raise HTTPException(422, f"Modellen {model} kan ikke se bilder. Last ned en synsmodell under Models (f.eks. moondream, 1,7 GB) og velg den.")
    if len(images) > MAX_IMAGES:
        raise HTTPException(422, f"Maks {MAX_IMAGES} bilder per melding.")
    out = []
    for s in images:
        s = s.split(",", 1)[1] if s.startswith("data:") and "," in s else s
        try:
            raw = base64.b64decode(s, validate=True)
        except (binascii.Error, ValueError):
            raise HTTPException(422, "Ugyldig bildedata.")
        if len(raw) > MAX_BYTES:
            raise HTTPException(422, "Bildet er for stort (maks 4 MB).")
        if not _kind(raw):
            raise HTTPException(422, "Bare PNG, JPEG, WebP og GIF støttes.")
        out.append(s)
    return out
