import json
import logging
import os
from typing import Any

import requests

logger = logging.getLogger("qa-orchestrator")

LLM_GATEWAY_URL = os.getenv("LLM_GATEWAY_URL", "http://127.0.0.1:8003")
RESULT_SERVICE_URL = os.getenv("RESULT_SERVICE_URL", "http://127.0.0.1:8004")
RAG_SERVICE_URL = os.getenv("RAG_SERVICE_URL", "http://127.0.0.1:8005")


def build_rag_query(input_data: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in [
        "text",
        "story",
        "story_title",
        "story_description",
        "service_name",
        "architecture_context",
    ]:
        value = input_data.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())

    acceptance_criteria = input_data.get("acceptance_criteria")
    if isinstance(acceptance_criteria, list):
        parts.extend(item.strip() for item in acceptance_criteria if isinstance(item, str) and item.strip())

    related_docs = input_data.get("related_docs")
    if isinstance(related_docs, list):
        parts.extend(item.strip() for item in related_docs if isinstance(item, str) and item.strip())

    return "\n".join(parts[:20]).strip()


def get_effective_input_data(event: dict) -> dict:
    raw_input = event.get("input", {})
    if not isinstance(raw_input, dict):
        return {}

    nested_input = raw_input.get("input")
    if isinstance(nested_input, dict):
        merged = dict(raw_input)
        merged.update(nested_input)
        merged.pop("input", None)
        return merged

    return raw_input


def fetch_rag_context(event: dict, input_data: dict | None = None) -> list[dict]:
    input_data = input_data or get_effective_input_data(event)

    query = (
        input_data.get("summary")
        or input_data.get("description")
        or input_data.get("requirements")
        or build_rag_query(input_data)
        or json.dumps(input_data, ensure_ascii=False)
    )
    if not query:
        return []

    payload = {
        "project_id": event.get("project_id", "default-project"),
        "service_name": input_data.get("service_name") or event.get("service_name") or "qa-platform",
        "query": str(query),
        "limit": 5,
    }

    search_url = RAG_SERVICE_URL.rstrip("/") + "/api/knowledge/search"
    try:
        response = requests.post(search_url, json=payload, timeout=20)
        response.raise_for_status()
        data = response.json()
        return data.get("results", [])
    except Exception as exc:
        logger.warning("RAG lookup failed for task %s: %s", event.get("task_id"), exc)
        return []


def call_llm_gateway(event: dict) -> dict:
    input_data = get_effective_input_data(event)
    task_type = event.get("task_type", "test_case_generation")

    rag_results = fetch_rag_context(event, input_data)
    llm_context = dict(input_data)
    llm_context["knowledge_context"] = [
        {
            "title": item.get("title"),
            "service_name": item.get("service_name"),
            "content": item.get("content"),
        }
        for item in rag_results
    ]
    llm_context["debug_context"] = {
        "rag_titles": [item.get("title") for item in rag_results if item.get("title")],
        "rag_count": len(rag_results),
    }

    logger.info(
        "RAG context for task %s: chunks=%s titles=%s previews=%s",
        event.get("task_id"),
        len(llm_context["knowledge_context"]),
        [chunk.get("title") for chunk in llm_context["knowledge_context"]],
        [(chunk.get("content") or "")[:120] for chunk in llm_context["knowledge_context"]],
    )

    prompt = json.dumps(
        {
            "task_input": input_data,
            "knowledge_context": llm_context["knowledge_context"],
        },
        ensure_ascii=False,
        indent=2,
    )

    response = requests.post(
        f"{LLM_GATEWAY_URL}/generate",
        json={
            "model_profile": event.get("mode", "balanced"),
            "prompt": prompt,
            "task_id": event.get("task_id"),
            "task_type": task_type,
            "context": llm_context,
            "provider": event.get("model_provider", "stub"),
            "model_name": event.get("model_name", "stub-default"),
        },
        timeout=120,
    )
    response.raise_for_status()
    return response.json()


def persist_result(task_id: str, artifact: dict) -> None:
    response = requests.post(
        f"{RESULT_SERVICE_URL}/internal/results",
        json={
            "task_id": task_id,
            "state": "completed",
            "result": artifact,
            "error": None,
            "event_type": "qa.agent.task.completed",
        },
        timeout=30,
    )
    response.raise_for_status()
