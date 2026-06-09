from backend.services.qa_orchestrator.builders import (
    build_structured_result,
    normalize_llm_output,
)
from backend.services.qa_orchestrator.clients import call_llm_gateway, get_effective_input_data, search_domain_context
from backend.services.qa_orchestrator.roadmap_executor import (
    build_default_roadmap_steps,
    build_roadmap_prompt,
    roadmap_step_to_llm_payload,
)


def _normalize_simple_list(value) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            continue
        text = " ".join(item.split()).strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def _extract_requirement_lines(input_data: dict) -> list[str]:
    items: list[str] = []
    for key in ["acceptance_criteria", "requirements"]:
        values = input_data.get(key)
        if isinstance(values, list):
            items.extend(item for item in values if isinstance(item, str))

    for key in ["requirement_text", "text", "summary", "title"]:
        value = input_data.get(key)
        if isinstance(value, str) and value.strip():
            items.append(value)

    return _normalize_simple_list(items)


def _enrich_requirements_analysis_artifact(artifact: dict, input_data: dict) -> dict:
    enriched = dict(artifact) if isinstance(artifact, dict) else {}
    lines = _extract_requirement_lines(input_data if isinstance(input_data, dict) else {})
    joined = "\n".join(lines).lower()

    if not _normalize_simple_list(enriched.get("requirements_under_test", [])):
        enriched["requirements_under_test"] = lines[:10] or ["Requirement details were not provided."]

    if not isinstance(enriched.get("summary"), str) or not enriched.get("summary", "").strip():
        title = str(input_data.get("title", "")).strip()
        ac_count = len(input_data.get("acceptance_criteria", [])) if isinstance(input_data.get("acceptance_criteria", []), list) else 0
        enriched["summary"] = (
            f"QA analysis for {title or 'the provided requirement'} with {ac_count} acceptance criteria. "
            f"The artifact highlights ambiguities, missing coverage, and suggested test areas based only on the provided input."
        ).strip()

    clarity_findings = _normalize_simple_list(enriched.get("clarity_findings", []))
    if not clarity_findings:
        trigger_map = {
            "valid": "The term 'valid' is ambiguous unless validation rules are explicitly defined.",
            "eligible": "The term 'eligible' is ambiguous unless eligibility rules are explicitly defined.",
            "clear error": "The phrase 'clear error' is ambiguous unless expected error content and presentation are defined.",
            "within configured limits": "Configured limits are referenced but the concrete boundary rules are not provided.",
            "updated balance": "Balance update expectations are mentioned but the exact expected state transition is not fully defined.",
        }
        for needle, message in trigger_map.items():
            if needle in joined:
                clarity_findings.append(message)
        if not clarity_findings:
            clarity_findings.append("Some requirement wording remains high-level and may need more explicit acceptance detail for precise QA coverage.")
        enriched["clarity_findings"] = _normalize_simple_list(clarity_findings)

    coverage_gaps = _normalize_simple_list(enriched.get("coverage_gaps", []))
    if not coverage_gaps:
        if all(token not in joined for token in ["invalid", "validation", "error"]):
            coverage_gaps.append("Validation and invalid-input scenarios are not explicitly described.")
        if all(token not in joined for token in ["fail", "failed", "failure", "error", "declined"]):
            coverage_gaps.append("Failure handling scenarios are not explicitly described.")
        if all(token not in joined for token in ["duplicate", "double", "retry", "again"]):
            coverage_gaps.append("Repeat submission or duplicate action handling is not explicitly described.")
        if all(token not in joined for token in ["limit", "min", "max"]):
            coverage_gaps.append("Boundary conditions or configurable limits are not explicitly described.")
        if not coverage_gaps:
            coverage_gaps.append("Alternative and edge-case paths may need stronger coverage definition.")
        enriched["coverage_gaps"] = _normalize_simple_list(coverage_gaps)

    assumptions = _normalize_simple_list(enriched.get("assumptions", []))
    if not assumptions:
        assumptions.append("The described flow is intended to be available to the target user in the tested environment.")
        enriched["assumptions"] = assumptions

    questions = _normalize_simple_list(enriched.get("questions_for_refinement", []))
    if not questions:
        if "valid" in joined:
            questions.append("What exact validation rules determine whether the input is valid or invalid?")
        if "eligible" in joined:
            questions.append("What exact rules determine whether a user or action is eligible?")
        if "error" in joined or "failed" in joined:
            questions.append("What specific error cases and user-visible messages are expected for failure scenarios?")
        if "limit" in joined or "within configured limits" in joined:
            questions.append("What are the exact configured limits or boundary values that should be enforced?")
        if not questions:
            questions.append("Which edge cases or alternative paths should be treated as mandatory coverage for this requirement?")
        enriched["questions_for_refinement"] = _normalize_simple_list(questions)

    test_areas = _normalize_simple_list(enriched.get("suggested_test_areas", []))
    if not test_areas:
        test_areas.extend([
            "Happy path",
            "Validation and invalid input handling",
            "Failure and error handling",
        ])
        if "eligible" in joined:
            test_areas.append("Eligibility rules and non-eligible scenarios")
        if "balance" in joined:
            test_areas.append("State consistency and balance updates")
        if any(token in joined for token in ["submit", "confirm"]):
            test_areas.append("Repeat submission and idempotency")
        enriched["suggested_test_areas"] = _normalize_simple_list(test_areas)

    risks = enriched.get("risks", [])
    if not isinstance(risks, list) or not risks:
        enriched["risks"] = [
            "Ambiguous or incomplete requirements may lead to inconsistent implementation and insufficient QA coverage.",
        ]

    return enriched


def _build_handler_result(event: dict, llm_response: dict | None) -> dict:
    raw_output = llm_response.get("output", {}) if isinstance(llm_response, dict) else {}
    llm_output = normalize_llm_output(raw_output, event, llm_response)
    artifact = build_structured_result(event, llm_output)

    task_type = event.get("task_type", "") if isinstance(event, dict) else ""
    input_data = get_effective_input_data(event) if isinstance(event, dict) else {}
    if task_type == "requirements_analysis" and isinstance(artifact, dict):
        artifact = _enrich_requirements_analysis_artifact(artifact, input_data)
        if isinstance(llm_output, dict):
            llm_output = dict(llm_output)
            llm_output.setdefault("summary", artifact.get("summary", ""))
            llm_output["requirements_under_test"] = artifact.get("requirements_under_test", [])
            llm_output["clarity_findings"] = artifact.get("clarity_findings", [])
            llm_output["coverage_gaps"] = artifact.get("coverage_gaps", [])
            llm_output["assumptions"] = artifact.get("assumptions", [])
            llm_output["questions_for_refinement"] = artifact.get("questions_for_refinement", [])
            llm_output["suggested_test_areas"] = artifact.get("suggested_test_areas", [])
            llm_output["risks"] = artifact.get("risks", [])
            artifact = build_structured_result(event, llm_output)

    llm_context = llm_response.get("context") if isinstance(llm_response, dict) and isinstance(llm_response.get("context"), dict) else {}
    title = input_data.get("title") if isinstance(input_data, dict) else ""
    requirements = input_data.get("requirements") if isinstance(input_data, dict) else []
    executed_tests = input_data.get("executed_tests") if isinstance(input_data, dict) else []

    fallback_reason = None
    fallback_output = None

    if task_type == "test_case_generation" and isinstance(artifact, dict) and not artifact.get("test_cases"):
        fallback_reason = "empty_test_cases"
        fallback_output = {
            "summary": llm_output.get("summary") or f"Fallback test cases for {title or 'Untitled task'}",
            "requirements_under_test": requirements if isinstance(requirements, list) else [],
            "coverage": {
                "areas": ["happy path", "validation", "error handling"],
                "priority": "high",
            },
            "test_cases": [
                {
                    "id": "TC-001",
                    "title": f"{title or 'Untitled task'}: happy path",
                    "steps": [
                        "Open the flow",
                        "Provide valid input",
                        "Submit the action",
                    ],
                    "expected_result": "Flow completes successfully",
                    "priority": "high",
                    "type": "functional",
                },
                {
                    "id": "TC-002",
                    "title": f"{title or 'Untitled task'}: validation handling",
                    "steps": [
                        "Open the flow",
                        "Submit invalid or incomplete input",
                    ],
                    "expected_result": "Validation feedback is shown",
                    "priority": "high",
                    "type": "negative",
                },
                {
                    "id": "TC-003",
                    "title": f"{title or 'Untitled task'}: failure path",
                    "steps": [
                        "Open the flow",
                        "Trigger or simulate provider or service failure",
                    ],
                    "expected_result": "A clear error state is shown and data remains consistent",
                    "priority": "medium",
                    "type": "resilience",
                },
            ],
            "assumptions": [
                "The target flow is reachable in the selected environment.",
            ],
            "risks": llm_output.get("risks") or [
                "Generated artifact was empty, deterministic fallback test cases were applied.",
            ],
            "debug_context": llm_context.get("debug_context", {}),
            "fallback": True,
        }

    elif task_type == "requirements_analysis" and isinstance(artifact, dict) and not artifact.get("requirements_under_test"):
        fallback_reason = "empty_requirements_under_test"
        fallback_requirements = requirements if isinstance(requirements, list) and requirements else [
            title or "Requirement details were not provided.",
        ]
        fallback_output = {
            "summary": llm_output.get("summary") or "Deterministic fallback requirements analysis was applied.",
            "requirements_under_test": fallback_requirements,
            "clarity_findings": llm_output.get("clarity_findings") or [
                "Requirements are high-level and may need more concrete acceptance criteria.",
            ],
            "coverage_gaps": llm_output.get("coverage_gaps") or [
                "Negative scenarios and service failure handling are not explicitly described.",
            ],
            "assumptions": llm_output.get("assumptions") or [
                "The described flow is available to the target user role.",
            ],
            "questions_for_refinement": llm_output.get("questions_for_refinement") or [
                "What are the expected validation rules and error messages?",
            ],
            "suggested_test_areas": llm_output.get("suggested_test_areas") or [
                "Happy path",
                "Validation handling",
                "Error recovery",
            ],
            "risks": llm_output.get("risks") or [
                "Generated artifact was missing requirements_under_test, deterministic fallback analysis was applied.",
            ],
            "debug_context": llm_context.get("debug_context", {}),
            "fallback": True,
        }

    elif task_type == "test_report" and isinstance(artifact, dict) and not artifact.get("summary"):
        fallback_reason = "empty_summary"
        tested_scope = executed_tests if isinstance(executed_tests, list) else []
        fallback_output = {
            "summary": "Deterministic fallback smoke report was applied.",
            "tested_scope": tested_scope,
            "not_tested_scope": llm_output.get("not_tested_scope") or [],
            "pass_fail_blocked": llm_output.get("pass_fail_blocked") or {
                "passed": len(tested_scope),
                "failed": 0,
                "blocked": 0,
            },
            "key_findings": llm_output.get("key_findings") or [
                "Smoke scenarios executed through the QA agent pipeline.",
            ],
            "key_defects": llm_output.get("key_defects") or [],
            "blockers": llm_output.get("blockers") or [],
            "open_issues": llm_output.get("open_issues") or [],
            "risks": llm_output.get("risks") or [
                "Report content was sparse, deterministic fallback summary was applied.",
            ],
            "quality_assessment": llm_output.get("quality_assessment") or "Basic smoke execution completed without reported blockers.",
            "recommendation": llm_output.get("recommendation") or "Proceed with deeper regression and domain-specific validation.",
            "signoff_status": llm_output.get("signoff_status") or "pending",
            "debug_context": llm_context.get("debug_context", {}),
            "fallback": True,
        }

    if fallback_output is not None:
        llm_output = fallback_output
        artifact = build_structured_result(event, llm_output)
        if isinstance(artifact, dict):
            artifact.setdefault("processing_profile", {})
            if isinstance(artifact["processing_profile"], dict):
                artifact["processing_profile"]["fallback_applied"] = True
                artifact["processing_profile"]["fallback_reason"] = fallback_reason

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
    input_data = get_effective_input_data(event)
    metadata = enriched_event.get("metadata") if isinstance(enriched_event.get("metadata"), dict) else {}

    domain_id = event.get("domain_id")
    context_scope = event.get("context_scope") or "domain_default"
    selected_context_ids = event.get("selected_context_ids") or []

    retrieval_query_parts = []
    if isinstance(input_data, dict):
        for key in ["requirement_text", "requirements", "prompt", "text", "summary"]:
            value = input_data.get(key)
            if isinstance(value, str) and value.strip():
                retrieval_query_parts.append(value.strip())
    retrieval_query = "\n".join(retrieval_query_parts)[:2000]

    used_context = []
    if domain_id and retrieval_query:
        used_context = search_domain_context(
            domain_id=domain_id,
            query=retrieval_query,
            selected_context_ids=selected_context_ids if context_scope == "manual_selection" else [],
            limit=5,
        )

    enriched_input = dict(input_data) if isinstance(input_data, dict) else {}
    if used_context:
        enriched_input["domain_context"] = [
            {
                "context_file_id": item.get("context_file_id"),
                "chunk_id": item.get("chunk_id"),
                "chunk_index": item.get("chunk_index"),
                "title": item.get("title"),
                "content": item.get("content"),
            }
            for item in used_context
        ]
    enriched_event["input"] = enriched_input

    enriched_event["metadata"] = {
        **metadata,
        "specialized_handler": "requirements_analysis",
        "handoff_enabled": True,
        "domain_focus": "qa_requirements_analysis",
        "domain_id": domain_id,
        "context_scope": context_scope,
        "used_context_count": len(used_context),
    }
    llm_response = call_llm_gateway(enriched_event)
    result = _build_handler_result(enriched_event, llm_response)
    artifact = result.get("artifact") if isinstance(result, dict) else None
    if isinstance(artifact, dict):
        artifact["used_context"] = [
            {
                "context_file_id": item.get("context_file_id"),
                "title": item.get("title"),
                "chunk_id": item.get("chunk_id"),
                "chunk_index": item.get("chunk_index"),
                "preview": (item.get("content") or "")[:200],
            }
            for item in used_context
        ]
        if domain_id:
            artifact["domain_id"] = domain_id
        summary_text = str(artifact.get("summary", "")).strip()
        if not summary_text:
            title = str(enriched_input.get("title", "")).strip()
            story = str(enriched_input.get("story", "")).strip() or str(enriched_input.get("text", "")).strip()
            acceptance_criteria = enriched_input.get("acceptance_criteria", [])
            ac_count = len(acceptance_criteria) if isinstance(acceptance_criteria, list) else 0
            flow_hint = title or story or "the provided requirement"
            artifact["summary"] = (
                f"QA analysis for {flow_hint} with {ac_count} acceptance criteria. "
                f"The result highlights ambiguities, coverage gaps, risks, and suggested test areas based on the provided input."
            ).strip()
    return _apply_processing_profile(
        result,
        handler="handle_requirements_analysis",
        specialized=True,
        handoff_enabled=True,
        domain_context_used=bool(used_context),
        used_context_count=len(used_context),
    )


def handle_test_case_generation(event: dict) -> dict:
    enriched_event = dict(event)
    input_data = get_effective_input_data(event)
    metadata = enriched_event.get("metadata") if isinstance(enriched_event.get("metadata"), dict) else {}

    # --- domain context retrieval (same pattern as handle_requirements_analysis) ---
    domain_id = event.get("domain_id")
    context_scope = event.get("context_scope") or "domain_default"
    selected_context_ids = event.get("selected_context_ids") or []

    retrieval_query_parts = []
    if isinstance(input_data, dict):
        for key in ["requirement_text", "requirements", "prompt", "text", "summary", "title"]:
            value = input_data.get(key)
            if isinstance(value, str) and value.strip():
                retrieval_query_parts.append(value.strip())
        ac = input_data.get("acceptance_criteria")
        if isinstance(ac, list):
            retrieval_query_parts.extend(item for item in ac if isinstance(item, str) and item.strip())
    retrieval_query = "\n".join(retrieval_query_parts)[:2000]

    used_context: list[dict] = []
    if domain_id and retrieval_query:
        used_context = search_domain_context(
            domain_id=domain_id,
            query=retrieval_query,
            selected_context_ids=selected_context_ids if context_scope == "manual_selection" else [],
            limit=5,
        )
    # --- end domain context retrieval ---

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
        "domain_id": domain_id,
        "context_scope": context_scope,
        "used_context_count": len(used_context),
    }

    enriched_input = dict(input_data) if isinstance(input_data, dict) else {}
    if used_context:
        enriched_input["domain_context"] = [
            {
                "context_file_id": item.get("context_file_id"),
                "chunk_id": item.get("chunk_id"),
                "chunk_index": item.get("chunk_index"),
                "title": item.get("title"),
                "content": item.get("content"),
            }
            for item in used_context
        ]
    if analysis_handoff:
        enriched_input["analysis_handoff"] = analysis_handoff
        if analysis_handoff.get("suggested_next_prompt") and not enriched_input.get("prompt_hint"):
            enriched_input["prompt_hint"] = analysis_handoff.get("suggested_next_prompt")
    enriched_event["input"] = enriched_input

    llm_response = call_llm_gateway(enriched_event)
    result = _build_handler_result(enriched_event, llm_response)

    artifact = result.get("artifact") if isinstance(result, dict) else None
    if isinstance(artifact, dict):
        artifact["used_context"] = [
            {
                "context_file_id": item.get("context_file_id"),
                "title": item.get("title"),
                "chunk_id": item.get("chunk_id"),
                "chunk_index": item.get("chunk_index"),
                "preview": (item.get("content") or "")[:200],
            }
            for item in used_context
        ]
        if domain_id:
            artifact["domain_id"] = domain_id

    return _apply_processing_profile(
        result,
        handler="handle_test_case_generation",
        specialized=True,
        analysis_handoff_present=bool(analysis_handoff),
        derived_from_requirements=bool(analysis_handoff.get("requirements_under_test")),
        derived_from_gaps=bool(analysis_handoff.get("coverage_gaps")),
        domain_context_used=bool(used_context),
        used_context_count=len(used_context),
    )


def handle_roadmap_step_executor(event: dict) -> dict:
    enriched_event = dict(event)
    input_data = get_effective_input_data(event)
    metadata = enriched_event.get("metadata") if isinstance(enriched_event.get("metadata"), dict) else {}

    steps = build_default_roadmap_steps()
    requested_step_id = input_data.get("step_id") if isinstance(input_data, dict) else None

    selected_step = None
    if requested_step_id:
        selected_step = next((step for step in steps if step.id == requested_step_id), None)
    if selected_step is None and steps:
        selected_step = steps[0]

    if selected_step is None:
        enriched_event["metadata"] = {
            **metadata,
            "specialized_handler": "roadmap_step_executor",
            "roadmap_error": "no_steps_available",
        }
        enriched_event["input"] = {
            "prompt": "No roadmap steps are available to execute.",
        }
        llm_response = call_llm_gateway(enriched_event)
        result = _build_handler_result(enriched_event, llm_response)
        return _apply_processing_profile(
            result,
            handler="handle_roadmap_step_executor",
            specialized=True,
            roadmap_step_available=False,
        )

    extra_context = {
        "task_type": event.get("task_type", "roadmap_step_executor"),
        "requested_step_id": requested_step_id or "<auto>",
        "execution_mode": "autonomous_continue",
    }
    prompt = build_roadmap_prompt(selected_step, extra_context=extra_context)
    roadmap_payload = roadmap_step_to_llm_payload(selected_step)

    enriched_event["metadata"] = {
        **metadata,
        "specialized_handler": "roadmap_step_executor",
        "roadmap_step_id": selected_step.id,
        "roadmap_phase": selected_step.phase,
        "domain_focus": "qa_platform_self_evolution",
        "no_user_confirmation_required": True,
    }
    enriched_event["input"] = {
        **(input_data if isinstance(input_data, dict) else {}),
        "prompt": prompt,
        "roadmap_step": roadmap_payload,
    }

    llm_response = call_llm_gateway(enriched_event)
    result = _build_handler_result(enriched_event, llm_response)
    artifact = result.get("artifact") if isinstance(result, dict) else None
    if isinstance(artifact, dict):
        artifact.setdefault("roadmap_execution", {})
        if isinstance(artifact["roadmap_execution"], dict):
            artifact["roadmap_execution"].update(
                {
                    "selected_step_id": selected_step.id,
                    "selected_step_title": selected_step.title,
                    "selected_step_phase": selected_step.phase,
                    "autonomous_continue": True,
                }
            )

    return _apply_processing_profile(
        result,
        handler="handle_roadmap_step_executor",
        specialized=True,
        roadmap_step_id=selected_step.id,
        roadmap_phase=selected_step.phase,
        autonomous_continue=True,
    )
