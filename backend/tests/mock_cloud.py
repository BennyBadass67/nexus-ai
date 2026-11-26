"""Falsk OpenAI-kompatibel skytjeneste for tester."""
import json
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

app = FastAPI()
SEEN: list[dict] = []


@app.get("/v1/models")
def models(req: Request):
    if req.headers.get("authorization") != "Bearer testkey1234":
        return JSONResponse({"error": {"message": "bad key"}}, status_code=401)
    return {"data": [{"id": "free-a"}, {"id": "models/free-b"}]}


@app.post("/v1/chat/completions")
async def chat(req: Request):
    b = await req.json()
    SEEN.append({"auth": req.headers.get("authorization"), "body": b})
    if req.headers.get("authorization") != "Bearer testkey1234":
        return JSONResponse({"error": {"message": "Invalid API key"}}, status_code=401)
    if b["model"] == "limit":
        return JSONResponse({"error": {"message": "rate limit"}}, status_code=429)
    if b["model"] == "paywall":
        return JSONResponse({"error": {"message": "credits"}}, status_code=402)
    if not b.get("stream"):
        return {"choices": [{"message": {"content": "OK"}}]}
    last = b["messages"][-1]["content"]

    def sse(d): return "data: " + json.dumps(d) + "\n\n"

    def g():
        if b.get("tools"):
            yield sse({"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"name": "list_no", "arguments": '{"pa'}}]}}]})
            yield sse({"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": 'th": "/x"}'}}]}}]})
        elif b.get("response_format"):
            yield sse({"choices": [{"delta": {"content": '{"ok": true}'}}]})
        else:
            for w in ["Sky ", "svar: ", last]:
                yield sse({"choices": [{"delta": {"content": w}}]})
        yield "data: [DONE]\n\n"
    return StreamingResponse(g(), media_type="text/event-stream")
