# Known Issues and Fix Log

## Purpose

This file tracks recurring bugs, root causes, fixes, and verification notes so the same mistake is less likely to happen again.

## Issue Log

### 2026-06-09 — requirements_analysis enrichment fields lost

- Status: fixed and runtime-verified.
- Area: `backend/services/qa_orchestrator`
- Symptom: `qa_requirement_analysis` returned only `requirements_under_test`, while `summary`, `clarity_findings`, `coverage_gaps`, `assumptions`, `questions_for_refinement`, `suggested_test_areas`, and `risks` stayed empty even after enrichment logic was added.
- Root cause 1: enrichment was applied after `build_structured_result`, but the final artifact was still rebuilt from raw `llm_output`.
- Root cause 2: `build_requirements_analysis_artifact()` always recalculated `requirements_under_test` from the event input instead of respecting enriched `llm_output` values.
- Root cause 3: a circular import between `clients.py` and `builders.py` blocked orchestrator startup during the fix rollout.
- Root cause 4: `QaRequirementAnalysis.risks` expected `List[str]`, but the builder used structured risk normalization and produced dict items.
- Root cause 5: `summary` could still be empty on the final return path, so a deterministic backfill was required in `handle_requirements_analysis()`.
- Fixes applied:
  - In `handlers.py`, enriched fields are copied back into `llm_output` and the artifact is rebuilt.
  - In `builders.py`, `build_requirements_analysis_artifact()` now uses `llm_output["requirements_under_test"]` when present, with fallback to `extract_requirements_under_test(event)`.
  - `get_effective_input_data()` was moved to `backend/services/qa_orchestrator/utils.py` to remove the circular import between `clients.py` and `builders.py`.
  - In `builders.py`, requirements analysis `risks` now use string normalization compatible with `QaRequirementAnalysis`.
  - In `handlers.py`, a final deterministic summary backfill is applied before returning the requirements analysis artifact.
  - `scripts/smoke_requirements_analysis.py` was updated into a regression script that verifies enriched sections, summary presence, and domain-specific scenarios.
- Runtime verification completed:
  - `qa_orchestrator` restarted successfully after the import fix.
  - Regression script `scripts/smoke_requirements_analysis.py` passed for five scenarios: status-code mapping, underspecified requirement, cross-service flow, deposit limits plus bonus, and ambiguous withdrawal flow.
  - Verified outputs now contain non-empty `summary`, `clarity_findings`, `coverage_gaps`, `assumptions`, `questions_for_refinement`, `suggested_test_areas`, and `risks`.

### Usage rule

When a bug is found and investigated, add or update an entry here with:

- symptom,
- actual root cause,
- concrete code fix,
- how to verify.
