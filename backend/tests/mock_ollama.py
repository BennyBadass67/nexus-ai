"""Falsk Ollama-server KUN for tester uten GPU. Samme API-form som ekte Ollama."""
import json
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, JSONResponse

app = FastAPI()

@app.get("/api/version")
def v(): return {"version": "0.0-mock"}

@app.get("/api/tags")
def t(): return {"models": [{"name": "mock:1b", "size": 123, "details": {"parameter_size": "1B", "quantization_level": "Q4"}}]}

@app.post("/api/chat")
async def chat(req: Request):
    b = await req.json()
    if b["model"] != "mock:1b":
        return JSONResponse({"error": f"model '{b['model']}' not found"}, status_code=404)
    last = b["messages"][-1]["content"]
    if b.get("format") == "json":
        return JSONResponse({"message": {"role": "assistant", "content": json.dumps({"cards": [
            {"front": "Hva er fotosyntese?", "back": "Prosessen der planter lager sukker og oksygen av lys, vann og CO2."},
            {"front": "Hvor i cellen skjer fotosyntesen?", "back": "I kloroplastene."},
            {"front": "Hvilken gass tar planter opp?", "back": "Karbondioksid (CO2)."}]})}, "done": True})
    def g():
        for w in ["Hei ", "fra ", "mock: ", last]:
            yield json.dumps({"message": {"role": "assistant", "content": w}, "done": False}) + "\n"
        yield json.dumps({"message": {"role": "assistant", "content": ""}, "done": True}) + "\n"
    return StreamingResponse(g(), media_type="application/x-ndjson")

@app.post("/api/pull")
async def pull(req: Request):
    b = await req.json()
    if b["model"].startswith("nope"):
        return JSONResponse({"error": "pull model manifest: file does not exist"}, status_code=500)
    def g():
        for c in (0, 50, 100):
            yield json.dumps({"status": "pulling abc", "total": 100, "completed": c}) + "\n"
        yield json.dumps({"status": "success"}) + "\n"
    return StreamingResponse(g(), media_type="application/x-ndjson")

@app.delete("/api/delete")
async def delete(req: Request):
    b = await req.json()
    return JSONResponse({}, status_code=200 if b["model"] == "mock:1b" else 404)

@app.post("/api/generate")
async def gen(req: Request):
    b = await req.json()
    if b["model"] != "mock:1b":
        return JSONResponse({"error": "model not found"}, status_code=404)
    return {"response": "x", "eval_count": 96, "eval_duration": 3_000_000_000, "load_duration": 500_000_000}
