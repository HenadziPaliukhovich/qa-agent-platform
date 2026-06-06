from backend.services.qa_orchestrator.builders import (
    build_structured_result,
    normalize_llm_output,
)
from backend.services.qa_orchestrator.clients import call_llm_gateway


def _build_handler_result(event: dict, llm_response: dict | None) -> dict:
    raw_output = llm_response.get("output", {}) if isinstance(llm_response, dict) else {}
    llm_output = normalize_llm_output(raw_output, event, llm_response)
    artifact = build_structured_result(event, llm_output)
    return {
        "llm_response": llm_response,
        "llm_output": llm_output,
        "artifact": artifact,
    }


def handle_generic_task(event: dict) -> dict:
    llm_response = call_llm_gateway(event)
    return _build_handler_result(event, llm_response)


def handle_requirements_analysis(event: dict) -> dict:
    enriched_event = dict(event)
    metadata = enriched_event.get("metadata") if isinstance(enriched_event.get("metadata"), dict) else {}
    enriched_event["metadata"] = {
        **metadata,
        "specialized_handler": "requirements_analysis",
        "handoff_enabled": True,
        "domain_focus": "qa_requirements_analysis",
    }
    llm_response = call_llm_gateway(enriched_event)
    result = _build_handler_result(enriched_event, llm_response)
    artifact = result.get("artifact") if isinstance(result, dict) else None
    if isinstance(artifact, dict):
        artifact.setdefault("processing_profile", {})
        if isinstance(artifact["processing_profile"], dict):
            artifact["processing_profile"].update(
                {
                    "handler": "handle_requirements_analysis",
                    "specialized": True,
                    "handoff_enabled": True,
                }
            )
    return result
