import json
from pathlib import Path

import pytest

from devdefender_lab.briefing_feedback import build_feedback_plan, write_feedback_plan
from scripts.answer_briefing_clarification import answer_clarification


def test_answer_briefing_clarification_updates_feedback_plan(tmp_path: Path) -> None:
    path = tmp_path / "briefing_feedback_plan.json"
    write_feedback_plan(build_feedback_plan("The AI should listen, clarify, and update the plan."), path)

    result = answer_clarification(
        feedback_plan_path=path,
        question_index=1,
        answer="Pause after direction and risk summary, then before final execution plan.",
    )
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert result["ok"] is True
    assert result["pending_question_count"] == 2
    assert result["answered_question_count"] == 1
    assert payload["clarification_questions"][0]["status"] == "answered"
    assert payload["clarification_questions"][0]["answer_summary"].startswith("Pause after direction")


def test_answer_briefing_clarification_can_write_to_new_path(tmp_path: Path) -> None:
    source = tmp_path / "briefing_feedback_plan.json"
    target = tmp_path / "answered.json"
    write_feedback_plan(build_feedback_plan("The AI should listen, clarify, and update the plan."), source)

    result = answer_clarification(
        feedback_plan_path=source,
        question_index=1,
        answer="Pause after risk summary.",
        out=target,
    )

    assert result["ok"] is True
    assert target.exists()
    assert json.loads(source.read_text(encoding="utf-8"))["clarification_questions"][0]["status"] == "pending"
    assert json.loads(target.read_text(encoding="utf-8"))["clarification_questions"][0]["status"] == "answered"


def test_answer_briefing_clarification_rejects_invalid_index(tmp_path: Path) -> None:
    path = tmp_path / "briefing_feedback_plan.json"
    write_feedback_plan(build_feedback_plan("The AI should listen, clarify, and update the plan."), path)

    with pytest.raises(ValueError):
        answer_clarification(feedback_plan_path=path, question_index=99, answer="No.")
