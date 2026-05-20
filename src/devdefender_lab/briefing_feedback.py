from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator

from devdefender_lab.briefing import (
    BriefingBaseModel,
    ProjectBriefingReport,
    TaskPriority,
    contains_forbidden_briefing_artifact_fields,
    validate_evidence_pointer_strings,
)
from devdefender_lab.evidence import dedupe_strings


FeedbackInputSource = Literal["cli_text", "file", "room_typed_feedback", "stt_text", "default_sample"]
FeedbackConcernCategory = Literal["direction", "priority", "workflow", "requirement", "risk", "scope", "other"]
ClarificationStatus = Literal["pending", "answered"]
ClarificationDecisionKind = Literal[
    "pause_policy",
    "blocking_rule",
    "plan_destination",
    "direction_priority",
    "requirement_gap",
    "status_explanation",
    "risk_blocker",
    "write_target",
    "general",
]
PlanChangeType = Literal["add", "modify", "remove", "reprioritize"]

MAX_FEEDBACK_TEXT_LENGTH = 4000
DEFAULT_FEEDBACK_PLAN_OUT = Path("artifacts/briefing_feedback_plan.json")
DEFAULT_STAKEHOLDER_FEEDBACK = (
    "The current briefing loop is too one-way. The AI should listen to stakeholder feedback, "
    "ask clarifying questions, and update the execution plan before continuing."
)
FORBIDDEN_FEEDBACK_CAPTURE_ARTIFACT_FRAGMENTS = (
    "audio_path=",
    "audio_url=",
    "full transcript:",
    "full transcript=",
    "full_transcript",
    "meeting transcript:",
    "meeting transcript=",
    "meeting_transcript",
    "raw transcript:",
    "raw transcript=",
    "raw_audio",
    "transcript_path=",
    "transcript_url=",
    "webvtt",
)


class StakeholderFeedbackInput(BriefingBaseModel):
    source: FeedbackInputSource
    text: str = Field(min_length=1, max_length=MAX_FEEDBACK_TEXT_LENGTH)
    path: str | None = Field(default=None, max_length=512)

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        text = _normalize_text(value)
        if not text:
            raise ValueError("Stakeholder feedback is required.")
        if contains_forbidden_briefing_artifact_fields(text):
            raise ValueError("Stakeholder feedback contains forbidden secret, raw audio, or transcript artifact fields.")
        if _contains_forbidden_feedback_capture_artifact(value):
            raise ValueError("Stakeholder feedback must not include raw audio artifacts or full meeting transcripts.")
        return text


class FeedbackConcern(BriefingBaseModel):
    concern: str = Field(min_length=1, max_length=240)
    category: FeedbackConcernCategory
    priority: TaskPriority
    evidence_pointers: list[str] = Field(default_factory=list, max_length=12)

    @field_validator("evidence_pointers")
    @classmethod
    def validate_evidence_pointers(cls, values: list[str]) -> list[str]:
        return validate_evidence_pointer_strings(values)


class FeedbackClarificationQuestion(BriefingBaseModel):
    question: str = Field(min_length=1, max_length=240)
    why_it_matters: str = Field(min_length=1, max_length=400)
    options: list[str] = Field(default_factory=list, max_length=5)
    answer_summary: str | None = Field(default=None, max_length=240)
    status: ClarificationStatus = "pending"

    @field_validator("options")
    @classmethod
    def validate_options(cls, values: list[str]) -> list[str]:
        return _dedupe_limited_strings(values, max_item_length=120)


class ExecutionPlanChange(BriefingBaseModel):
    change_type: PlanChangeType
    title: str = Field(min_length=1, max_length=160)
    rationale: str = Field(min_length=1, max_length=400)
    priority: TaskPriority


class UpdatedExecutionPlan(BriefingBaseModel):
    summary: str = Field(min_length=1, max_length=600)
    next_steps: list[str] = Field(default_factory=list, min_length=1, max_length=12)
    acceptance_criteria: list[str] = Field(default_factory=list, min_length=1, max_length=12)
    out_of_scope: list[str] = Field(default_factory=list, max_length=12)

    @field_validator("next_steps", "acceptance_criteria", "out_of_scope")
    @classmethod
    def validate_string_list(cls, values: list[str]) -> list[str]:
        return _dedupe_limited_strings(values, max_item_length=240)


class BriefingFeedbackPlan(BriefingBaseModel):
    schema_version: str = Field(default="1", pattern=r"^1$")
    project_name: str = Field(default="DevDefender Lab", min_length=1, max_length=120)
    source: str = Field(default="stakeholder_feedback", min_length=1, max_length=80)
    feedback_summary: str = Field(min_length=1, max_length=600)
    interpreted_concerns: list[FeedbackConcern] = Field(default_factory=list, min_length=1, max_length=12)
    clarification_questions: list[FeedbackClarificationQuestion] = Field(default_factory=list, min_length=1, max_length=8)
    decisions: list[str] = Field(default_factory=list, max_length=12)
    plan_changes: list[ExecutionPlanChange] = Field(default_factory=list, min_length=1, max_length=12)
    updated_execution_plan: UpdatedExecutionPlan
    needs_follow_up: bool = True
    evidence_pointers: list[str] = Field(default_factory=list, max_length=24)

    @field_validator("decisions")
    @classmethod
    def validate_decisions(cls, values: list[str]) -> list[str]:
        return _dedupe_limited_strings(values, max_item_length=240)

    @field_validator("evidence_pointers")
    @classmethod
    def validate_evidence_pointers(cls, values: list[str]) -> list[str]:
        return validate_evidence_pointer_strings(values)


class ClarificationMergeResult(BriefingBaseModel):
    kind: ClarificationDecisionKind
    decisions: list[str] = Field(default_factory=list, max_length=4)
    plan_changes: list[ExecutionPlanChange] = Field(default_factory=list, max_length=4)
    next_steps: list[str] = Field(default_factory=list, max_length=4)

    @field_validator("decisions", "next_steps")
    @classmethod
    def validate_string_list(cls, values: list[str]) -> list[str]:
        return _dedupe_limited_strings(values, max_item_length=240)


def select_feedback_input(
    *,
    feedback: str | None = None,
    feedback_file: Path | str | None = None,
    stt_text: str | None = None,
    use_default_feedback: bool = False,
    source: FeedbackInputSource | None = None,
) -> StakeholderFeedbackInput:
    if feedback_file is not None:
        input_path = Path(feedback_file)
        text = input_path.read_text(encoding="utf-8", errors="ignore")
        return StakeholderFeedbackInput(source=source or "file", text=text, path=str(input_path))
    if stt_text is not None and stt_text.strip():
        return StakeholderFeedbackInput(source=source or "stt_text", text=stt_text)
    if feedback is not None and feedback.strip():
        return StakeholderFeedbackInput(source=source or "cli_text", text=feedback)
    if use_default_feedback:
        return StakeholderFeedbackInput(source=source or "default_sample", text=DEFAULT_STAKEHOLDER_FEEDBACK)
    raise ValueError("Provide feedback text, a feedback file, STT feedback text, or use_default_feedback=True.")


def build_feedback_plan_from_input(
    feedback_input: StakeholderFeedbackInput,
    *,
    clarification_answers: list[str] | None = None,
    briefing_report: ProjectBriefingReport | dict[str, object] | None = None,
    evidence_pointers: list[str] | None = None,
) -> BriefingFeedbackPlan:
    return build_feedback_plan(
        feedback_input.text,
        clarification_answers=clarification_answers,
        briefing_report=briefing_report,
        evidence_pointers=evidence_pointers,
        source=feedback_input.source,
    )


def build_feedback_plan(
    feedback: str,
    *,
    clarification_answers: list[str] | None = None,
    briefing_report: ProjectBriefingReport | dict[str, object] | None = None,
    evidence_pointers: list[str] | None = None,
    source: str = "stakeholder_feedback",
) -> BriefingFeedbackPlan:
    feedback_text = _normalize_text(feedback)
    if not feedback_text:
        raise ValueError("Stakeholder feedback is required.")
    if contains_forbidden_briefing_artifact_fields(feedback_text):
        raise ValueError("Stakeholder feedback contains forbidden secret, raw audio, or transcript artifact fields.")
    if _contains_forbidden_feedback_capture_artifact(feedback):
        raise ValueError("Stakeholder feedback must not include raw audio artifacts or full meeting transcripts.")

    project_name = _project_name_from_report(briefing_report)
    pointers = _evidence_pointers_from_report(briefing_report, evidence_pointers)
    summary = _summarize_feedback(feedback_text)
    concerns = _infer_concerns(feedback_text, evidence_pointers=pointers[:3])
    questions = _build_clarification_questions(feedback_text, clarification_answers or [])
    decisions = _build_decisions(clarification_answers or [])
    plan_changes = _build_plan_changes(feedback_text)
    updated_plan = _build_updated_execution_plan(
        feedback_summary=summary,
        answered_all=all(question.status == "answered" for question in questions),
        clarification_answers=clarification_answers or [],
    )
    return BriefingFeedbackPlan(
        project_name=project_name,
        source=source,
        feedback_summary=summary,
        interpreted_concerns=concerns,
        clarification_questions=questions,
        decisions=decisions,
        plan_changes=plan_changes,
        updated_execution_plan=updated_plan,
        needs_follow_up=any(question.status == "pending" for question in questions),
        evidence_pointers=pointers,
    )


def load_briefing_report(path: Path | str | None) -> ProjectBriefingReport | None:
    if path is None:
        return None
    input_path = Path(path)
    try:
        text = input_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    if contains_forbidden_briefing_artifact_fields(text):
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or contains_forbidden_briefing_artifact_fields(payload):
        return None
    try:
        return ProjectBriefingReport.model_validate(payload)
    except Exception:
        return None


def load_feedback_text(path: Path | str) -> str:
    input_path = Path(path)
    return StakeholderFeedbackInput(
        source="file",
        text=input_path.read_text(encoding="utf-8", errors="ignore"),
        path=str(input_path),
    ).text


def write_feedback_plan(plan: BriefingFeedbackPlan, path: Path | str) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(plan.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return output_path


def answer_feedback_clarification(
    plan: BriefingFeedbackPlan,
    *,
    question_index: int,
    answer: str,
) -> BriefingFeedbackPlan:
    if question_index < 1 or question_index > len(plan.clarification_questions):
        raise ValueError(f"question_index must be between 1 and {len(plan.clarification_questions)}.")
    answer_text = _normalize_text(answer)
    if not answer_text:
        raise ValueError("Clarification answer is required.")
    if contains_forbidden_briefing_artifact_fields(answer_text):
        raise ValueError("Clarification answer contains forbidden secret, raw audio, or transcript artifact fields.")
    questions = list(plan.clarification_questions)
    original_question = questions[question_index - 1]
    questions[question_index - 1] = original_question.model_copy(
        update={
            "answer_summary": _clip(answer_text, 240),
            "status": "answered",
        }
    )
    structured_decision = _decision_from_clarification(original_question, answer_text)
    decisions = dedupe_strings([*plan.decisions, *structured_decision.decisions])[:12]
    plan_changes = _merge_plan_changes(plan.plan_changes, structured_decision.plan_changes)
    needs_follow_up = any(question.status == "pending" for question in questions)
    updated_plan = plan.updated_execution_plan
    if structured_decision.next_steps:
        updated_plan = updated_plan.model_copy(
            update={"next_steps": dedupe_strings([*updated_plan.next_steps, *structured_decision.next_steps])[:12]}
        )
    if not needs_follow_up:
        next_steps = [
            step
            for step in updated_plan.next_steps
            if step != "Pause for stakeholder clarification before treating the updated plan as final."
        ]
        next_steps.append("Use the answered feedback plan as the next execution source of truth.")
        updated_plan = updated_plan.model_copy(update={"next_steps": dedupe_strings(next_steps)[:12]})
    return plan.model_copy(
        update={
            "clarification_questions": questions,
            "decisions": decisions,
            "plan_changes": plan_changes,
            "needs_follow_up": needs_follow_up,
            "updated_execution_plan": updated_plan,
        }
    )


def load_feedback_plan(path: Path | str) -> BriefingFeedbackPlan | None:
    input_path = Path(path)
    try:
        text = input_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    if contains_forbidden_briefing_artifact_fields(text):
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or contains_forbidden_briefing_artifact_fields(payload):
        return None
    try:
        return BriefingFeedbackPlan.model_validate(payload)
    except Exception:
        return None


def _project_name_from_report(report: ProjectBriefingReport | dict[str, object] | None) -> str:
    if isinstance(report, ProjectBriefingReport):
        return report.project_name
    if isinstance(report, dict) and isinstance(report.get("project_name"), str) and report["project_name"].strip():
        return str(report["project_name"]).strip()[:120]
    return "DevDefender Lab"


def _evidence_pointers_from_report(
    report: ProjectBriefingReport | dict[str, object] | None,
    extra_pointers: list[str] | None,
) -> list[str]:
    pointers: list[str] = []
    if isinstance(report, ProjectBriefingReport):
        pointers.extend(pointer.pointer for pointer in report.evidence_pointers)
    elif isinstance(report, dict) and isinstance(report.get("evidence_pointers"), list):
        for item in report["evidence_pointers"]:
            if isinstance(item, dict) and isinstance(item.get("pointer"), str):
                pointers.append(item["pointer"])
            elif isinstance(item, str):
                pointers.append(item)
    if extra_pointers:
        pointers.extend(extra_pointers)
    return validate_evidence_pointer_strings(dedupe_strings(pointers))[:24]


def _infer_concerns(feedback: str, *, evidence_pointers: list[str]) -> list[FeedbackConcern]:
    lowered = feedback.lower()
    concerns: list[FeedbackConcern] = []
    if _contains_any(feedback, lowered, ["不满意", "不满足", "不对", "not satisfied", "too one-way"]):
        concerns.append(
            FeedbackConcern(
                concern=(
                    "The briefing must stop being a one-way status report and treat stakeholder objections as "
                    "inputs that can change the next execution step."
                ),
                category="workflow",
                priority="high",
                evidence_pointers=evidence_pointers,
            )
        )
    if _contains_any(feedback, lowered, ["反馈", "听取", "listen", "feedback"]):
        concerns.append(
            FeedbackConcern(
                concern=(
                    "The meeting needs an explicit listening phase where the stakeholder can confirm, redirect, "
                    "or challenge the AI's interpretation."
                ),
                category="requirement",
                priority="high",
                evidence_pointers=evidence_pointers,
            )
        )
    if _contains_any(feedback, lowered, ["澄清", "确认", "clarify", "clarifying"]):
        concerns.append(
            FeedbackConcern(
                concern=(
                    "Ambiguous feedback should trigger concise follow-up questions before the AI commits to a "
                    "revised implementation plan."
                ),
                category="workflow",
                priority="high",
                evidence_pointers=evidence_pointers,
            )
        )
    if _contains_any(feedback, lowered, ["执行方案", "计划", "plan", "next execution"]):
        concerns.append(
            FeedbackConcern(
                concern=(
                    "The practical output of the briefing should be an updated execution plan, not just a meeting "
                    "summary or evidence packet."
                ),
                category="direction",
                priority="high",
                evidence_pointers=evidence_pointers,
            )
        )
    if _contains_any(feedback, lowered, ["架构", "进度", "需求", "实验", "architecture", "progress", "requirement", "experiment"]):
        concerns.append(
            FeedbackConcern(
                concern=(
                    "The AI should translate technical project status into stakeholder language covering architecture, "
                    "progress, requirement coverage, and experiment results."
                ),
                category="requirement",
                priority="medium",
                evidence_pointers=evidence_pointers,
            )
        )
    if not concerns:
        concerns.append(
            FeedbackConcern(
                concern=(
                    "The feedback should be interpreted into concrete concerns and mapped to explicit plan changes "
                    "before execution continues."
                ),
                category="other",
                priority="medium",
                evidence_pointers=evidence_pointers,
            )
        )
    return _dedupe_concerns(concerns)


def _build_clarification_questions(
    feedback: str,
    clarification_answers: list[str],
) -> list[FeedbackClarificationQuestion]:
    lowered = feedback.lower()
    base_questions = [
        FeedbackClarificationQuestion(
            question="Which parts of the briefing should pause for stakeholder feedback before the AI continues?",
            why_it_matters="This defines where the meeting changes from one-way reporting into an interactive decision loop.",
            options=["After risk and direction summary", "After each major section", "Only before execution changes"],
        ),
        FeedbackClarificationQuestion(
            question="Which stakeholder comments should block the next execution step until clarified?",
            why_it_matters="This separates hard requirements from suggestions so the agent does not overreact or ignore important input.",
            options=["Direction changes", "Requirement concerns", "All unresolved objections"],
        ),
        FeedbackClarificationQuestion(
            question="Where should the updated execution plan be written after feedback is interpreted?",
            why_it_matters="This decides whether the loop produces an immediately usable plan artifact or waits for another manual step.",
            options=["briefing_feedback_plan.json", "plan.md handoff section", "Both artifact and plan docs"],
        ),
    ]
    type_specific_questions = _build_type_specific_clarification_questions(feedback, lowered)
    selected_questions = _dedupe_questions([*type_specific_questions, *base_questions])[:8]
    answers = [_normalize_text(answer) for answer in clarification_answers if _normalize_text(answer)]
    if contains_forbidden_briefing_artifact_fields(answers):
        raise ValueError("Clarification answer contains forbidden secret, raw audio, or transcript artifact fields.")
    questions: list[FeedbackClarificationQuestion] = []
    for index, question in enumerate(selected_questions):
        answer = answers[index] if index < len(answers) else None
        questions.append(
            question.model_copy(
                update={
                    "answer_summary": _clip(answer, 240) if answer else None,
                    "status": "answered" if answer else "pending",
                }
            )
        )
    if _contains_any(feedback, lowered, ["执行方案", "计划", "plan"]):
        return questions
    if type_specific_questions:
        return questions[: min(5, len(questions))]
    return questions[:2]


def _build_type_specific_clarification_questions(
    feedback: str,
    lowered: str,
) -> list[FeedbackClarificationQuestion]:
    questions: list[FeedbackClarificationQuestion] = []
    if _contains_any(feedback, lowered, ["方向", "优先级", "priority", "direction", "roadmap"]):
        questions.append(
            FeedbackClarificationQuestion(
                question="Which direction or priority should change before the AI continues execution?",
                why_it_matters="Direction and priority changes can invalidate the current next step, so they must be explicit.",
                options=["Change current priority", "Change product direction", "Reorder next steps"],
            )
        )
    if _contains_any(feedback, lowered, ["需求", "不满足", "验收", "requirement", "acceptance", "not met"]):
        questions.append(
            FeedbackClarificationQuestion(
                question="Which requirement or acceptance criterion is not satisfied yet?",
                why_it_matters="The AI needs the unmet requirement boundary before it can revise scope or tests.",
                options=["Functional requirement", "Workflow requirement", "Acceptance criterion"],
            )
        )
    if _contains_any(feedback, lowered, ["架构", "进度", "实验", "结果", "architecture", "progress", "experiment", "result"]):
        questions.append(
            FeedbackClarificationQuestion(
                question="Which project-status explanation needs to be clearer for non-technical stakeholders?",
                why_it_matters="This determines whether the next plan should improve architecture, progress, requirement, or experiment communication.",
                options=["Architecture", "Progress", "Requirement coverage", "Experiment results"],
            )
        )
    if _contains_any(feedback, lowered, ["风险", "安全", "隐私", "secret", "privacy", "safety", "risk"]):
        questions.append(
            FeedbackClarificationQuestion(
                question="Which risk should block execution until the AI clarifies it?",
                why_it_matters="Safety, privacy, and project risks need different mitigation steps and should not be merged into generic feedback.",
                options=["Privacy or secrets", "Execution risk", "Product risk"],
            )
        )
    if _contains_any(feedback, lowered, ["写回", "保存", "落点", "artifact", "plan.md", "where should", "write back"]):
        questions.append(
            FeedbackClarificationQuestion(
                question="Where should this feedback change be written so the next agent step can use it?",
                why_it_matters="A clear write target prevents the meeting from producing feedback that is not connected to execution.",
                options=["plan.md", "briefing_feedback_plan.json", "Both"],
            )
        )
    return questions


def _build_decisions(clarification_answers: list[str]) -> list[str]:
    answers = [_normalize_text(answer) for answer in clarification_answers if _normalize_text(answer)]
    if not answers:
        return ["Treat stakeholder feedback as a first-class planning input before the agent continues execution."]
    return [f"Clarification accepted: {_clip(answer, 210)}" for answer in answers[:6]]


def _decision_from_clarification(
    question: FeedbackClarificationQuestion,
    answer_text: str,
) -> ClarificationMergeResult:
    kind = _clarification_kind(question.question)
    clipped = _clip(answer_text, 180)
    generic_decision = f"Clarification accepted: {_clip(answer_text, 210)}"
    if kind == "pause_policy":
        return ClarificationMergeResult(
            kind=kind,
            decisions=[
                generic_decision,
                f"Set briefing pause policy: {clipped}",
            ],
            plan_changes=[
                ExecutionPlanChange(
                    change_type="modify",
                    title="Apply stakeholder-defined briefing pause policy.",
                    rationale="The meeting must pause at agreed decision points before the AI continues execution.",
                    priority="high",
                )
            ],
            next_steps=["Apply the accepted pause policy during future stakeholder briefings."],
        )
    if kind == "blocking_rule":
        return ClarificationMergeResult(
            kind=kind,
            decisions=[
                generic_decision,
                f"Set feedback blocking rule: {clipped}",
            ],
            plan_changes=[
                ExecutionPlanChange(
                    change_type="modify",
                    title="Gate execution on stakeholder-defined blocking feedback.",
                    rationale="The agent should not continue when feedback matches the accepted blocking rule.",
                    priority="high",
                )
            ],
            next_steps=["Check answered feedback against the blocking rule before continuing implementation."],
        )
    if kind in {"plan_destination", "write_target"}:
        return ClarificationMergeResult(
            kind=kind,
            decisions=[
                generic_decision,
                f"Set feedback plan write target: {clipped}",
            ],
            plan_changes=[
                ExecutionPlanChange(
                    change_type="modify",
                    title="Write interpreted feedback to the accepted execution-plan target.",
                    rationale="The updated plan must land where the next code-agent step can consume it.",
                    priority="high",
                )
            ],
            next_steps=["Write the interpreted feedback plan to the accepted target before the next execution step."],
        )
    if kind == "direction_priority":
        return ClarificationMergeResult(
            kind=kind,
            decisions=[
                generic_decision,
                f"Update execution direction or priority: {clipped}",
            ],
            plan_changes=[
                ExecutionPlanChange(
                    change_type="reprioritize",
                    title="Reprioritize the next execution step from stakeholder clarification.",
                    rationale="Direction or priority feedback can invalidate the current implementation order.",
                    priority="high",
                )
            ],
            next_steps=["Reorder the next execution step according to the accepted direction or priority clarification."],
        )
    if kind == "requirement_gap":
        return ClarificationMergeResult(
            kind=kind,
            decisions=[
                generic_decision,
                f"Track unmet requirement or acceptance gap: {clipped}",
            ],
            plan_changes=[
                ExecutionPlanChange(
                    change_type="modify",
                    title="Revise acceptance criteria from stakeholder requirement clarification.",
                    rationale="A clarified requirement gap should update the plan before implementation continues.",
                    priority="high",
                )
            ],
            next_steps=["Update acceptance criteria and tests for the clarified requirement gap."],
        )
    if kind == "status_explanation":
        return ClarificationMergeResult(
            kind=kind,
            decisions=[
                generic_decision,
                f"Improve stakeholder explanation focus: {clipped}",
            ],
            plan_changes=[
                ExecutionPlanChange(
                    change_type="modify",
                    title="Improve non-technical project-status explanation.",
                    rationale="The briefing should translate the clarified project-status area into stakeholder language.",
                    priority="medium",
                )
            ],
            next_steps=["Revise the next briefing artifact to explain the clarified project-status area plainly."],
        )
    if kind == "risk_blocker":
        return ClarificationMergeResult(
            kind=kind,
            decisions=[
                generic_decision,
                f"Treat clarified risk as an execution blocker: {clipped}",
            ],
            plan_changes=[
                ExecutionPlanChange(
                    change_type="add",
                    title="Add mitigation for clarified blocking risk.",
                    rationale="Risk, safety, or privacy feedback should become an explicit mitigation before execution continues.",
                    priority="high",
                )
            ],
            next_steps=["Document the mitigation for the clarified blocking risk before continuing implementation."],
        )
    return ClarificationMergeResult(
        kind=kind,
        decisions=[generic_decision],
        plan_changes=[
            ExecutionPlanChange(
                change_type="modify",
                title="Reflect stakeholder clarification in the execution plan.",
                rationale="Answered feedback should be represented as an actionable plan change.",
                priority="medium",
            )
        ],
        next_steps=["Review the answered clarification before continuing execution."],
    )


def _clarification_kind(question: str) -> ClarificationDecisionKind:
    lowered = question.lower()
    if "pause" in lowered:
        return "pause_policy"
    if "block" in lowered and "risk" not in lowered:
        return "blocking_rule"
    if "updated execution plan" in lowered:
        return "plan_destination"
    if "direction or priority" in lowered:
        return "direction_priority"
    if "requirement or acceptance" in lowered:
        return "requirement_gap"
    if "project-status explanation" in lowered:
        return "status_explanation"
    if "risk" in lowered:
        return "risk_blocker"
    if "written" in lowered or "write" in lowered:
        return "write_target"
    return "general"


def _merge_plan_changes(
    existing: list[ExecutionPlanChange],
    additions: list[ExecutionPlanChange],
) -> list[ExecutionPlanChange]:
    merged: list[ExecutionPlanChange] = []
    seen: set[tuple[str, str]] = set()
    for change in [*existing, *additions]:
        key = (change.change_type, change.title)
        if key in seen:
            continue
        seen.add(key)
        merged.append(change)
    return merged[:12]


def _build_plan_changes(feedback: str) -> list[ExecutionPlanChange]:
    changes = [
        ExecutionPlanChange(
            change_type="add",
            title="Generate briefing_feedback_plan.json after every stakeholder briefing.",
            rationale="The product needs a durable artifact that turns user feedback into concerns, questions, decisions, and next steps.",
            priority="high",
        ),
        ExecutionPlanChange(
            change_type="add",
            title="Ask clarification questions when stakeholder intent is ambiguous.",
            rationale="The AI should not proceed from vague dissatisfaction directly into implementation without checking intent.",
            priority="high",
        ),
        ExecutionPlanChange(
            change_type="modify",
            title="Make the briefing loop update the execution plan before continuing work.",
            rationale="The final output must be an actionable plan update, not only a meeting/deck evidence packet.",
            priority="high",
        ),
    ]
    if _contains_any(feedback, feedback.lower(), ["轻量", "minimal", "skills", "skill"]):
        changes.append(
            ExecutionPlanChange(
                change_type="reprioritize",
                title="Keep the feedback loop lightweight and skill-friendly.",
                rationale="The product target is a low-manual-configuration skill workflow for multiple code agents.",
                priority="medium",
            )
        )
    return changes


def _build_updated_execution_plan(
    *,
    feedback_summary: str,
    answered_all: bool,
    clarification_answers: list[str],
) -> UpdatedExecutionPlan:
    next_steps = [
        "Capture stakeholder feedback as bounded text from CLI input, file input, or later STT output.",
        "Summarize the feedback into stakeholder-facing concerns without storing raw recordings or full meeting notes.",
        "Generate clarification questions for ambiguous opinions and mark pending items before execution continues.",
        "Merge answered clarifications into decisions and plan changes.",
        "Write briefing_feedback_plan.json and require the product smoke to verify it.",
    ]
    if answered_all:
        next_steps.append("Use the answered feedback plan as the next execution source of truth.")
    elif clarification_answers:
        next_steps.append("Continue only on answered decisions and keep remaining clarifications pending.")
    else:
        next_steps.append("Pause for stakeholder clarification before treating the updated plan as final.")
    return UpdatedExecutionPlan(
        summary=(
            "Shift Project Briefing Room from one-way reporting to an interactive feedback-to-plan loop. "
            f"Stakeholder signal: {feedback_summary}"
        ),
        next_steps=next_steps,
        acceptance_criteria=[
            "briefing_feedback_plan.json is generated by the quick product gate.",
            "The artifact contains interpreted concerns, clarification questions, plan changes, and an updated execution plan.",
            "The artifact avoids secrets, raw audio, full meeting notes, cookies, local storage, and unredacted meeting start URLs.",
            "The product smoke fails if the feedback plan is missing or does not contain actionable next steps.",
        ],
        out_of_scope=[
            "Speech-to-text opinion extraction.",
            "Provider-specific meeting SaaS automation.",
            "Automatic code edits from unresolved stakeholder feedback.",
        ],
    )


def _summarize_feedback(feedback: str) -> str:
    normalized = _normalize_text(feedback)
    if _contains_any(normalized, normalized.lower(), ["不满意", "too one-way", "one-way"]):
        return (
            "Stakeholder is not satisfied with a one-way briefing loop and wants feedback to shape the next "
            "execution step."
        )
    if _contains_any(normalized, normalized.lower(), ["听取", "反馈", "listen", "feedback"]):
        return (
            "Stakeholder wants the AI to actively listen during the briefing, clarify intent, and reflect the "
            "result in the execution plan."
        )
    if len(normalized) <= 360:
        return normalized
    return normalized[:357].rstrip() + "..."


def _contains_any(original: str, lowered: str, markers: list[str]) -> bool:
    return any((marker in original) or (marker.lower() in lowered) for marker in markers)


def _contains_forbidden_feedback_capture_artifact(value: str) -> bool:
    lowered = value.lower()
    if any(fragment in lowered for fragment in FORBIDDEN_FEEDBACK_CAPTURE_ARTIFACT_FRAGMENTS):
        return True
    speaker_line_count = 0
    for line in value.splitlines():
        stripped = line.strip().lower()
        if stripped.startswith(("speaker ", "speaker:", "user:", "assistant:", "reviewer:", "stakeholder:")):
            speaker_line_count += 1
    return speaker_line_count >= 4


def _dedupe_concerns(concerns: list[FeedbackConcern]) -> list[FeedbackConcern]:
    seen: set[tuple[str, str]] = set()
    deduped: list[FeedbackConcern] = []
    for concern in concerns:
        key = (concern.category, concern.concern)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(concern)
    return deduped[:12]


def _dedupe_questions(questions: list[FeedbackClarificationQuestion]) -> list[FeedbackClarificationQuestion]:
    seen: set[str] = set()
    deduped: list[FeedbackClarificationQuestion] = []
    for question in questions:
        key = question.question.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(question)
    return deduped


def _dedupe_limited_strings(values: list[str], *, max_item_length: int) -> list[str]:
    normalized = dedupe_strings(value.strip() for value in values if isinstance(value, str) and value.strip())
    too_long = [value for value in normalized if len(value) > max_item_length]
    if too_long:
        raise ValueError(f"String value exceeds {max_item_length} characters.")
    return normalized


def _normalize_text(value: str) -> str:
    return " ".join(str(value).split())


def _clip(value: str, max_length: int) -> str:
    return value if len(value) <= max_length else value[: max_length - 3].rstrip() + "..."
