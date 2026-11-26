"""Arbeidsområde: bla i de godkjente mappene og forhåndsvis tekstfiler. Bruker samme sandkasse som agenten."""
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException

from . import tools

router = APIRouter()
TEXT_EXT = {".txt", ".md", ".json", ".csv", ".py", ".js", ".ts", ".tsx", ".html", ".css", ".log", ".yml", ".yaml", ".toml", ".ini", ".xml", ".rs", ".sql", ".sh", ".bat"}


def _safe(path: str) -> Path:
    try:
        return tools.resolve_safe(path)
    except tools.ToolError as e:
        raise HTTPException(403, str(e))


@router.get("/api/workspace/roots")
def roots():
    return {"roots": [{"path": r, "exists": Path(r).is_dir()} for r in tools.get_roots()]}


@router.put("/api/workspace/roots")
def put_roots(body: dict):
    try:
        return {"roots": tools.set_roots([str(x) for x in body.get("roots", [])])}
    except tools.ToolError as e:
        raise HTTPException(422, str(e))


@router.get("/api/workspace/list")
def list_dir(path: str):
    p = _safe(path)
    if not p.is_dir():
        raise HTTPException(400, "Ikke en mappe")
    items = []
    try:
        entries = sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
    except OSError as e:
        raise HTTPException(403, str(e))
    for e in entries[:300]:
        try:
            st = e.stat()
        except OSError:
            continue
        items.append({"name": e.name, "path": str(e), "dir": e.is_dir(), "size": 0 if e.is_dir() else st.st_size, "mtime": st.st_mtime})
    return {"path": str(p), "parent": str(p.parent) if _inside(p.parent) else None, "items": items, "truncated": len(entries) > 300}


def _inside(p: Path) -> bool:
    try:
        tools.resolve_safe(str(p))
        return True
    except tools.ToolError:
        return False


@router.get("/api/workspace/read")
def read(path: str):
    p = _safe(path)
    if not p.is_file():
        raise HTTPException(404, "Ikke en fil")
    size = p.stat().st_size
    data = p.read_bytes()[:100000]
    if b"\x00" in data[:2000] and p.suffix.lower() not in TEXT_EXT:
        return {"path": str(p), "size": size, "text": None, "binary": True}
    return {"path": str(p), "size": size, "text": data.decode("utf-8", "replace"), "binary": False, "truncated": size > 100000}


@router.post("/api/workspace/open")
def open_it(body: dict):
    p = _safe(str(body.get("path", "")))
    try:
        tools.run_tool("open_path", {"path": str(p)})
    except tools.ToolError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}
