from fastapi import FastAPI
import logging
import os

from backend.services.qa_orchestrator.clients import persist_result
from backend.services.qa_orchestrator.dispatcher import get_task_handler
from backend.services.qa_orchestrator.runtime import OrchestratorRuntime

app = FastAPI(title="qa-orchestrator")
logger = logging.getLogger("qa-orchestrator")
logging.basicConfig(level=logging.INFO)

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
TASK_CREATED_TOPIC = "qa.agent.task.created"
TASK_STATUS_TOPIC = "qa.agent.task.status"
TASK_COMPLETED_TOPIC = "qa.agent.task.completed"
TASK_FAILED_TOPIC = "qa.agent.task.failed"
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://qa:qa@127.0.0.1:5432/qa_agent")
CONSUMER_GROUP = os.getenv("QA_ORCHESTRATOR_GROUP", "qa-orchestrator")

TASK_TYPE_TO_AGENT = {
    "test_case_generation": "test_case_generator",
    "requirements_analysis": "requirements_qa_analyst",
    "manual_test_case_review": "manual_test_case_reviewer",
    "test_plan": "test_plan_builder",
    "test_report": "test_report_writer",
    "release_readiness": "release_readiness",
}


def process_task_event(event: dict) -> None:
    task_id = event.get("task_id")
    if not task_id:
        logger.warning("Skipping event without task_id: %s", event)
        return

    task_type = event.get("task_type", "test_case_generation")
    handler = get_task_handler(task_type)

    try:
        runtime.publish_status(task_id, "running", TASK_STATUS_TOPIC, {"message": f"Processing {task_type}"})

        result = handler(event)
        artifact = result.get("artifact", {}) if isinstance(result, dict) else {}
        persist_result(task_id, artifact)

        runtime.publish_status(
            task_id,
            "completed",
            TASK_COMPLETED_TOPIC,
            {
                "message": "Task completed successfully",
                "artifact_type": artifact.get("artifact_type"),
                "task_type": task_type,
            },
        )
    except Exception as exc:
        logger.exception("Task processing failed for %s: %s", task_id, exc)
        runtime.publish_status(
            task_id,
            "failed",
            TASK_FAILED_TOPIC,
            {"error": str(exc), "task_type": task_type},
        )


runtime = OrchestratorRuntime(
    kafka_bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
    consumer_group=CONSUMER_GROUP,
    task_created_topic=TASK_CREATED_TOPIC,
    task_status_topic=TASK_STATUS_TOPIC,
    database_url=DATABASE_URL,
    process_task_event=process_task_event,
)


@app.on_event("startup")
def startup_event():
    runtime.startup()


@app.on_event("shutdown")
def shutdown_event():
    runtime.shutdown()


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "qa-orchestrator",
        "consumer_running": runtime.consumer_thread is not None and runtime.consumer_thread.is_alive(),
    }
