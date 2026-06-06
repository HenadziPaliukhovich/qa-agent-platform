from uuid import uuid4
from typing import Dict, Any
import json
import os
import time

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict
from kafka import KafkaProducer
from sse_starlette.sse import EventSourceResponse
import psycopg
import requests

app = FastAPI(title="qa-task-api")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class TaskCreateRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    project_id: str = "default-project"
    task_type: str
    mode: str = "balanced"
    approval_mode: str = "auto"
    input: Dict[str, Any]
    model_provider: str = "ollama"
    model_name: str = "llama3"


KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
TASK_CREATED_TOPIC = "qa.agent.task.created"
TASK_STATUS_TOPIC = "qa.agent.task.status"
RESULT_SERVICE_URL = os.getenv("RESULT_SERVICE_URL", "http://127.0.0.1:8004")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://qa:qa@127.0.0.1:5432/qa_agent")

ALLOWED_TASK_TYPES = {
    "test_case_generation",
    "requirements_analysis",
    "manual_test_case_review",
    "test_plan",
    "test_report",
    "release_readiness",
}

producer: KafkaProducer | None = None


def get_conn():
    return psycopg.connect(DATABASE_URL)


def _create_producer() -> KafkaProducer | None:
    try:
        return KafkaProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            key_serializer=lambda v: v.encode("utf-8") if v else None,
            api_version=(2, 5, 0),
        )
    except Exception as e:
        print(f"[qa-task-api] Kafka producer is unavailable: {e}")
        return None


def _append_event(cur, task_id: str, event_type: str, payload: dict) -> None:
    cur.execute(
        """
        insert into task_events (event_id, task_id, event_type, payload)
        values (%s, %s, %s, %s::jsonb)
        """,
        (f"evt-{uuid4().hex[:12]}", task_id, event_type, json.dumps(payload)),
    )


def _safe_json_load(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _fetch_result(task_id: str) -> dict | None:
    try:
        response = requests.get(f"{RESULT_SERVICE_URL}/api/tasks/{task_id}/result", timeout=5)
        response.raise_for_status()
        data = response.json()
        return data.get("result")
    except Exception:
        return None


@app.on_event("startup")
def on_startup() -> None:
    global producer
    producer = _create_producer()


@app.on_event("shutdown")
def on_shutdown() -> None:
    global producer
    if producer is not None:
        try:
            producer.flush()
            producer.close()
        except Exception as e:
            print(f"[qa-task-api] Kafka shutdown warning: {e}")
        producer = None


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "qa-task-api",
        "kafka_enabled": producer is not None,
    }


@app.post("/api/tasks")
def create_task(req: TaskCreateRequest):
    global producer

    if req.task_type not in ALLOWED_TASK_TYPES:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "unsupported_task_type",
                "supported_task_types": sorted(ALLOWED_TASK_TYPES),
            },
        )

    if producer is None:
        producer = _create_producer()

    task_id = f"task-{uuid4().hex[:12]}"
    task_payload = req.model_dump()

    event = {
        "task_id": task_id,
        "project_id": req.project_id,
        "task_type": req.task_type,
        "mode": req.mode,
        "approval_mode": req.approval_mode,
        "input": req.input,
        "model_provider": req.model_provider,
        "model_name": req.model_name,
        "state": "created",
    }

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into tasks (task_id, project_id, task_type, state, input_json, approval_required)
                values (%s, %s, %s, %s, %s::jsonb, %s)
                """,
                (
                    task_id,
                    req.project_id,
                    req.task_type,
                    "created",
                    json.dumps(task_payload),
                    req.approval_mode != "auto",
                ),
            )
            _append_event(cur, task_id, TASK_CREATED_TOPIC, event)
        conn.commit()

    if producer is not None:
        try:
            producer.send(TASK_CREATED_TOPIC, key=task_id, value=event)
            producer.flush()
        except Exception as e:
            print(f"[qa-task-api] Kafka send failed: {e}")

    return {
        "task_id": task_id,
        "state": "created",
        "stream_url": f"/api/tasks/{task_id}/events",
        "result_url": f"/api/tasks/{task_id}/result",
        "kafka_enabled": producer is not None,
    }


@app.get("/api/tasks")
def list_tasks(limit: int = 20):
    safe_limit = min(max(limit, 1), 100)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                select
                    task_id,
                    project_id,
                    task_type,
                    state,
                    approval_required,
                    input_json,
                    created_at,
                    updated_at
                from tasks
                order by created_at desc
                limit %s
                """,
                (safe_limit,),
            )
            rows = cur.fetchall()

    tasks = []
    for row in rows:
        input_json = _safe_json_load(row[5]) or {}
        result = _fetch_result(row[0])

        tasks.append(
            {
                "task_id": row[0],
                "project_id": row[1],
                "task_type": row[2],
                "state": row[3],
                "approval_required": row[4],
                "input": input_json,
                "created_at": row[6].isoformat() if row[6] else None,
                "updated_at": row[7].isoformat() if row[7] else None,
                "result": result,
            }
        )

    return {"tasks": tasks}


@app.get("/api/tasks/{task_id}")
def get_task(task_id: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                select
                    task_id,
                    project_id,
                    task_type,
                    state,
                    approval_required,
                    input_json,
                    created_at,
                    updated_at
                from tasks
                where task_id = %s
                """,
                (task_id,),
            )
            row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Task not found")

    input_json = _safe_json_load(row[5]) or {}
    result = _fetch_result(task_id)

    return {
        "task_id": row[0],
        "project_id": row[1],
        "task_type": row[2],
        "state": row[3],
        "approval_required": row[4],
        "input": input_json,
        "created_at": row[6].isoformat() if row[6] else None,
        "updated_at": row[7].isoformat() if row[7] else None,
        "result": result,
    }


@app.get("/api/tasks/{task_id}/result")
def get_task_result(task_id: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("select state from tasks where task_id = %s", (task_id,))
            row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Task not found")

    state = row[0]
    result = _fetch_result(task_id)

    return {
        "task_id": task_id,
        "state": state,
        "result": result,
    }


@app.get("/api/tasks/{task_id}/events")
def stream_task_events(task_id: str):
    def event_generator():
        last_seen_created_at = None

        while True:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    if last_seen_created_at is None:
                        cur.execute(
                            """
                            select event_id, event_type, payload, created_at
                            from task_events
                            where task_id = %s
                            order by created_at asc
                            """,
                            (task_id,),
                        )
                    else:
                        cur.execute(
                            """
                            select event_id, event_type, payload, created_at
                            from task_events
                            where task_id = %s and created_at > %s
                            order by created_at asc
                            """,
                            (task_id, last_seen_created_at),
                        )

                    rows = cur.fetchall()

            for event_id, event_type, payload, created_at in rows:
                last_seen_created_at = created_at
                parsed_payload = _safe_json_load(payload) or {}
                yield {
                    "event": event_type,
                    "id": event_id,
                    "data": json.dumps(parsed_payload),
                }

            time.sleep(1)

    return EventSourceResponse(event_generator())
