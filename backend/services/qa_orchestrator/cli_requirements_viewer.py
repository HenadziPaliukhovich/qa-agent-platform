#!/usr/bin/env python3
import json
import sys
from pathlib import Path

from backend.shared.artifacts import QaRequirementAnalysis


def _load_json(path: Path) -> dict:
    data = json.loads(path.read_text())
    if isinstance(data, dict):
        return data
    raise SystemExit(f"Unsupported JSON structure in {path}")


def _format_section(title: str, items: list[str]) -> str:
    if not items:
        return ""
    lines = [f"{title}:"]
    for item in items:
        lines.append(f"- {item}")
    return "\n".join(lines)


def _build_jira_comment(artifact: QaRequirementAnalysis) -> str:
    parts: list[str] = []

    if artifact.summary:
        parts.append(f"*QA Requirements Analysis Summary*\n{artifact.summary}")

    if artifact.clarity_findings:
        parts.append(_format_section("Clarity & ambiguity findings", artifact.clarity_findings))

    if artifact.coverage_gaps:
        parts.append(_format_section("Coverage gaps", artifact.coverage_gaps))

    if artifact.risks:
        parts.append(_format_section("Risks", artifact.risks))

    if artifact.questions_for_refinement:
        parts.append(_format_section("Questions for refinement", artifact.questions_for_refinement))

    if artifact.suggested_test_areas:
        parts.append(_format_section("Suggested test areas", artifact.suggested_test_areas))

    if artifact.requirements_under_test:
        parts.append(_format_section("Requirements under test", artifact.requirements_under_test))

    parts.append(f"QA priority: {artifact.qa_priority}")

    return "\n\n".join(part for part in parts if part)


def _print_full(artifact: QaRequirementAnalysis) -> None:
    print("=== QA Requirements Analysis (console view) ===\n")
    print(f"Summary: {artifact.summary}\n")

    if artifact.risks:
        print("Risks:")
        for r in artifact.risks:
            print(f"- {r}")
        print()

    if artifact.clarity_findings:
        print("Clarity findings:")
        for item in artifact.clarity_findings:
            print(f"- {item}")
        print()

    if artifact.coverage_gaps:
        print("Coverage gaps:")
        for item in artifact.coverage_gaps:
            print(f"- {item}")
        print()

    if artifact.questions_for_refinement:
        print("Questions for refinement:")
        for item in artifact.questions_for_refinement:
            print(f"- {item}")
        print()

    if artifact.suggested_test_areas:
        print("Suggested test areas:")
        for item in artifact.suggested_test_areas:
            print(f"- {item}")
        print()

    if artifact.requirements_under_test:
        print("Requirements under test:")
        for item in artifact.requirements_under_test:
            print(f"- {item}")
        print()

    print("=== Jira comment (copy-paste below) ===\n")
    print(_build_jira_comment(artifact))


def _print_short(artifact: QaRequirementAnalysis) -> None:
    print("=== QA Requirements Analysis (short view) ===\n")
    print(f"Summary: {artifact.summary}\n")

    if artifact.risks:
        print("Risks:")
        for r in artifact.risks[:5]:
            print(f"- {r}")
        print()

    if artifact.questions_for_refinement:
        print("Questions for refinement:")
        for item in artifact.questions_for_refinement[:5]:
            print(f"- {item}")
        print()

    print(f"QA priority: {artifact.qa_priority}")


def main() -> None:
    args = sys.argv[1:]

    short_mode = False
    jira_only = False

    if "--short" in args:
        short_mode = True
        args.remove("--short")

    if "--jira-only" in args:
        jira_only = True
        args.remove("--jira-only")

    if len(args) != 1:
        print("Usage: python -m backend.services.qa_orchestrator.cli_requirements_viewer [--short|--jira-only] <result.json>")
        raise SystemExit(1)

    path = Path(args[0])
    if not path.exists():
        raise SystemExit(f"File not found: {path}")

    raw = _load_json(path)
    artifact = QaRequirementAnalysis(**raw)

    if jira_only:
        print(_build_jira_comment(artifact))
        return

    if short_mode:
        _print_short(artifact)
        return

    _print_full(artifact)


if __name__ == "__main__":
    main()
