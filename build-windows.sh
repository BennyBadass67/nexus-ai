#!/usr/bin/env bash
# Bygger en bærbar Windows-mappe (zip) fra Linux/macOS: ingen installasjon nødvendig på Windows,
# bortsett fra Ollama. Krever: python3, pip, npm, curl, zip.
set -euo pipefail
cd "$(dirname "$0")"
PYV=3.12.8
OUT=dist-windows/NEXUS-AI
rm -rf dist-windows && mkdir -p "$OUT"
(cd frontend && npm install --no-audit --no-fund && npm run build)
curl -fsSL -o /tmp/pyembed.zip "https://www.python.org/ftp/python/$PYV/python-$PYV-embed-amd64.zip"
mkdir -p "$OUT/python" && unzip -q /tmp/pyembed.zip -d "$OUT/python"
pip download -q -r backend/requirements.txt -d /tmp/winwheels --platform win_amd64 \
  --python-version 3.12 --implementation cp --only-binary=:all:
mkdir -p "$OUT/python/Lib/site-packages"
for w in /tmp/winwheels/*.whl; do unzip -q -o "$w" -d "$OUT/python/Lib/site-packages"; done
cat > "$OUT/python/python312._pth" <<'PTH'
python312.zip
.
Lib\site-packages
..\backend
import site
PTH
mkdir -p "$OUT/backend" "$OUT/frontend"
cp -r backend/app backend/run.py "$OUT/backend/"
find "$OUT/backend" -name __pycache__ -prune -exec rm -rf {} +
cp -r frontend/dist "$OUT/frontend/dist"
cp windows/NEXUS-AI.bat windows/LES-MEG.txt "$OUT/"
(cd dist-windows && zip -qr NEXUS-AI-windows.zip NEXUS-AI)
echo "Ferdig: dist-windows/NEXUS-AI-windows.zip"
