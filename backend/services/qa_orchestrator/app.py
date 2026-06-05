from fastapi import FastAPI

app = FastAPI(title="qa-orchestrator")

@app.get("/health")
def health():
    return {"status": "ok", "service": "qa-orchestrator"}
