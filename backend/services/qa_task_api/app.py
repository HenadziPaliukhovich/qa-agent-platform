from uuid import uuid4
from typing import Dict, Any, Optional
import json
import os
import time

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field
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
    domain_id: Optional[str] = None
    task_type: str
    mode: str = "balanced"
    approval_mode: str = "auto"
    context_scope: str = "domain_default"
    selected_context_ids: list[str] = Field(default_factory=list)
    input: Dict[str, Any]
    model_provider: str = "ollama"
    model_name: str = "llama3"


class DomainCreateRequest(BaseModel):
    name: str
    slug: str
    description: Optional[str] = None
    tags: list[str] = Field(default_factory=list)


class DomainProfileUpsertRequest(BaseModel):
    business_scope: Optional[str] = None
    prompt_policy: Dict[str, Any] = Field(default_factory=dict)
    retrieval_policy: Dict[str, Any] = Field(default_factory=dict)
    supported_artifacts: list[str] = Field(default_factory=list)
    event_source_settings: Dict[str, Any] = Field(default_factory=dict)
    integration_bindings: list[Dict[str, Any]] = Field(default_factory=list)


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
    if isinstance(value, memoryview):
        value = value.tobytes().decode("utf-8")
    elif isinstance(value, bytes):
        value = value.decode("utf-8")
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _normalize_tags(tags: list[str]) -> list[str]:
    normalized = []
    seen = set()
    for tag in tags:
        value = str(tag).strip()
        if not value:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(value)
    return normalized


def _get_effective_domain_id(req: TaskCreateRequest) -> Optional[str]:
    if req.domain_id and str(req.domain_id).strip():
        return str(req.domain_id).strip()
    if isinstance(req.input, dict):
        nested_domain_id = req.input.get("domain_id")
        if isinstance(nested_domain_id, str) and nested_domain_id.strip():
            return nested_domain_id.strip()
    return None


def _serialize_domain_row(row) -> dict:
    return {
        "domain_id": row[0],
        "name": row[1],
        "slug": row[2],
        "description": row[3],
        "status": row[4],
        "tags": _safe_json_load(row[5]) or [],
        "created_at": row[6].isoformat() if row[6] else None,
        "updated_at": row[7].isoformat() if row[7] else None,
    }


def _serialize_domain_profile_row(row) -> dict:
    return {
        "domain_id": row[0],
        "business_scope": row[1],
        "prompt_policy": _safe_json_load(row[2]) or {},
        "retrieval_policy": _safe_json_load(row[3]) or {},
        "supported_artifacts": _safe_json_load(row[4]) or [],
        "event_source_settings": _safe_json_load(row[5]) or {},
        "integration_bindings": _safe_json_load(row[6]) or [],
        "created_at": row[7].isoformat() if row[7] else None,
        "updated_at": row[8].isoformat() if row[8] else None,
    }


def _get_domain_or_404(cur, domain_id: str):
    cur.execute(
        """
        select domain_id, name, slug, description, status, tags, created_at, updated_at
        from domains
        where domain_id = %s
        """,
        (domain_id,),
    )
    row = cur.fetchone()
    if not row:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "domain_not_found",
                    "message": "Domain was not found",
                    "details": {"domain_id": domain_id},
                }
            },
        )
    return row


def _ensure_domain_slug_available(cur, slug: str, exclude_domain_id: str | None = None) -> None:
    cur.execute(
        "select domain_id from domains where slug = %s",
        (slug,),
    )
    row = cur.fetchone()
    if row and str(row[0]) != str(exclude_domain_id):
        raise HTTPException(
            status_code=409,
            detail={
                "error": {
                    "code": "domain_slug_conflict",
                    "message": "Domain slug already exists",
                    "details": {"slug": slug},
                }
            },
        )




def _validate_task_domain_context(cur, req: TaskCreateRequest) -> None:
    effective_domain_id = _get_effective_domain_id(req)

    if effective_domain_id:
        row = _get_domain_or_404(cur, effective_domain_id)
        if row[4] != "active":
            raise HTTPException(
                status_code=409,
                detail={
                    "error": {
                        "code": "domain_archived",
                        "message": "Archived domain cannot accept new tasks",
                        "details": {"domain_id": effective_domain_id},
                    }
                },
            )
    if req.context_scope not in {"domain_default", "manual_selection"}:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "invalid_context_scope",
                    "message": "context_scope must be domain_default or manual_selection",
                    "details": {"context_scope": req.context_scope},
                }
            },
        )
    if req.context_scope == "manual_selection" and not req.selected_context_ids:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "selected_context_ids_required",
                    "message": "manual_selection requires selected_context_ids",
                    "details": {},
                }
            },
        )
    if req.selected_context_ids:
        if not effective_domain_id:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": {
                        "code": "domain_id_required",
                        "message": "domain_id is required when selected_context_ids are provided",
                        "details": {},
                    }
                },
            )
        cur.execute(
            """
            select context_file_id
            from domain_context_files
            where domain_id = %s
              and status = 'active'
              and context_file_id = any(%s)
            """,
            (effective_domain_id, req.selected_context_ids),
        )
        existing_ids = {row[0] for row in cur.fetchall()}
        missing_ids = [item for item in req.selected_context_ids if item not in existing_ids]
        if missing_ids:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": {
                        "code": "invalid_selected_context_ids",
                        "message": "Some selected_context_ids do not belong to the domain",
                        "details": {"missing_ids": missing_ids},
                    }
                },
            )


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
    effective_domain_id = _get_effective_domain_id(req)
    task_payload = req.model_dump()
    task_payload["domain_id"] = effective_domain_id

    event = {
        "task_id": task_id,
        "project_id": req.project_id,
        "domain_id": effective_domain_id,
        "task_type": req.task_type,
        "mode": req.mode,
        "approval_mode": req.approval_mode,
        "context_scope": req.context_scope,
        "selected_context_ids": req.selected_context_ids,
        "input": req.input,
        "model_provider": req.model_provider,
        "model_name": req.model_name,
        "state": "created",
    }

    with get_conn() as conn:
        with conn.cursor() as cur:
            _validate_task_domain_context(cur, req)
            cur.execute(
                """
                insert into tasks (task_id, project_id, domain_id, task_type, state, input_json, approval_required, context_scope, selected_context_ids)
                values (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s::jsonb)
                """,
                (
                    task_id,
                    req.project_id,
                    effective_domain_id,
                    req.task_type,
                    "created",
                    json.dumps(task_payload),
                    req.approval_mode != "auto",
                    req.context_scope,
                    json.dumps(req.selected_context_ids),
                ),
            )
            for context_file_id in req.selected_context_ids:
                cur.execute(
                    """
                    insert into task_context_links (task_id, context_file_id, relation_type)
                    values (%s, %s, 'selected')
                    on conflict do nothing
                    """,
                    (task_id, context_file_id),
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
        "domain_id": effective_domain_id,
        "context_scope": req.context_scope,
        "selected_context_ids": req.selected_context_ids,
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
                    domain_id,
                    task_type,
                    state,
                    approval_required,
                    context_scope,
                    selected_context_ids,
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
        selected_context_ids = _safe_json_load(row[7]) or []
        input_json = _safe_json_load(row[8]) or {}
        result = _fetch_result(row[0])

        tasks.append(
            {
                "task_id": row[0],
                "project_id": row[1],
                "domain_id": row[2],
                "task_type": row[3],
                "state": row[4],
                "approval_required": row[5],
                "context_scope": row[6],
                "selected_context_ids": selected_context_ids,
                "input": input_json,
                "created_at": row[9].isoformat() if row[9] else None,
                "updated_at": row[10].isoformat() if row[10] else None,
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
                    domain_id,
                    task_type,
                    state,
                    approval_required,
                    context_scope,
                    selected_context_ids,
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

    selected_context_ids = _safe_json_load(row[7]) or []
    input_json = _safe_json_load(row[8]) or {}
    result = _fetch_result(task_id)

    return {
        "task_id": row[0],
        "project_id": row[1],
        "domain_id": row[2],
        "task_type": row[3],
        "state": row[4],
        "approval_required": row[5],
        "context_scope": row[6],
        "selected_context_ids": selected_context_ids,
        "input": input_json,
        "created_at": row[9].isoformat() if row[9] else None,
        "updated_at": row[10].isoformat() if row[10] else None,
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

@app.post("/api/domains")
def create_domain(req: DomainCreateRequest):
    domain_id = str(uuid4())
    tags = _normalize_tags(req.tags)

    with get_conn() as conn:
        with conn.cursor() as cur:
            _ensure_domain_slug_available(cur, req.slug)
            cur.execute(
                """
                insert into domains (domain_id, name, slug, description, status, tags)
                values (%s, %s, %s, %s, 'active', %s::jsonb)
                returning domain_id, name, slug, description, status, tags, created_at, updated_at
                """,
                (domain_id, req.name, req.slug, req.description, json.dumps(tags)),
            )
            row = cur.fetchone()
        conn.commit()

    return _serialize_domain_row(row)


@app.get("/api/domains")
def list_domains(status: Optional[str] = Query(default=None), q: Optional[str] = Query(default=None)):
    query = """
        select
            d.domain_id,
            d.name,
            d.slug,
            d.description,
            d.status,
            d.tags,
            d.created_at,
            d.updated_at,
            coalesce(count(f.context_file_id), 0) as context_files_count
        from domains d
        left join domain_context_files f
          on f.domain_id = d.domain_id
         and f.status = 'active'
        where (%s::text is null or d.status = %s::text)
          and (
            %s::text is null
            or d.name ilike %s::text
            or d.slug ilike %s::text
            or coalesce(d.description, '') ilike %s::text
          )
        group by d.domain_id, d.name, d.slug, d.description, d.status, d.tags, d.created_at, d.updated_at
        order by d.created_at desc
    """
    search = f"%{q.strip()}%" if q and q.strip() else None

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (status, status, search, search, search, search))
            rows = cur.fetchall()

    domains = []
    for row in rows:
        item = _serialize_domain_row(row[:8])
        item["context_files_count"] = row[8]
        domains.append(item)

    return {"domains": domains}


@app.get("/api/domains/{domain_id}")
def get_domain(domain_id: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            row = _get_domain_or_404(cur, domain_id)
    return _serialize_domain_row(row)


@app.put("/api/domains/{domain_id}")
def update_domain(domain_id: str, req: DomainCreateRequest):
    tags = _normalize_tags(req.tags)

    with get_conn() as conn:
        with conn.cursor() as cur:
            _get_domain_or_404(cur, domain_id)
            _ensure_domain_slug_available(cur, req.slug, exclude_domain_id=domain_id)
            cur.execute(
                """
                update domains
                set name = %s,
                    slug = %s,
                    description = %s,
                    tags = %s::jsonb,
                    updated_at = now()
                where domain_id = %s
                returning domain_id, name, slug, description, status, tags, created_at, updated_at
                """,
                (req.name, req.slug, req.description, json.dumps(tags), domain_id),
            )
            row = cur.fetchone()
        conn.commit()

    return _serialize_domain_row(row)


@app.post("/api/domains/{domain_id}/archive")
def archive_domain(domain_id: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            _get_domain_or_404(cur, domain_id)
            cur.execute(
                """
                update domains
                set status = 'archived', updated_at = now()
                where domain_id = %s
                returning domain_id, status, updated_at
                """,
                (domain_id,),
            )
            row = cur.fetchone()
        conn.commit()

    return {
        "domain_id": row[0],
        "status": row[1],
        "updated_at": row[2].isoformat() if row[2] else None,
    }


@app.post("/api/domains/{domain_id}/unarchive")
def unarchive_domain(domain_id: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            _get_domain_or_404(cur, domain_id)
            cur.execute(
                """
                update domains
                set status = 'active', updated_at = now()
                where domain_id = %s
                returning domain_id, status, updated_at
                """,
                (domain_id,),
            )
            row = cur.fetchone()
        conn.commit()

    return {
        "domain_id": row[0],
        "status": row[1],
        "updated_at": row[2].isoformat() if row[2] else None,
    }


@app.get("/api/domains/{domain_id}/profile")
def get_domain_profile(domain_id: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            _get_domain_or_404(cur, domain_id)
            cur.execute(
                """
                select
                    domain_id,
                    business_scope,
                    prompt_policy,
                    retrieval_policy,
                    supported_artifacts,
                    event_source_settings,
                    integration_bindings,
                    created_at,
                    updated_at
                from domain_profiles
                where domain_id = %s
                """,
                (domain_id,),
            )
            row = cur.fetchone()

    if not row:
        return {
            "domain_id": domain_id,
            "business_scope": None,
            "prompt_policy": {},
            "retrieval_policy": {},
            "supported_artifacts": [],
            "event_source_settings": {},
            "integration_bindings": [],
            "created_at": None,
            "updated_at": None,
        }

    return _serialize_domain_profile_row(row)


@app.put("/api/domains/{domain_id}/profile")
def upsert_domain_profile(domain_id: str, req: DomainProfileUpsertRequest):
    with get_conn() as conn:
        with conn.cursor() as cur:
            _get_domain_or_404(cur, domain_id)
            cur.execute(
                """
                insert into domain_profiles (
                    domain_id,
                    business_scope,
                    prompt_policy,
                    retrieval_policy,
                    supported_artifacts,
                    event_source_settings,
                    integration_bindings
                )
                values (%s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb)
                on conflict (domain_id) do update set
                    business_scope = excluded.business_scope,
                    prompt_policy = excluded.prompt_policy,
                    retrieval_policy = excluded.retrieval_policy,
                    supported_artifacts = excluded.supported_artifacts,
                    event_source_settings = excluded.event_source_settings,
                    integration_bindings = excluded.integration_bindings,
                    updated_at = now()
                returning domain_id, business_scope, prompt_policy, retrieval_policy, supported_artifacts, event_source_settings, integration_bindings, created_at, updated_at
                """,
                (
                    domain_id,
                    req.business_scope,
                    json.dumps(req.prompt_policy),
                    json.dumps(req.retrieval_policy),
                    json.dumps(req.supported_artifacts),
                    json.dumps(req.event_source_settings),
                    json.dumps(req.integration_bindings),
                ),
            )
            row = cur.fetchone()
        conn.commit()

    return _serialize_domain_profile_row(row)

