from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from devdefender_lab.evidence import dedupe_strings, is_safe_evidence_pointer


BriefingDiagramKind = Literal["architecture", "sequence", "data-flow", "timeline", "requirements", "risk"]
BriefingStatus = Literal["done", "in_progress", "blocked", "planned"]
RequirementStatus = Literal["met", "partial", "unmet", "unknown"]
ExperimentStatus = Literal["passed", "failed", "not_run", "inconclusive"]
RiskSeverity = Literal["low", "medium", "high"]
TaskPriority = Literal["low", "medium", "high"]


class BriefingBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def reject_forbidden_artifacts(self):
        if contains_forbidden_briefing_artifact_fields(self.model_dump(mode="json")):
            raise ValueError("Briefing payload contains forbidden secret, raw audio, or transcript artifact fields.")
        return self


class BriefingEvidencePointer(BriefingBaseModel):
    pointer: str = Field(min_length=1, max_length=256)
    label: str = Field(min_length=1, max_length=120)

    @field_validator("pointer")
    @classmethod
    def validate_pointer(cls, value: str) -> str:
        pointer = value.strip()
        if not is_safe_evidence_pointer(pointer):
            raise ValueError(f"Unsafe evidence pointer: {value}")
        return pointer


class BriefingDiagramRequest(BriefingBaseModel):
    diagram_id: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9][a-z0-9-]{0,79}$")
    title: str = Field(min_length=1, max_length=120)
    kind: BriefingDiagramKind
    audience_goal: str = Field(min_length=1, max_length=300)
    mermaid_hint: str | None = Field(default=None, max_length=2000)
    evidence_pointers: list[str] = Field(default_factory=list, max_length=12)

    @field_validator("evidence_pointers")
    @classmethod
    def validate_evidence_pointers(cls, values: list[str]) -> list[str]:
        return validate_evidence_pointer_strings(values)


class BriefingProgressItem(BriefingBaseModel):
    label: str = Field(min_length=1, max_length=120)
    status: BriefingStatus
    plain_language_summary: str = Field(min_length=1, max_length=500)
    evidence_pointers: list[str] = Field(default_factory=list, max_length=12)

    @field_validator("evidence_pointers")
    @classmethod
    def validate_evidence_pointers(cls, values: list[str]) -> list[str]:
        return validate_evidence_pointer_strings(values)


class BriefingRequirementCoverage(BriefingBaseModel):
    requirement: str = Field(min_length=1, max_length=160)
    status: RequirementStatus
    explanation: str = Field(min_length=1, max_length=500)
    evidence_pointers: list[str] = Field(default_factory=list, max_length=12)

    @field_validator("evidence_pointers")
    @classmethod
    def validate_evidence_pointers(cls, values: list[str]) -> list[str]:
        return validate_evidence_pointer_strings(values)


class BriefingExperimentResult(BriefingBaseModel):
    name: str = Field(min_length=1, max_length=160)
    status: ExperimentStatus
    summary: str = Field(min_length=1, max_length=500)
    command: str | None = Field(default=None, max_length=500)
    evidence_pointers: list[str] = Field(default_factory=list, max_length=12)

    @field_validator("evidence_pointers")
    @classmethod
    def validate_evidence_pointers(cls, values: list[str]) -> list[str]:
        return validate_evidence_pointer_strings(values)


class BriefingRisk(BriefingBaseModel):
    risk: str = Field(min_length=1, max_length=240)
    severity: RiskSeverity
    mitigation: str = Field(min_length=1, max_length=500)
    decision_needed: bool = False


class BriefingQuestion(BriefingBaseModel):
    question: str = Field(min_length=1, max_length=240)
    why_it_matters: str = Field(min_length=1, max_length=500)
    options: list[str] = Field(default_factory=list, max_length=5)

    @field_validator("options")
    @classmethod
    def validate_options(cls, values: list[str]) -> list[str]:
        return _dedupe_limited_strings(values, max_item_length=120)


class BriefingFollowUpTask(BriefingBaseModel):
    task: str = Field(min_length=1, max_length=240)
    owner_hint: str = Field(min_length=1, max_length=80)
    priority: TaskPriority
    evidence_pointers: list[str] = Field(default_factory=list, max_length=12)

    @field_validator("evidence_pointers")
    @classmethod
    def validate_evidence_pointers(cls, values: list[str]) -> list[str]:
        return validate_evidence_pointer_strings(values)


class BriefingContext(BriefingBaseModel):
    project_name: str = Field(default="DevDefender Lab", min_length=1, max_length=120)
    task_goal: str = Field(min_length=1, max_length=400)
    current_task: str | None = Field(default=None, max_length=400)
    repo_path: str | None = Field(default=None, max_length=512)
    changed_files: list[str] = Field(default_factory=list, max_length=100)
    completed_work: list[str] = Field(default_factory=list, max_length=50)
    in_progress_work: list[str] = Field(default_factory=list, max_length=50)
    blockers: list[str] = Field(default_factory=list, max_length=50)
    next_steps: list[str] = Field(default_factory=list, max_length=50)
    requirements: list[str] = Field(default_factory=list, max_length=50)
    tests: list[str] = Field(default_factory=list, max_length=100)
    artifacts: list[str] = Field(default_factory=list, max_length=100)
    docs: list[str] = Field(default_factory=list, max_length=100)
    architecture_facts: list[str] = Field(default_factory=list, max_length=50)
    experiment_facts: list[str] = Field(default_factory=list, max_length=50)
    risks: list[str] = Field(default_factory=list, max_length=50)
    open_questions: list[str] = Field(default_factory=list, max_length=50)
    constraints: list[str] = Field(default_factory=list, max_length=50)
    evidence_pointers: list[str] = Field(default_factory=list, max_length=50)

    @field_validator(
        "changed_files",
        "completed_work",
        "in_progress_work",
        "blockers",
        "next_steps",
        "requirements",
        "tests",
        "artifacts",
        "docs",
        "architecture_facts",
        "experiment_facts",
        "risks",
        "open_questions",
        "constraints",
    )
    @classmethod
    def validate_string_list(cls, values: list[str]) -> list[str]:
        return _dedupe_limited_strings(values, max_item_length=400)

    @field_validator("evidence_pointers")
    @classmethod
    def validate_evidence_pointers(cls, values: list[str]) -> list[str]:
        return validate_evidence_pointer_strings(values)


class ProjectBriefingReport(BriefingBaseModel):
    project_name: str = Field(min_length=1, max_length=120)
    task_goal: str = Field(min_length=1, max_length=400)
    generated_by: str = Field(default="mock-briefing-adapter", min_length=1, max_length=80)
    audience_summary: str = Field(min_length=1, max_length=1200)
    architecture_diagrams: list[BriefingDiagramRequest] = Field(default_factory=list, max_length=8)
    progress_status: list[BriefingProgressItem] = Field(default_factory=list, max_length=20)
    requirements_coverage: list[BriefingRequirementCoverage] = Field(default_factory=list, max_length=20)
    experiment_results: list[BriefingExperimentResult] = Field(default_factory=list, max_length=20)
    risks_and_unknowns: list[BriefingRisk] = Field(default_factory=list, max_length=20)
    stakeholder_questions: list[BriefingQuestion] = Field(default_factory=list, max_length=20)
    follow_up_tasks: list[BriefingFollowUpTask] = Field(default_factory=list, max_length=20)
    evidence_pointers: list[BriefingEvidencePointer] = Field(default_factory=list, max_length=50)


class BriefingAdapter(Protocol):
    def build_report(self, context: BriefingContext) -> ProjectBriefingReport:
        """Return a provider-neutral project briefing report."""


class MockBriefingAdapter:
    backend = "mock-briefing-adapter"

    def build_report(self, context: BriefingContext | None = None) -> ProjectBriefingReport:
        context = context or default_briefing_context()
        pointers = context.evidence_pointers or [
            "timeline://briefing#event=0&kind=briefing_generated",
            "slide://briefing#page=1",
        ]
        primary_pointer = pointers[0]
        slide_pointer = next((pointer for pointer in pointers if pointer.startswith("slide://")), pointers[-1])

        return ProjectBriefingReport(
            project_name=context.project_name,
            task_goal=context.task_goal,
            generated_by=self.backend,
            audience_summary=(
                f"{context.project_name} is being packaged into a lightweight project briefing room. "
                "The important product change is that the code agent explains project status in stakeholder "
                "language while the local runtime handles deck generation, feedback interpretation, plan updates, "
                "and the execution gate."
            ),
            architecture_diagrams=[
                BriefingDiagramRequest(
                    diagram_id="skill-runtime-boundary",
                    title="Skill and Runtime Boundary",
                    kind="architecture",
                    audience_goal=(
                        "Show that the user-facing skill orchestrates the workflow, while the repo runtime owns "
                        "repeatable deck, feedback-plan, plan-update, and execution-gate operations."
                    ),
                    mermaid_hint=(
                        "flowchart LR\n"
                        "  User[Stakeholder] --> Skill[project-briefing-room skill]\n"
                        "  Skill --> Adapter[Code-agent briefing adapter]\n"
                        "  Skill --> Runtime[DevDefender Lab runtime]\n"
                        "  Runtime --> Deck[Markdown and Mermaid briefing]\n"
                        "  Runtime --> Feedback[Feedback plan]\n"
                        "  Feedback --> Gate[Execution gate]"
                    ),
                    evidence_pointers=[primary_pointer, slide_pointer],
                )
            ],
            progress_status=[
                BriefingProgressItem(
                    label="Codex-native briefing loop",
                    status="done",
                    plain_language_summary=(
                        "The retained default path can generate a stakeholder deck, interpret feedback, update "
                        "the plan, and decide whether Codex can continue."
                    ),
                    evidence_pointers=[primary_pointer],
                ),
                BriefingProgressItem(
                    label="Product skill shell",
                    status="done",
                    plain_language_summary=(
                        "The repo now has a thin skill entry point that explains how a code agent should run the "
                        "briefing workflow and which optional helper skills can be used."
                    ),
                    evidence_pointers=[slide_pointer],
                ),
                BriefingProgressItem(
                    label="Structured briefing contract",
                    status="in_progress",
                    plain_language_summary=(
                        "The next layer is the provider-neutral report format that lets Codex, Aider, or a generic "
                        "agent feed the same local briefing runtime."
                    ),
                    evidence_pointers=[primary_pointer],
                ),
            ],
            requirements_coverage=[
                BriefingRequirementCoverage(
                    requirement="Minimal manual setup",
                    status="met",
                    explanation=(
                        "The default path avoids external meeting scheduling, credentials, browser automation, and Node."
                    ),
                    evidence_pointers=[primary_pointer],
                ),
                BriefingRequirementCoverage(
                    requirement="Code-agent portability",
                    status="partial",
                    explanation=(
                        "The schema is provider-neutral, but real adapters beyond the mock adapter still need to "
                        "be implemented."
                    ),
                    evidence_pointers=[slide_pointer],
                ),
                BriefingRequirementCoverage(
                    requirement="Non-technical project explanation",
                    status="met",
                    explanation=(
                        "The report separates stakeholder summary, architecture diagrams, progress, requirements, "
                        "experiments, risks, questions, and follow-up tasks."
                    ),
                    evidence_pointers=[slide_pointer],
                ),
            ],
            experiment_results=[
                BriefingExperimentResult(
                    name="Codex-native feedback-to-plan route",
                    status="passed",
                    summary="Stakeholder feedback is converted into a structured feedback plan and applied back to plan.md.",
                    command="scripts/project_briefing_room_smoke.py --agent-backend workspace --repo .",
                    evidence_pointers=[primary_pointer],
                ),
                BriefingExperimentResult(
                    name="Execution gate route",
                    status="passed",
                    summary="The gate blocks continuation when clarification is pending and allows it when the plan is actionable.",
                    command="scripts/briefing_execution_gate.py --plan-update artifacts/briefing_plan_update.json",
                    evidence_pointers=[primary_pointer],
                ),
            ],
            risks_and_unknowns=[
                BriefingRisk(
                    risk="Real code-agent adapters may vary in output quality.",
                    severity="medium",
                    mitigation="Keep the briefing schema strict and validate adapter output before starting a room.",
                    decision_needed=False,
                ),
                BriefingRisk(
                    risk="A live meeting experience is no longer bundled in the minimal core.",
                    severity="low",
                    mitigation="Keep the current Codex-native product path small; add room providers later only if the product needs them.",
                    decision_needed=False,
                ),
            ],
            stakeholder_questions=[
                BriefingQuestion(
                    question="Which code-agent adapter should be implemented first after the mock adapter?",
                    why_it_matters="The first real adapter defines the integration contract for other agents.",
                    options=["Codex-native report", "Aider", "Generic JSON input"],
                )
            ],
            follow_up_tasks=[
                BriefingFollowUpTask(
                    task="Generate a Markdown/Mermaid briefing deck from ProjectBriefingReport.",
                    owner_hint="runtime",
                    priority="high",
                    evidence_pointers=[slide_pointer],
                ),
                BriefingFollowUpTask(
                    task="Add the Phase 4D one-command project briefing room smoke.",
                    owner_hint="runtime",
                    priority="high",
                    evidence_pointers=[primary_pointer],
                ),
            ],
            evidence_pointers=[
                BriefingEvidencePointer(pointer=primary_pointer, label="Primary briefing timeline pointer"),
                BriefingEvidencePointer(pointer=slide_pointer, label="Primary slide/deck pointer"),
            ],
        )


def default_briefing_context() -> BriefingContext:
    return BriefingContext(
        project_name="DevDefender Lab",
        task_goal="Package a lightweight project briefing product for code agents.",
        changed_files=[
            "skills/project-briefing-room/SKILL.md",
            "skills/project-briefing-room/templates/agent_briefing_input.json",
        ],
        tests=["skill-creator quick_validate.py skills/project-briefing-room"],
        docs=["plan.md", "PHASE3_DESIGN.md", "PHASE3_HANDOFF.md", "DESIGN.md", "README.md"],
        architecture_facts=[
            "The product skill remains thin and delegates deterministic deck, feedback-plan, plan-update, and gate work to the repo runtime.",
            "The default implementation is Codex-native and does not require a live meeting provider.",
        ],
        experiment_facts=[
            "Project smoke accepts briefing artifacts, feedback plan, plan update, and execution gate.",
            "Project doctor accepts a quick workspace closure without external credentials.",
        ],
        risks=[
            "Real code-agent adapters are not implemented yet.",
            "External SaaS meeting providers are intentionally deferred.",
        ],
        constraints=[
            "No raw audio, full transcript, provider token, cookie, local storage, or unredacted meeting URL in artifacts.",
            "Core product path should stay usable without optional helper skills.",
        ],
        evidence_pointers=[
            "timeline://briefing#event=0&kind=briefing_generated",
            "slide://briefing#page=1",
        ],
    )


def validate_evidence_pointer_strings(values: list[str]) -> list[str]:
    pointers = dedupe_strings(value.strip() for value in values if isinstance(value, str))
    unsafe = [pointer for pointer in pointers if not is_safe_evidence_pointer(pointer)]
    if unsafe:
        raise ValueError(f"Unsafe evidence pointers: {', '.join(unsafe)}")
    return pointers


def contains_forbidden_briefing_artifact_fields(payload: object) -> bool:
    forbidden_keys = {
        "access_token",
        "api_key",
        "api_secret",
        "audio",
        "audio_path",
        "audio_url",
        "cookie",
        "cookies",
        "full_transcript",
        "host_start_url",
        "local_storage",
        "oauth_token",
        "password",
        "raw_audio",
        "start_token",
        "start_url",
        "token",
        "transcript",
        "zak",
    }
    forbidden_fragments = (
        "data:audio",
        ".wav",
        ".mp3",
        "api_secret=",
        "api_key=",
        "bearer ",
        "document.cookie",
        "localstorage",
        "local_storage",
        "mock-host-token",
        "mock-join-token",
        "mock-password",
        "password=",
        "set-cookie",
        "start_token=",
    )
    if isinstance(payload, BaseModel):
        return contains_forbidden_briefing_artifact_fields(payload.model_dump(mode="json"))
    if isinstance(payload, dict):
        for key, value in payload.items():
            if isinstance(key, str) and key.lower() in forbidden_keys and not _is_empty_artifact_value(value):
                return True
            if contains_forbidden_briefing_artifact_fields(value):
                return True
        return False
    if isinstance(payload, list):
        return any(contains_forbidden_briefing_artifact_fields(value) for value in payload)
    if isinstance(payload, str):
        lowered = payload.lower()
        return any(fragment in lowered for fragment in forbidden_fragments)
    return False


def _dedupe_limited_strings(values: list[str], *, max_item_length: int) -> list[str]:
    normalized = dedupe_strings(value.strip() for value in values if isinstance(value, str) and value.strip())
    too_long = [value for value in normalized if len(value) > max_item_length]
    if too_long:
        raise ValueError(f"String value exceeds {max_item_length} characters.")
    return normalized


def _is_empty_artifact_value(value: object) -> bool:
    return value is None or value == "" or value == []
