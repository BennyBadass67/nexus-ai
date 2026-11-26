"""Liten Ollama-etterligning for skjermbilder: kun en synsmodell som beskriver hva den fikk (ikke ekte bildeforståelse)."""
import json
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

app = FastAPI()


@app.get("/api/version")
def v(): return {"version": "0.0-mock"}


@app.get("/api/tags")
def t(): return {"models": [{"name": "moondream:mock", "size": 123, "details": {"parameter_size": "1.8B", "quantization_level": "Q4"}},
                            {"name": "mock:1b", "size": 123, "details": {"parameter_size": "1B", "quantization_level": "Q4"}}]}


@app.post("/api/chat")
async def chat(req: Request):
    b = await req.json()
    m = b["messages"][-1]
    n = len(m.get("images") or [])
    txt = f"(mock) Fikk {n} bilde(r), første er {len((m.get('images') or [''])[0]) // 1000} kB base64. Spørsmålet var: {m['content']}"
    def g():
        for w in txt.split(" "):
            yield json.dumps({"message": {"role": "assistant", "content": w + " "}, "done": False}) + "\n"
        yield json.dumps({"message": {"role": "assistant", "content": ""}, "done": True}) + "\n"
    return StreamingResponse(g(), media_type="application/x-ndjson")
