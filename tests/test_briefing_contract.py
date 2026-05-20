import json
from pathlib import Path

from devdefender_lab.briefing import BriefingContext
from devdefender_lab.briefing_contract import (
    AgentBriefingInput,
    load_agent_briefing_input,
    merge_agent_input,
    write_agent_briefing_template,
)


def test_agent_briefing_input_merges_into_context(tmp_path: Path) -> None:
    path = tmp_path / "agent.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "1",
                "agent_kind": "codex",
                "project_name": "Portable Briefing",
                "task_goal": "Make project briefings portable across code agents.",
                "current_task": "Define the provider-neutral input contract.",
                "changed_files": ["src/contract.py"],
                "completed_work": ["Workspace backend accepted."],
                "in_progress_work": ["Agent contract implementation."],
                "blockers": ["Need stakeholder confirmation on priority."],
                "next_steps": ["Run quick workspace gate."],
                "requirements": ["Agents can provide task context with one JSON file."],
                "tests": ["pytest tests/test_briefing_contract.py"],
                "evidence_pointers": ["timeline://thread-1#event=0&kind=briefing_generated"],
            }
        ),
        encoding="utf-8",
    )

    agent_input = load_agent_briefing_input(path)
    context = merge_agent_input(BriefingContext(task_goal="Fallback goal"), agent_input)

    assert isinstance(agent_input, AgentBriefingInput)
    assert context.project_name == "Portable Briefing"
    assert context.current_task == "Define the provider-neutral input contract."
    assert "Workspace backend accepted." in context.completed_work
    assert context.evidence_pointers == ["timeline://thread-1#event=0&kind=briefing_generated"]


def test_agent_briefing_input_rejects_forbidden_payload(tmp_path: Path) -> None:
    path = tmp_path / "agent.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "1",
                "agent_kind": "codex",
                "task_goal": "bad",
                "full_transcript": "private conversation",
            }
        ),
        encoding="utf-8",
    )

    assert load_agent_briefing_input(path) is None


def test_write_agent_briefing_template(tmp_path: Path) -> None:
    path = write_agent_briefing_template(tmp_path / "nested" / "agent.json")
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["schema_version"] == "1"
    assert payload["agent_kind"] == "generic"
    assert "constraints" in payload
