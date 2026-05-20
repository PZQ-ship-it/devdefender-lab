from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import Field, ValidationError, field_validator

from devdefender_lab.briefing import (
    BriefingBaseModel,
    BriefingContext,
    contains_forbidden_briefing_artifact_fields,
    validate_evidence_pointer_strings,
)
from devdefender_lab.evidence import dedupe_strings


AgentKind = Literal["codex", "openclaude", "aider", "generic"]
DEFAULT_AGENT_BRIEFING_INPUT = Path("artifacts/agent_briefing_input.json")


class AgentBriefingInput(BriefingBaseModel):
    """Provider-neutral facts a code agent can hand to the briefing runtime."""

    schema_version: str = Field(default="1", pattern=r"^1$")
    agent_kind: AgentKind = "generic"
    project_name: str | None = Field(default=None, max_length=120)
    task_goal: str | None = Field(default=None, max_length=400)
    current_task: str | None = Field(default=None, max_length=400)
    changed_files: list[str] = Field(default_factory=list, max_length=100)
    completed_work: list[str] = Field(default_factory=list, max_length=50)
    in_progress_work: list[str] = Field(default_factory=list, max_length=50)
    blockers: list[str] = Field(default_factory=list, max_length=50)
    next_steps: list[str] = Field(default_factory=list, max_length=50)
    requirements: list[str] = Field(default_factory=list, max_length=50)
    tests: list[str] = Field(default_factory=list, max_length=100)
    artifacts: list[str] = Field(default_factory=list, max_length=100)
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


def load_agent_briefing_input(path: Path | str) -> AgentBriefingInput | None:
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
        return AgentBriefingInput.model_validate(payload)
    except ValidationError:
        return None


def write_agent_briefing_template(path: Path | str) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    template = AgentBriefingInput(
        agent_kind="generic",
        project_name="",
        task_goal="",
        current_task="",
        completed_work=[],
        in_progress_work=[],
        blockers=[],
        next_steps=[],
        requirements=[],
        tests=[],
        artifacts=[],
        architecture_facts=[],
        experiment_facts=[],
        risks=[],
        open_questions=[],
        constraints=["Do not include raw secrets, raw audio, full transcripts, cookies, or meeting start URLs."],
        evidence_pointers=[],
    )
    output_path.write_text(template.model_dump_json(indent=2), encoding="utf-8")
    return output_path


def write_agent_briefing_input(agent_input: AgentBriefingInput, path: Path | str, *, overwrite: bool = True) -> Path:
    output_path = Path(path)
    if output_path.exists() and not overwrite:
        raise FileExistsError(f"Agent briefing input already exists: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(agent_input.model_dump_json(indent=2), encoding="utf-8")
    return output_path


def agent_input_from_context(context: BriefingContext, *, agent_kind: AgentKind = "generic") -> AgentBriefingInput:
    return AgentBriefingInput(
        agent_kind=agent_kind,
        project_name=context.project_name,
        task_goal=context.task_goal,
        current_task=context.current_task,
        changed_files=context.changed_files,
        completed_work=context.completed_work,
        in_progress_work=context.in_progress_work,
        blockers=context.blockers,
        next_steps=context.next_steps,
        requirements=context.requirements,
        tests=context.tests,
        artifacts=context.artifacts,
        architecture_facts=context.architecture_facts,
        experiment_facts=context.experiment_facts,
        risks=context.risks,
        open_questions=context.open_questions,
        constraints=context.constraints,
        evidence_pointers=context.evidence_pointers,
    )


def merge_agent_input(context: BriefingContext, agent_input: AgentBriefingInput | None) -> BriefingContext:
    if agent_input is None:
        return context
    payload = context.model_dump(mode="json")
    payload.update(
        {
            "project_name": agent_input.project_name or context.project_name,
            "task_goal": agent_input.task_goal or context.task_goal,
            "current_task": agent_input.current_task or context.current_task,
            "changed_files": _merge(context.changed_files, agent_input.changed_files, max_items=100),
            "completed_work": _merge(context.completed_work, agent_input.completed_work),
            "in_progress_work": _merge(context.in_progress_work, agent_input.in_progress_work),
            "blockers": _merge(context.blockers, agent_input.blockers),
            "next_steps": _merge(context.next_steps, agent_input.next_steps),
            "requirements": _merge(context.requirements, agent_input.requirements),
            "tests": _merge(context.tests, agent_input.tests, max_items=100),
            "artifacts": _merge(context.artifacts, agent_input.artifacts, max_items=100),
            "architecture_facts": _merge(context.architecture_facts, agent_input.architecture_facts),
            "experiment_facts": _merge(context.experiment_facts, agent_input.experiment_facts),
            "risks": _merge(context.risks, agent_input.risks),
            "open_questions": _merge(context.open_questions, agent_input.open_questions),
            "constraints": _merge(context.constraints, agent_input.constraints),
            "evidence_pointers": _merge(context.evidence_pointers, agent_input.evidence_pointers),
        }
    )
    return BriefingContext.model_validate(payload)


def _merge(left: list[str], right: list[str], *, max_items: int = 50) -> list[str]:
    return dedupe_strings([*left, *right])[:max_items]


def _dedupe_limited_strings(values: list[str], *, max_item_length: int) -> list[str]:
    normalized = dedupe_strings(value.strip() for value in values if isinstance(value, str) and value.strip())
    too_long = [value for value in normalized if len(value) > max_item_length]
    if too_long:
        raise ValueError(f"String value exceeds {max_item_length} characters.")
    return normalized
