from fastapi import FastAPI
from kafka import KafkaProducer
import logging
import os
import re
from typing import Any

from backend.services.qa_orchestrator.clients import (
    call_llm_gateway,
    get_effective_input_data,
    persist_result,
)
from backend.services.qa_orchestrator.runtime import OrchestratorRuntime

from backend.shared.normalization import (
    extract_json_from_text,
    normalize_text,
    normalize_text_list,
    normalize_steps,
    normalize_severity,
    normalize_risks,
    normalize_risk_strings,
    normalize_test_cases,
    recover_summary_and_test_cases,
    dedupe_preserve_order,
)

from backend.shared.artifacts import (
    QaTestPlan,
    QaTestCaseReviewReport,
    QaTestCaseBundle,
    QaRequirementAnalysis,
    QaReleaseReadinessReport,
    QaTestReport,
)

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

runtime = OrchestratorRuntime(
    kafka_bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
    consumer_group=CONSUMER_GROUP,
    task_created_topic=TASK_CREATED_TOPIC,
    task_status_topic=TASK_STATUS_TOPIC,
    database_url=DATABASE_URL,
    process_task_event=lambda event: process_task_event(event),
)


def _extract_requirements_under_test(event: dict) -> list[str]:
    input_data = _get_effective_input_data(event)
    if not isinstance(input_data, dict):
        return []

    requirements: list[str] = []

    story = input_data.get("story")
    if isinstance(story, str) and story.strip():
        requirements.append(story.strip())

    story_title = input_data.get("story_title")
    if isinstance(story_title, str) and story_title.strip():
        requirements.append(story_title.strip())

    story_description = input_data.get("story_description")
    if isinstance(story_description, str) and story_description.strip():
        requirements.append(story_description.strip())

    text_value = input_data.get("text")
    if isinstance(text_value, str) and text_value.strip():
        requirements.append(text_value.strip())

    acceptance_criteria = input_data.get("acceptance_criteria")
    if isinstance(acceptance_criteria, list):
        for item in acceptance_criteria:
            if isinstance(item, str) and item.strip():
                requirements.append(item.strip())

    release_scope = input_data.get("release_scope")
    if isinstance(release_scope, list):
        for item in release_scope:
            if isinstance(item, str) and item.strip():
                requirements.append(item.strip())

    direct_requirements = input_data.get("requirements")
    if isinstance(direct_requirements, list):
        for item in direct_requirements:
            if isinstance(item, str) and item.strip():
                requirements.append(item.strip())

    deduped: list[str] = []
    seen: set[str] = set()
    for item in requirements:
        key = re.sub(r"\s+", " ", item).strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(item.strip())

    return deduped



# ---------------------------------------------------------------------------
# Aliases to shared normalisation helpers (logic moved to backend.shared.normalization)
# ---------------------------------------------------------------------------
_extract_json_from_text     = extract_json_from_text
_normalize_text             = normalize_text
_normalize_text_list        = normalize_text_list
_normalize_steps            = normalize_steps
_normalize_severity         = normalize_severity
_normalize_risks            = normalize_risks
_normalize_risk_strings     = normalize_risk_strings
_normalize_test_cases       = normalize_test_cases
_recover_summary_and_test_cases = recover_summary_and_test_cases
_dedupe_preserve_order      = dedupe_preserve_order


def _normalize_llm_output(raw_output: Any, event: dict, llm_response: Any) -> dict:
    llm_output = raw_output

    if isinstance(llm_output, str):
        parsed = _extract_json_from_text(llm_output)
        llm_output = parsed if isinstance(parsed, dict) else {"summary": llm_output}

    if not isinstance(llm_output, dict):
        llm_output = {"summary": str(llm_output)}

    summary_value = llm_output.get("summary")
    parsed_summary = _extract_json_from_text(summary_value)

    if isinstance(parsed_summary, dict):
        merged = dict(llm_output)
        merged.update(parsed_summary)
        llm_output = merged

    context = llm_response.get("context") if isinstance(llm_response, dict) else None
    if isinstance(context, dict):
        debug_context = context.get("debug_context")
        if isinstance(debug_context, dict):
            llm_output["debug_context"] = debug_context

    if not isinstance(llm_output.get("summary"), str):
        llm_output["summary"] = _normalize_text(str(llm_output.get("summary", "")))

    return llm_output



def _format_handoff_section(title: str, items: list[str]) -> str:
    if not items:
        return ""
    lines = [f"{title}:"]
    for item in items:
        lines.append(f"- {item}")
    return "\n".join(lines)


def _build_test_case_handoff_prompt_from_artifact(artifact: dict) -> str:
    summary = _normalize_text(str(artifact.get("summary", "")))
    requirements_under_test = _normalize_text_list(artifact.get("requirements_under_test", []))
    clarity_findings = _normalize_text_list(artifact.get("clarity_findings", []))
    coverage_gaps = _normalize_text_list(artifact.get("coverage_gaps", []))
    assumptions = _normalize_text_list(artifact.get("assumptions", []))
    questions_for_refinement = _normalize_text_list(artifact.get("questions_for_refinement", []))
    suggested_test_areas = _normalize_text_list(artifact.get("suggested_test_areas", []))

    raw_risks = artifact.get("risks", [])
    risk_lines: list[str] = []
    if isinstance(raw_risks, list):
        for item in raw_risks:
            if isinstance(item, dict):
                title = _normalize_text(str(item.get("title", "")))
                severity = _normalize_severity(item.get("severity", "medium"))
                description = _normalize_text(str(item.get("description", "")))
                if title:
                    line = f"[{severity}] {title}"
                    if description:
                        line += f" — {description}"
                    risk_lines.append(line)
            elif isinstance(item, str):
                value = _normalize_text(item)
                if value:
                    risk_lines.append(value)

    parts = [
        "Generate manual QA test cases from the requirement analysis below.",
        "Prioritize coverage of listed risks, ambiguity areas, coverage gaps, and refinement questions.",
        "Stay grounded in the provided requirement and do not invent unsupported business rules.",
    ]

    if summary:
        parts.append(f"Analysis summary: {summary}")

    for title, items in [
        ("Requirements under test", requirements_under_test),
        ("Clarity findings", clarity_findings),
        ("Coverage gaps", coverage_gaps),
        ("Assumptions", assumptions),
        ("Risks", risk_lines),
        ("Questions for refinement", questions_for_refinement),
        ("Suggested test areas", suggested_test_areas),
    ]:
        section = _format_handoff_section(title, items)
        if section:
            parts.append(section)

    parts.append(
        "Output should focus on practical manual QA coverage with positive, negative, edge, and error-handling scenarios where justified by the analysis."
    )

    return "\n\n".join(parts)



def _derive_requirement_health(
    clarity_findings: list[str],
    coverage_gaps: list[str],
    risks: list[str],
    questions_for_refinement: list[str],
    qa_priority: str,
) -> tuple[str, int]:
    score = 100
    score -= min(len(clarity_findings) * 8, 24)
    score -= min(len(coverage_gaps) * 10, 30)
    score -= min(len(questions_for_refinement) * 7, 21)
    score -= min(len(risks) * 8, 24)

    priority = _normalize_text(qa_priority).lower()
    if priority == "high":
        score -= 10
    elif priority == "medium":
        score -= 4

    score = max(0, min(100, score))

    if score >= 80:
        return "green", score
    if score >= 55:
        return "yellow", score
    return "red", score


def _build_requirement_analysis_artifact(event: dict, llm_output: dict, provider: str, model_name: str) -> dict:
    input_data = _get_effective_input_data(event)
    requirements_under_test = [_normalize_text(x) for x in _extract_requirements_under_test(event)]

    if not requirements_under_test:
        text_value = input_data.get("text")
        if isinstance(text_value, str) and text_value.strip():
            requirements_under_test = [_normalize_text(text_value)]

    requirements_under_test = _dedupe_preserve_order(requirements_under_test)

    summary = _normalize_text(llm_output.get("summary", ""))
    clarity_findings = _normalize_text_list(llm_output.get("clarity_findings", []))
    coverage_gaps = _normalize_text_list(llm_output.get("coverage_gaps", []))
    assumptions = _normalize_text_list(llm_output.get("assumptions", []))
    risks = _normalize_risk_strings(llm_output.get("risks", []))
    questions_for_refinement = _normalize_text_list(llm_output.get("questions_for_refinement", []))
    suggested_test_areas = _normalize_text_list(llm_output.get("suggested_test_areas", []))

    weak_signal_count = sum(
        1
        for bucket in [
            clarity_findings,
            coverage_gaps,
            assumptions,
            risks,
            questions_for_refinement,
            suggested_test_areas,
        ]
        if bucket
    )

    if weak_signal_count <= 1:
        coverage_gaps = _dedupe_preserve_order(
            coverage_gaps + ["Model returned minimal analytical detail; manual QA review is recommended"]
        )

    qa_priority = _normalize_text(llm_output.get("qa_priority", "")) or "medium"
    qa_health, readiness_score = _derive_requirement_health(
        clarity_findings=clarity_findings,
        coverage_gaps=coverage_gaps,
        risks=risks,
        questions_for_refinement=questions_for_refinement,
        qa_priority=qa_priority,
    )

    artifact = QaRequirementAnalysis(
        summary=summary,
        clarity_findings=clarity_findings,
        coverage_gaps=coverage_gaps,
        assumptions=assumptions,
        risks=risks,
        questions_for_refinement=questions_for_refinement,
        suggested_test_areas=suggested_test_areas,
        qa_priority=qa_priority,
        qa_health=qa_health,
        readiness_score=readiness_score,
        requirements_under_test=requirements_under_test,
        source_context={
            "story_id": _normalize_text(str(input_data.get("story_id", ""))),
            "jira_key": _normalize_text(str(input_data.get("jira_key", ""))),
            "story_title": _normalize_text(str(input_data.get("story_title", ""))),
            "service_name": _normalize_text(str(input_data.get("service_name", event.get("service_name", "")))),
            "owner_team": _normalize_text(str(input_data.get("owner_team", ""))),
            "platforms": input_data.get("platforms", []) if isinstance(input_data.get("platforms", []), list) else [],
            "linked_services": input_data.get("linked_services", []) if isinstance(input_data.get("linked_services", []), list) else [],
        },
        generated_by=_build_generated_by(provider, model_name, "requirements_analysis"),
    )
    return artifact.model_dump()


def _build_test_case_review_artifact(event: dict, llm_output: dict, provider: str, model_name: str) -> dict:
    artifact = QaTestCaseReviewReport(
        summary=_normalize_text(llm_output.get("summary", "")),
        structure_issues=_normalize_text_list(llm_output.get("structure_issues", [])),
        clarity_issues=_normalize_text_list(llm_output.get("clarity_issues", [])),
        coverage_issues=_normalize_text_list(llm_output.get("coverage_issues", [])),
        duplicates=_normalize_text_list(llm_output.get("duplicates", [])),
        missing_negative_cases=_normalize_text_list(llm_output.get("missing_negative_cases", [])),
        improvement_actions=_normalize_text_list(llm_output.get("improvement_actions", [])),
        review_score=_normalize_text(llm_output.get("review_score", "")) or "needs_review",
        generated_by=_build_generated_by(provider, model_name, "manual_test_case_review"),
    )
    return artifact.model_dump()


def _build_test_plan_artifact(event: dict, llm_output: dict, provider: str, model_name: str) -> dict:
    artifact = QaTestPlan(
        summary=_normalize_text(llm_output.get("summary", "")),
        scope_in=_normalize_text_list(llm_output.get("scope_in", [])),
        scope_out=_normalize_text_list(llm_output.get("scope_out", [])),
        test_levels=_normalize_text_list(llm_output.get("test_levels", [])),
        priority_matrix=_normalize_text_list(llm_output.get("priority_matrix", [])),
        dependencies=_normalize_text_list(llm_output.get("dependencies", [])),
        env_requirements=_normalize_text_list(llm_output.get("env_requirements", [])),
        test_data_needs=_normalize_text_list(llm_output.get("test_data_needs", [])),
        entry_criteria=_normalize_text_list(llm_output.get("entry_criteria", [])),
        exit_criteria=_normalize_text_list(llm_output.get("exit_criteria", [])),
        staffing_notes=_normalize_text_list(llm_output.get("staffing_notes", [])),
        generated_by=_build_generated_by(provider, model_name, "test_plan"),
    )
    return artifact.model_dump()


def _build_test_report_artifact(event: dict, llm_output: dict, provider: str, model_name: str) -> dict:
    artifact = QaTestReport(
        summary=_normalize_text(llm_output.get("summary", "")),
        tested_scope=_normalize_text_list(llm_output.get("tested_scope", [])),
        not_tested_scope=_normalize_text_list(llm_output.get("not_tested_scope", [])),
        pass_fail_blocked=llm_output.get("pass_fail_blocked", {}) if isinstance(llm_output.get("pass_fail_blocked", {}), dict) else {},
        key_defects=_normalize_text_list(llm_output.get("key_defects", [])),
        blockers=_normalize_text_list(llm_output.get("blockers", [])),
        risks=_normalize_text_list(llm_output.get("risks", [])),
        quality_assessment=_normalize_text(llm_output.get("quality_assessment", "")),
        recommendation=_normalize_text(llm_output.get("recommendation", "")),
        signoff_status=_normalize_text(llm_output.get("signoff_status", "")) or "pending",
        generated_by=_build_generated_by(provider, model_name, "test_report"),
    )
    return artifact.model_dump()


def _build_release_readiness_artifact(event: dict, llm_output: dict, provider: str, model_name: str) -> dict:
    artifact = QaReleaseReadinessReport(
        summary=_normalize_text(llm_output.get("summary", "")),
        release_decision=_normalize_text(llm_output.get("release_decision", "")) or "caution",
        decision_reasoning=_normalize_text_list(llm_output.get("decision_reasoning", [])),
        must_fix_before_release=_normalize_text_list(llm_output.get("must_fix_before_release", [])),
        acceptable_known_issues=_normalize_text_list(llm_output.get("acceptable_known_issues", [])),
        follow_up_actions=_normalize_text_list(llm_output.get("follow_up_actions", [])),
        generated_by=_build_generated_by(provider, model_name, "release_readiness"),
    )
    return artifact.model_dump()


def _build_structured_result(event: dict, llm_output: dict) -> dict:
    provider = llm_output.get("provider", event.get("model_provider", "unknown"))
    model_name = llm_output.get("model_name", event.get("model_name", "unknown"))
    task_type = event.get("task_type", "test_case_generation")

    if task_type == "requirements_analysis":
        return _build_requirement_analysis_artifact(event, llm_output, provider, model_name)

    if task_type == "manual_test_case_review":
        return _build_test_case_review_artifact(event, llm_output, provider, model_name)

    if task_type == "test_plan":
        return _build_test_plan_artifact(event, llm_output, provider, model_name)

    if task_type == "test_report":
        return _build_test_report_artifact(event, llm_output, provider, model_name)

    if task_type == "release_readiness":
        return _build_release_readiness_artifact(event, llm_output, provider, model_name)

    requirements_under_test_raw = _extract_requirements_under_test(event)
    requirements_under_test = [_normalize_text(r) for r in requirements_under_test_raw]
    summary, test_cases = _recover_summary_and_test_cases(llm_output)

    coverage_areas = []
    if requirements_under_test:
        coverage_areas.append("requirements_analysis")
    if task_type == "test_case_generation":
        coverage_areas.extend(["functional", "positive_negative"])

    artifact = QaTestCaseBundle(
        summary=summary,
        requirements_under_test=requirements_under_test,
        assumptions=[],
        risks=[],
        coverage={
            "areas": coverage_areas,
            "priority": "medium",
        },
        test_cases=test_cases,
        generated_by=_build_generated_by(provider, model_name, task_type),
    )
    return artifact.model_dump()




def process_task_event(event: dict) -> None:
    task_id = event.get("task_id")
    if not task_id:
        logger.warning("Skipping event without task_id: %s", event)
        return

    try:
        runtime.publish_status(task_id, "running", TASK_STATUS_TOPIC, {"message": "Task is being processed"})

        llm_response = call_llm_gateway(event)
        raw_output = llm_response.get("output", {}) if isinstance(llm_response, dict) else {}
        llm_output = _normalize_llm_output(raw_output, event, llm_response)

        artifact = _build_structured_result(event, llm_output)
        persist_result(task_id, artifact)

        runtime.publish_status(
            task_id,
            "completed",
            TASK_COMPLETED_TOPIC,
            {
                "message": "Task completed successfully",
                "artifact_type": artifact.get("artifact_type"),
            },
        )
    except Exception as exc:
        logger.exception("Task processing failed for %s: %s", task_id, exc)
        runtime.publish_status(
            task_id,
            "failed",
            TASK_FAILED_TOPIC,
            {"error": str(exc)},
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
