from backend.services.qa_orchestrator.handlers import (
    handle_generic_task,
    handle_requirements_analysis,
    handle_test_case_generation,
)

TASK_HANDLERS = {
    "test_case_generation": handle_test_case_generation,
    "requirements_analysis": handle_requirements_analysis,
    "manual_test_case_review": handle_generic_task,
    "test_plan": handle_generic_task,
    "test_report": handle_generic_task,
    "release_readiness": handle_generic_task,
}


def get_task_handler(task_type: str):
    return TASK_HANDLERS.get(task_type, handle_generic_task)
