import os
import sys
from pathlib import Path

DATA_DIR = Path(os.environ.get("NEXUS_DATA_DIR", Path.home() / ".nexus-ai"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = Path(os.environ.get("NEXUS_DB", DATA_DIR / "nexus.db"))
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
PORT = int(os.environ.get("NEXUS_PORT", "8765"))
if getattr(sys, "frozen", False):  # PyInstaller-pakket
    _default_front = Path(sys._MEIPASS) / "frontend" / "dist"  # type: ignore[attr-defined]
else:
    _default_front = Path(__file__).resolve().parents[2] / "frontend" / "dist"
FRONTEND_DIST = Path(os.environ.get("NEXUS_FRONTEND", _default_front))
