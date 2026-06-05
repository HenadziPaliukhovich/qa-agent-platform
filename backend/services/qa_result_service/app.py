from fastapi import FastAPI

app = FastAPI(title="qa-result-service")

@app.get("/health")
def health():
    return {"status": "ok", "service": "qa-result-service"}
