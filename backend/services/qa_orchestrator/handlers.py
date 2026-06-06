from backend.services.qa_orchestrator.builders import build_structured_result, normalize_llm_output
from backend.services.qa_orchestrator.clients import call_llm_gateway


def handle_generic_task(event: dict) -> dict:
    llm_response = call_llm_gateway(event)
    raw_output = llm_response.get("output", {}) if isinstance(llm_response, dict) else {}
    llm_output = normalize_llm_output(raw_output, event, llm_response)
    artifact = build_structured_result(event, llm_output)
    return {
        "llm_response": llm_response,
        "llm_output": llm_output,
        "artifact": artifact,
    }
