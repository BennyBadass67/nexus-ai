# NEXUS AI

Personlig KI-agent for Windows. Fase 1: chat mot lokal Ollama, samtaler lagret i SQLite.

- `backend/` FastAPI + SQLite + Pydantic. Kjør tester: `python backend/tests/test_chat.py` (med Ollama eller mock).
- `frontend/` React + TypeScript + Tailwind (Liquid Glass-stil).
- `build-windows.sh` bygger bærbar zip for Windows fra Linux/macOS.
- `windows/NEXUS-AI.bat` startskript i zip-en.

Utvikling: `cd frontend && npm i && npm run build`, så `cd backend && python run.py`, åpne http://127.0.0.1:8765.
