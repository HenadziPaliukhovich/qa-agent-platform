"""Roadmap Step Executor for QA Agent Platform.

This module defines a simple data model and helper functions for executing
roadmap steps programmatically, so the orchestrator can progress through
an implementation plan without requiring the user to manually say
"продолжай" each time.

This is intentionally minimal and framework-agnostic so it can be
reused later when/if LangGraph or another graph engine is introduced.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional


class RoadmapStepStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class RoadmapStep:
    """Single roadmap step definition.

    This is deliberately generic: it does not know about specific
    services or files, only about intent and context. Concrete code
    that talks to an LLM or applies changes to the repo will use this
    data class as input/output.
    """

    id: str
    title: str
    description: str
    phase: str
    order: int
    status: RoadmapStepStatus = RoadmapStepStatus.PENDING
    notes: Optional[str] = None

    # Optional machine-friendly metadata
    tags: Optional[List[str]] = None
    domain: Optional[str] = None


@dataclass
class RoadmapExecutionState:
    """Tracks progress through a sequence of roadmap steps."""

    steps: List[RoadmapStep]
    current_index: int = 0

    def current_step(self) -> Optional[RoadmapStep]:
        if 0 <= self.current_index < len(self.steps):
            return self.steps[self.current_index]
        return None

    def mark_current_completed(self, notes: Optional[str] = None) -> None:
        step = self.current_step()
        if step is None:
            return
        step.status = RoadmapStepStatus.COMPLETED
        if notes:
            step.notes = (step.notes or "") + ("\n" if step.notes else "") + notes
        self.current_index += 1

    def mark_current_failed(self, notes: Optional[str] = None) -> None:
        step = self.current_step()
        if step is None:
            return
        step.status = RoadmapStepStatus.FAILED
        if notes:
            step.notes = (step.notes or "") + ("\n" if step.notes else "") + notes

    def is_finished(self) -> bool:
        return self.current_index >= len(self.steps)


def build_default_roadmap_steps() -> List[RoadmapStep]:
    """Encode a subset of the 6-month roadmap as executable steps.

    This list is intentionally short and focuses on the most mechanical
    improvements that an automated agent can help with first, such as
    orchestrator refactoring and configuration hardening. The full
    roadmap document remains the source of truth for human-level
    prioritization.
    """

    steps: List[RoadmapStep] = [
        RoadmapStep(
            id="month1-cleanup-env",
            phase="month1",
            order=1,
            title="Repository hygiene and secrets cleanup",
            description=(
                "Ensure .env is not committed, provide .env.example, and document "
                "how to configure local/dev/prod environments."
            ),
            tags=["security", "hygiene"],
        ),
        RoadmapStep(
            id="month1-config-typed",
            phase="month1",
            order=2,
            title="Introduce typed configuration for services",
            description=(
                "Replace direct os.getenv calls in orchestrator with a typed settings "
                "object so configuration is validated once and reused."
            ),
            tags=["config", "pydantic-settings"],
        ),
        RoadmapStep(
            id="month2-orchestrator-refactor",
            phase="month2",
            order=3,
            title="Refactor orchestrator into explicit workflow components",
            description=(
                "Split process_task_event lifecycle into dedicated components for "
                "dispatch, status publishing, and result persistence, preparing "
                "the codebase for graph/state-based orchestration."
            ),
            tags=["orchestrator", "refactor"],
        ),
        RoadmapStep(
            id="month3-llm-provider-layer",
            phase="month3",
            order=4,
            title="Introduce unified LLM provider layer",
            description=(
                "Replace manual LLM provider branching with a single adapter layer, so "
                "adding or switching models does not require changes in orchestrator "
                "or handlers."
            ),
            tags=["llm", "provider"],
        ),
    ]
    # Keep steps ordered by phase and order
    steps.sort(key=lambda s: (s.phase, s.order))
    return steps


def roadmap_step_to_llm_payload(step: RoadmapStep) -> Dict[str, Any]:
    """Convert a roadmap step into a generic payload for an LLM agent.

    Orchestrator can use this payload to ask an LLM to
    - analyze the current codebase state;
    - propose specific changes for this step;
    - optionally generate patches or detailed instructions.
    """

    return {
        "step_id": step.id,
        "title": step.title,
        "description": step.description,
        "phase": step.phase,
        "tags": step.tags or [],
        "status": step.status.value,
    }


def build_roadmap_prompt(step: RoadmapStep, extra_context: Optional[Dict[str, Any]] = None) -> str:
    """Build a natural-language prompt for an LLM to execute the given step.

    The key requirement: do not ask the user anything, just propose and
    apply the next improvement according to the roadmap.
    """

    ctx_lines: List[str] = []
    if extra_context:
        for key, value in extra_context.items():
            ctx_lines.append(f"- {key}: {value}")

    context_block = "\n".join(ctx_lines) if ctx_lines else "(no extra context provided)"

    return (
        "You are an AI architect working on the QA Agent Platform. "
        "Execute the next roadmap step without asking the user questions.\n\n" \
        f"Step ID: {step.id}\n" \
        f"Phase: {step.phase}\n" \
        f"Title: {step.title}\n" \
        f"Description: {step.description}\n" \
        "\nContext for this repository (partial):\n" \
        f"{context_block}\n\n" \
        "Your tasks:\n" \
        "1. Analyze the current codebase state relevant to this step.\n" \
        "2. Propose concrete changes (files, functions, signatures).\n" \
        "3. If the environment allows, apply the changes directly; otherwise, "
        "output a precise patch plan.\n" \
        "4. Do NOT ask the user for confirmation or additional input.\n"
    )
