from fastapi import FastAPI
from pydantic import BaseModel
from uuid import uuid4

app = FastAPI(title="qa-task-api")

class TaskCreateRequest(BaseModel):
    project_id: str
    task_type: str
    mode: str = "balanced"
    approval_mode: str = "auto"
    input: dict

@app.get("/health")
def health():
    return {"status": "ok", "service": "qa-task-api"}

@app.post("/api/tasks")
def create_task(req: TaskCreateRequest):
    task_id = f"task-{uuid4().hex[:12]}"
    return {
        "task_id": task_id,
        "state": "created",
        "stream_url": f"/api/tasks/{task_id}/events",
        "result_url": f"/api/tasks/{task_id}/result"
    }
