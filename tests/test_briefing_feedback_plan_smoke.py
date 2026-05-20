import json
from pathlib import Path

import pytest

from scripts.briefing_feedback_plan import generate_feedback_plan


def test_briefing_feedback_plan_cli_generates_plan_artifact(tmp_path: Path) -> None:
    out = tmp_path / "briefing_feedback_plan.json"

    result = generate_feedback_plan(
        feedback="这个闭环需要听取我的反馈，澄清意见，然后更新执行方案。",
        out=out,
        use_default_feedback=False,
    )
    payload = json.loads(out.read_text(encoding="utf-8"))

    assert result["ok"] is True
    assert result["feedback_source"] == "cli_text"
    assert result["checks"]["has_interpreted_concerns"] is True
    assert result["checks"]["has_clarification_questions"] is True
    assert result["checks"]["has_updated_execution_plan"] is True
    assert payload["needs_follow_up"] is True
    assert payload["updated_execution_plan"]["next_steps"]


def test_briefing_feedback_plan_cli_uses_feedback_file(tmp_path: Path) -> None:
    feedback_file = tmp_path / "feedback.txt"
    feedback_file.write_text("Please clarify my opinion before changing the plan.", encoding="utf-8")

    result = generate_feedback_plan(feedback_file=feedback_file, out=tmp_path / "out.json")

    assert result["ok"] is True
    assert result["feedback_source"] == "file"
    assert result["clarification_question_count"] >= 1


def test_briefing_feedback_plan_cli_uses_stt_text(tmp_path: Path) -> None:
    result = generate_feedback_plan(stt_text="Please pause after the risk summary.", out=tmp_path / "out.json")

    assert result["ok"] is True
    assert result["feedback_source"] == "stt_text"


def test_briefing_feedback_plan_requires_feedback(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        generate_feedback_plan(out=tmp_path / "out.json")
