from typing import List, Literal, Union
from pydantic import BaseModel, Field, ConfigDict


class GeneratedBy(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    provider: str = "unknown"
    model_name: str = "unknown"
    agent_id: str = "unknown"


class CoverageInfo(BaseModel):
    areas: List[str] = Field(default_factory=list)
    priority: str = "medium"


class BaseArtifact(BaseModel):
    schema_version: str = "1.0"
    artifact_type: str
    summary: str = ""
    generated_by: GeneratedBy = Field(default_factory=GeneratedBy)


class SourceContext(BaseModel):
    story_id: str = ""
    jira_key: str = ""
    story_title: str = ""
    service_name: str = ""
    owner_team: str = ""
    platforms: List[str] = Field(default_factory=list)
    linked_services: List[str] = Field(default_factory=list)


class TestCaseItem(BaseModel):
    id: str
    title: str
    objective: str = ""
    preconditions: List[str] = Field(default_factory=list)
    steps: List[str] = Field(default_factory=list)
    expected_result: str = ""
    priority: Literal["low", "medium", "high"] = "medium"
    type: str = "functional"
    tags: List[str] = Field(default_factory=list)


class QaRequirementAnalysis(BaseArtifact):
    artifact_type: Literal["qa_requirement_analysis"] = "qa_requirement_analysis"
    clarity_findings: List[str] = Field(default_factory=list)
    coverage_gaps: List[str] = Field(default_factory=list)
    assumptions: List[str] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)
    questions_for_refinement: List[str] = Field(default_factory=list)
    suggested_test_areas: List[str] = Field(default_factory=list)
    qa_priority: str = "medium"
    qa_health: str = "yellow"
    readiness_score: int = 50
    requirements_under_test: List[str] = Field(default_factory=list)
    source_context: SourceContext = Field(default_factory=SourceContext)


class QaTestCaseReviewReport(BaseArtifact):
    artifact_type: Literal["qa_test_case_review_report"] = "qa_test_case_review_report"
    structure_issues: List[str] = Field(default_factory=list)
    clarity_issues: List[str] = Field(default_factory=list)
    coverage_issues: List[str] = Field(default_factory=list)
    duplicates: List[str] = Field(default_factory=list)
    missing_negative_cases: List[str] = Field(default_factory=list)
    improvement_actions: List[str] = Field(default_factory=list)
    review_score: str = "needs_review"


class QaTestPlan(BaseArtifact):
    artifact_type: Literal["qa_test_plan"] = "qa_test_plan"
    scope_in: List[str] = Field(default_factory=list)
    scope_out: List[str] = Field(default_factory=list)
    test_levels: List[str] = Field(default_factory=list)
    test_types: List[str] = Field(default_factory=list)
    environments: List[str] = Field(default_factory=list)
    priority_matrix: List[str] = Field(default_factory=list)
    dependencies: List[str] = Field(default_factory=list)
    env_requirements: List[str] = Field(default_factory=list)
    test_data_needs: List[str] = Field(default_factory=list)
    entry_criteria: List[str] = Field(default_factory=list)
    exit_criteria: List[str] = Field(default_factory=list)
    staffing_notes: List[str] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)
    mitigations: List[str] = Field(default_factory=list)
    assumptions: List[str] = Field(default_factory=list)


class PassFailBlocked(BaseModel):
    passed: int = 0
    failed: int = 0
    blocked: int = 0


class QaTestReport(BaseArtifact):
    artifact_type: Literal["qa_test_report"] = "qa_test_report"
    tested_scope: List[str] = Field(default_factory=list)
    not_tested_scope: List[str] = Field(default_factory=list)
    pass_fail_blocked: PassFailBlocked = Field(default_factory=PassFailBlocked)
    key_findings: List[str] = Field(default_factory=list)
    key_defects: List[str] = Field(default_factory=list)
    blockers: List[str] = Field(default_factory=list)
    open_issues: List[str] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)
    quality_assessment: str = ""
    recommendation: str = ""
    signoff_status: str = "pending"


class QaReleaseReadinessReport(BaseArtifact):
    artifact_type: Literal["qa_release_readiness_report"] = "qa_release_readiness_report"
    release_decision: str = ""
    decision_reasoning: List[str] = Field(default_factory=list)
    must_fix_before_release: List[str] = Field(default_factory=list)
    acceptable_known_issues: List[str] = Field(default_factory=list)
    blocking_issues: List[str] = Field(default_factory=list)
    quality_signals: List[str] = Field(default_factory=list)
    follow_up_actions: List[str] = Field(default_factory=list)


class QaTestCaseBundle(BaseArtifact):
    artifact_type: Literal["qa_test_case_bundle"] = "qa_test_case_bundle"
    requirements_under_test: List[str] = Field(default_factory=list)
    assumptions: List[str] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)
    coverage: CoverageInfo = Field(default_factory=CoverageInfo)
    test_cases: List[TestCaseItem] = Field(default_factory=list)


class QaErrorArtifact(BaseArtifact):
    artifact_type: Literal["qa_error"] = "qa_error"
    error_code: str = "unknown_error"
    error_message: str = ""


ArtifactPayload = Union[
    QaRequirementAnalysis,
    QaTestCaseReviewReport,
    QaTestPlan,
    QaTestReport,
    QaReleaseReadinessReport,
    QaTestCaseBundle,
    QaErrorArtifact,
]
