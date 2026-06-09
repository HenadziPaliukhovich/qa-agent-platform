import json
import logging
import os
from typing import Any

import requests

from backend.services.qa_orchestrator.builders import build_requirements_analysis_prompt
from backend.services.qa_orchestrator.utils import get_effective_input_data

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


def _build_fallback_artifact(task_type: str, input_data: dict[str, Any], llm_context: dict[str, Any]) -> dict[str, Any]:
    title = input_data.get("title") or input_data.get("story_title") or "Untitled task"
    description = input_data.get("description") or input_data.get("story_description") or ""
    domain_id = input_data.get("domain_id")

    if task_type == "test_case_generation":
        return {
            "summary": f"Fallback test cases for {title}",
            "test_cases": [
                {
                    "id": "TC-001",
                    "title": f"{title}: happy path",
                    "steps": [
                        "Open the flow",
                        "Provide valid input",
                        "Submit the action",
                    ],
                    "expected_result": "Flow completes successfully",
                },
                {
                    "id": "TC-002",
                    "title": f"{title}: validation handling",
                    "steps": [
                        "Open the flow",
                        "Submit invalid or incomplete input",
                    ],
                    "expected_result": "Validation feedback is shown",
                },
                {
                    "id": "TC-003",
                    "title": f"{title}: failure path",
                    "steps": [
                        "Open the flow",
                        "Trigger or simulate provider or service failure",
                    ],
                    "expected_result": "A clear error state is shown and data remains consistent",
                },
            ],
            "risks": [
                "Domain context was limited because the LLM gateway was unavailable.",
                f"Domain binding should be verified for domain_id={domain_id}" if domain_id else "Domain binding was not provided.",
            ],
            "debug_context": llm_context.get("debug_context", {}),
            "fallback": True,
        }

    return {
        "summary": f"Fallback artifact for {task_type}",
        "details": {
            "title": title,
            "description": description,
            "domain_id": domain_id,
        },
        "debug_context": llm_context.get("debug_context", {}),
        "fallback": True,
    }


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

    if task_type == "requirements_analysis":
        prompt = build_requirements_analysis_prompt(input_data, llm_context)
    else:
        prompt = json.dumps(
            {
                "task_input": input_data,
                "knowledge_context": llm_context["knowledge_context"],
            },
            ensure_ascii=False,
            indent=2,
        )

    try:
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
    except Exception as exc:
        logger.warning("LLM gateway unavailable for task %s: %s", event.get("task_id"), exc)
        return {
            "raw_output": {
                "fallback": True,
                "task_type": task_type,
                "message": "LLM gateway unavailable, produced deterministic fallback artifact.",
            },
            "normalized_output": _build_fallback_artifact(task_type, input_data, llm_context),
        }


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

def search_domain_context(domain_id: str, query: str, selected_context_ids: list[str] | None = None, limit: int = 5) -> list[dict]:
    try:
        response = requests.post(
            f"{RAG_SERVICE_URL}/api/domains/context-search",
            json={
                "domain_id": domain_id,
                "query": query,
                "selected_context_ids": selected_context_ids or [],
                "limit": limit,
            },
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        return data.get("items", [])
    except Exception:
        return []

