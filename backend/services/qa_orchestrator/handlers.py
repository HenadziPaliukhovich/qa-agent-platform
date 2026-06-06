from backend.services.qa_orchestrator.builders import (
    build_structured_result,
    normalize_llm_output,
)
from backend.services.qa_orchestrator.clients import call_llm_gateway, get_effective_input_data


def _build_handler_result(event: dict, llm_response: dict | None) -> dict:
    raw_output = llm_response.get("output", {}) if isinstance(llm_response, dict) else {}
    llm_output = normalize_llm_output(raw_output, event, llm_response)
    artifact = build_structured_result(event, llm_output)
    return {
        "llm_response": llm_response,
        "llm_output": llm_output,
        "artifact": artifact,
    }


def _apply_processing_profile(result: dict, **profile_fields) -> dict:
    artifact = result.get("artifact") if isinstance(result, dict) else None
    if isinstance(artifact, dict):
        artifact.setdefault("processing_profile", {})
        if isinstance(artifact["processing_profile"], dict):
            artifact["processing_profile"].update(profile_fields)
    return result


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
    return _apply_processing_profile(
        result,
        handler="handle_requirements_analysis",
        specialized=True,
        handoff_enabled=True,
    )


def handle_test_case_generation(event: dict) -> dict:
    enriched_event = dict(event)
    input_data = get_effective_input_data(event)
    metadata = enriched_event.get("metadata") if isinstance(enriched_event.get("metadata"), dict) else {}

    analysis_handoff = {}
    if isinstance(input_data, dict):
        for key in [
            "suggested_next_prompt",
            "questions_for_refinement",
            "coverage_gaps",
            "suggested_test_areas",
            "requirements_under_test",
            "assumptions",
            "risks",
        ]:
            value = input_data.get(key)
            if value:
                analysis_handoff[key] = value

    enriched_event["metadata"] = {
        **metadata,
        "specialized_handler": "test_case_generation",
        "analysis_handoff_present": bool(analysis_handoff),
        "domain_focus": "qa_test_case_generation",
    }

    enriched_input = dict(input_data) if isinstance(input_data, dict) else {}
    if analysis_handoff:
        enriched_input["analysis_handoff"] = analysis_handoff
        if analysis_handoff.get("suggested_next_prompt") and not enriched_input.get("prompt_hint"):
            enriched_input["prompt_hint"] = analysis_handoff.get("suggested_next_prompt")
    enriched_event["input"] = enriched_input

    llm_response = call_llm_gateway(enriched_event)
    result = _build_handler_result(enriched_event, llm_response)
    return _apply_processing_profile(
        result,
        handler="handle_test_case_generation",
        specialized=True,
        analysis_handoff_present=bool(analysis_handoff),
        derived_from_requirements=bool(analysis_handoff.get("requirements_under_test")),
        derived_from_gaps=bool(analysis_handoff.get("coverage_gaps")),
    )
