from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="qa-llm-gateway")

class GenerateRequest(BaseModel):
    model_profile: str
    prompt: str
    keep_alive: str = "10m"

@app.get("/health")
def health():
    return {"status": "ok", "service": "qa-llm-gateway"}

@app.post("/generate")
def generate(req: GenerateRequest):
    return {
        "model_profile": req.model_profile,
        "keep_alive": req.keep_alive,
        "status": "stubbed"
    }
