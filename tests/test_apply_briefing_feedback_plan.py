import json
from pathlib import Path

from devdefender_lab.briefing_feedback import build_feedback_plan, write_feedback_plan
from scripts.apply_briefing_feedback_plan import main


def test_apply_briefing_feedback_plan_cli_updates_plan(tmp_path: Path, monkeypatch) -> None:
    feedback_plan = tmp_path / "briefing_feedback_plan.json"
    plan_path = tmp_path / "plan.md"
    out = tmp_path / "report.json"
    write_feedback_plan(
        build_feedback_plan(
            "The briefing should clarify and update the plan.",
            clarification_answers=[
                "Pause after risk summary.",
                "Direction changes block execution.",
                "Write both docs and artifact.",
            ],
        ),
        feedback_plan,
    )
    plan_path.write_text("# Plan\n", encoding="utf-8")
    monkeypatch.setattr(
        "sys.argv",
        [
            "apply_briefing_feedback_plan.py",
            "--feedback-plan",
            str(feedback_plan),
            "--plan",
            str(plan_path),
            "--out",
            str(out),
        ],
    )

    assert main() == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    text = plan_path.read_text(encoding="utf-8")
    assert report["ok"] is True
    assert report["ready_for_execution"] is True
    assert report["execution_source_of_truth"] is True
    assert report["execution_next_steps"]
    assert "Project Briefing Feedback Execution Plan" in text


def test_apply_briefing_feedback_plan_cli_fails_for_missing_plan(tmp_path: Path, monkeypatch) -> None:
    out = tmp_path / "report.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "apply_briefing_feedback_plan.py",
            "--feedback-plan",
            str(tmp_path / "missing.json"),
            "--plan",
            str(tmp_path / "plan.md"),
            "--out",
            str(out),
        ],
    )

    assert main() == 1
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["ok"] is False
