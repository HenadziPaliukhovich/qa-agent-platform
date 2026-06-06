import re
from typing import Any

from backend.services.qa_orchestrator.clients import get_effective_input_data
from backend.shared.artifacts import (
    QaRequirementAnalysis,
    QaReleaseReadinessReport,
    QaTestCaseBundle,
    QaTestCaseReviewReport,
    QaTestPlan,
    QaTestReport,
)
from backend.shared.normalization import (
    dedupe_preserve_order,
    extract_json_from_text,
    normalize_risk_strings,
    normalize_risks,
    normalize_severity,
    normalize_steps,
    normalize_test_cases,
    normalize_text,
    normalize_text_list,
    recover_summary_and_test_cases,
)


_extract_json_from_text = extract_json_from_text
_normalize_text = normalize_text
_normalize_text_list = normalize_text_list
_normalize_steps = normalize_steps
_normalize_severity = normalize_severity
_normalize_risks = normalize_risks
_normalize_risk_strings = normalize_risk_strings
_normalize_test_cases = normalize_test_cases
_recover_summary_and_test_cases = recover_summary_and_test_cases
_dedupe_preserve_order = dedupe_preserve_order


def extract_requirements_under_test(event: dict) -> list[str]:
    input_data = get_effective_input_data(event)
    if not isinstance(input_data, dict):
        return []

    requirements: list[str] = []
    for key in ["story", "story_title", "story_description", "text"]:
        value = input_data.get(key)
        if isinstance(value, str) and value.strip():
            requirements.append(value.strip())

    for key in ["acceptance_criteria", "release_scope", "requirements"]:
        values = input_data.get(key)
        if isinstance(values, list):
            for item in values:
                if isinstance(item, str) and item.strip():
                    requirements.append(item.strip())

    deduped: list[str] = []
    seen: set[str] = set()
    for item in requirements:
        normalized = re.sub(r"\s+", " ", item).strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(item.strip())
    return deduped


def normalize_llm_output(raw_output: Any, event: dict, llm_response: Any) -> dict:
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


def format_handoff_section(title: str, items: list[str]) -> str:
    if not items:
        return ""
    lines = [f"{title}:"]
    for item in items:
        lines.append(f"- {item}")
    return "\n".join(lines)


def build_test_case_handoff_prompt_from_artifact(artifact: dict) -> str:
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
                severity = _normalize_severity(str(item.get("severity", "medium")))
                description = _normalize_text(str(item.get("description", "")))
                risk_lines.append(f"{severity.upper()}: {title} — {description}".strip(" —"))
            elif isinstance(item, str) and item.strip():
                risk_lines.append(item.strip())

    sections = [
        summary and f"Summary:\n{summary}",
        format_handoff_section("Requirements under test", requirements_under_test),
        format_handoff_section("Clarity findings", clarity_findings),
        format_handoff_section("Coverage gaps", coverage_gaps),
        format_handoff_section("Assumptions", assumptions),
        format_handoff_section("Questions for refinement", questions_for_refinement),
        format_handoff_section("Suggested test areas", suggested_test_areas),
        format_handoff_section("Risks", risk_lines),
    ]
    return "\n\n".join(section for section in sections if section).strip()


def build_generated_by(provider: str, model_name: str, task_type: str) -> dict:
    return {
        "provider": _normalize_text(provider or "stub"),
        "model_name": _normalize_text(model_name or "stub-default"),
        "task_type": task_type,
    }


def build_test_case_bundle_artifact(event: dict, llm_output: dict, provider: str, model_name: str) -> dict:
    input_data = get_effective_input_data(event)
    generated_cases = _normalize_test_cases(llm_output.get("test_cases", []))
    recovered_cases = _normalize_test_cases(input_data.get("test_cases", []))
    final_cases = generated_cases or recovered_cases

    artifact = QaTestCaseBundle(
        summary=_normalize_text(llm_output.get("summary", "")),
        test_cases=final_cases,
        generated_by=build_generated_by(provider, model_name, "test_case_generation"),
    )
    return artifact.model_dump()


def build_requirements_analysis_artifact(event: dict, llm_output: dict, provider: str, model_name: str) -> dict:
    input_data = get_effective_input_data(event)
    artifact = QaRequirementAnalysis(
        summary=_normalize_text(llm_output.get("summary", "")),
        requirements_under_test=extract_requirements_under_test(event),
        clarity_findings=_normalize_text_list(llm_output.get("clarity_findings", [])),
        coverage_gaps=_normalize_text_list(llm_output.get("coverage_gaps", [])),
        assumptions=_normalize_text_list(llm_output.get("assumptions", [])),
        questions_for_refinement=_normalize_text_list(llm_output.get("questions_for_refinement", [])),
        suggested_test_areas=_normalize_text_list(llm_output.get("suggested_test_areas", [])),
        risks=_normalize_risks(llm_output.get("risks", [])),
        source_context={
            "story_id": _normalize_text(str(input_data.get("story_id", ""))),
            "jira_key": _normalize_text(str(input_data.get("jira_key", ""))),
            "story_title": _normalize_text(str(input_data.get("story_title", ""))),
            "service_name": _normalize_text(str(input_data.get("service_name", event.get("service_name", "")))),
            "owner_team": _normalize_text(str(input_data.get("owner_team", ""))),
            "platforms": input_data.get("platforms", []) if isinstance(input_data.get("platforms", []), list) else [],
            "linked_services": input_data.get("linked_services", []) if isinstance(input_data.get("linked_services", []), list) else [],
        },
        generated_by=build_generated_by(provider, model_name, "requirements_analysis"),
    )
    return artifact.model_dump()


def build_test_case_review_artifact(event: dict, llm_output: dict, provider: str, model_name: str) -> dict:
    artifact = QaTestCaseReviewReport(
        summary=_normalize_text(llm_output.get("summary", "")),
        structure_issues=_normalize_text_list(llm_output.get("structure_issues", [])),
        clarity_issues=_normalize_text_list(llm_output.get("clarity_issues", [])),
        coverage_issues=_normalize_text_list(llm_output.get("coverage_issues", [])),
        duplicates=_normalize_text_list(llm_output.get("duplicates", [])),
        missing_negative_cases=_normalize_text_list(llm_output.get("missing_negative_cases", [])),
        improvement_actions=_normalize_text_list(llm_output.get("improvement_actions", [])),
        review_score=_normalize_text(llm_output.get("review_score", "")) or "needs_review",
        generated_by=build_generated_by(provider, model_name, "manual_test_case_review"),
    )
    return artifact.model_dump()


def build_test_plan_artifact(event: dict, llm_output: dict, provider: str, model_name: str) -> dict:
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
        generated_by=build_generated_by(provider, model_name, "test_plan"),
    )
    return artifact.model_dump()


def build_test_report_artifact(event: dict, llm_output: dict, provider: str, model_name: str) -> dict:
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
        generated_by=build_generated_by(provider, model_name, "test_report"),
    )
    return artifact.model_dump()


def build_release_readiness_artifact(event: dict, llm_output: dict, provider: str, model_name: str) -> dict:
    artifact = QaReleaseReadinessReport(
        summary=_normalize_text(llm_output.get("summary", "")),
        release_decision=_normalize_text(llm_output.get("release_decision", "")) or "caution",
        decision_reasoning=_normalize_text_list(llm_output.get("decision_reasoning", [])),
        must_fix_before_release=_normalize_text_list(llm_output.get("must_fix_before_release", [])),
        acceptable_known_issues=_normalize_text_list(llm_output.get("acceptable_known_issues", [])),
        follow_up_actions=_normalize_text_list(llm_output.get("follow_up_actions", [])),
        generated_by=build_generated_by(provider, model_name, "release_readiness"),
    )
    return artifact.model_dump()


def build_structured_result(event: dict, llm_output: dict) -> dict:
    provider = llm_output.get("provider", event.get("model_provider", "stub"))
    model_name = llm_output.get("model_name", event.get("model_name", "stub-default"))
    task_type = event.get("task_type", "test_case_generation")

    if task_type == "requirements_analysis":
        artifact = build_requirements_analysis_artifact(event, llm_output, provider, model_name)
        handoff_prompt = build_test_case_handoff_prompt_from_artifact(artifact)
        if handoff_prompt:
            artifact["suggested_next_prompt"] = handoff_prompt
        artifact["artifact_type"] = "qa_requirement_analysis"
        return artifact

    if task_type == "manual_test_case_review":
        artifact = build_test_case_review_artifact(event, llm_output, provider, model_name)
        artifact["artifact_type"] = "qa_test_case_review_report"
        return artifact

    if task_type == "test_plan":
        artifact = build_test_plan_artifact(event, llm_output, provider, model_name)
        artifact["artifact_type"] = "qa_test_plan"
        return artifact

    if task_type == "test_report":
        artifact = build_test_report_artifact(event, llm_output, provider, model_name)
        artifact["artifact_type"] = "qa_test_report"
        return artifact

    if task_type == "release_readiness":
        artifact = build_release_readiness_artifact(event, llm_output, provider, model_name)
        artifact["artifact_type"] = "qa_release_readiness_report"
        return artifact

    artifact = build_test_case_bundle_artifact(event, llm_output, provider, model_name)
    artifact["artifact_type"] = "qa_test_case_bundle"
    return artifact
