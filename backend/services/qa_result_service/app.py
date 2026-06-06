from typing import Any, Dict, Optional
import json
import os
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, TypeAdapter
import psycopg

from backend.shared.artifacts import ArtifactPayload, QaErrorArtifact

app = FastAPI(title="qa-result-service")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://qa:qa@127.0.0.1:5432/qa_agent")


class ResultPayload(BaseModel):
    task_id: str
    state: str
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    event_type: str = "qa.agent.task.completed"


def get_conn():
    return psycopg.connect(DATABASE_URL)


_artifact_adapter = TypeAdapter(ArtifactPayload)


def _validate_artifact(raw_result: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    raw_result = raw_result or {}
    artifact = _artifact_adapter.validate_python(raw_result)
    return artifact.model_dump()


def _build_error_artifact(message: Optional[str]) -> Dict[str, Any]:
    artifact = QaErrorArtifact(
        error_code="task_failed",
        error_message=str(message or ""),
        generated_by={
            "provider": "unknown",
            "model_name": "unknown",
            "agent_id": "qa_result_service",
        },
    )
    return artifact.model_dump()


@app.get("/health")
def health():
    return {"status": "ok", "service": "qa-result-service"}


@app.post("/internal/results")
def store_result(payload: ResultPayload):
    result_id = f"result-{uuid4().hex[:12]}"

    if payload.state == "completed" and isinstance(payload.result, dict):
        content = _validate_artifact(payload.result)
        schema_name = content.get("artifact_type", "unknown_artifact")
    else:
        content = _build_error_artifact(payload.error)
        schema_name = content.get("artifact_type", "qa_error")

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into results (result_id, task_id, schema_name, content_json)
                values (%s, %s, %s, %s::jsonb)
                """,
                (result_id, payload.task_id, schema_name, json.dumps(content)),
            )
            cur.execute(
                """
                update tasks
                set state = %s, result_ref = %s, updated_at = now()
                where task_id = %s
                """,
                (payload.state, result_id, payload.task_id),
            )
            cur.execute(
                """
                insert into task_events (event_id, task_id, event_type, payload)
                values (%s, %s, %s, %s::jsonb)
                """,
                (
                    f"evt-{uuid4().hex[:12]}",
                    payload.task_id,
                    payload.event_type,
                    json.dumps(
                        {
                            "task_id": payload.task_id,
                            "state": payload.state,
                            "result_id": result_id,
                            "error": payload.error,
                        }
                    ),
                ),
            )
        conn.commit()

    return {"status": "stored", "task_id": payload.task_id, "result_id": result_id}


@app.get("/api/tasks/{task_id}/result")
def get_result(task_id: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                select t.task_id, t.state, r.content_json
                from tasks t
                left join results r on r.result_id = t.result_ref
                where t.task_id = %s
                """,
                (task_id,),
            )
            row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail={"task_id": task_id, "state": "not_found"})

    task_id_value, state, content_json = row

    if content_json is None:
        return {
            "task_id": task_id_value,
            "state": state,
            "result": None,
            "error": None,
        }

    return {
        "task_id": task_id_value,
        "state": state,
        "result": content_json,
        "error": content_json.get("error"),
    }
