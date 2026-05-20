import json
from pathlib import Path

from devdefender_lab.briefing_feedback import build_feedback_plan, write_feedback_plan
from devdefender_lab.briefing_plan_update import (
    PLAN_UPDATE_END,
    PLAN_UPDATE_START,
    apply_feedback_plan_to_markdown,
    replace_marked_section,
)


def test_apply_feedback_plan_writes_marked_plan_section(tmp_path: Path) -> None:
    feedback_plan_path = tmp_path / "briefing_feedback_plan.json"
    plan_path = tmp_path / "plan.md"
    report_path = tmp_path / "briefing_plan_update.json"
    plan_path.write_text("# Existing Plan\n\nKeep this.\n", encoding="utf-8")
    plan = build_feedback_plan(
        "The briefing should listen, clarify, and update the execution plan.",
        clarification_answers=[
            "Pause after risk summary.",
            "Direction changes block execution.",
            "Write both artifact and plan docs.",
        ],
    )
    write_feedback_plan(plan, feedback_plan_path)

    report = apply_feedback_plan_to_markdown(
        feedback_plan_path=feedback_plan_path,
        plan_path=plan_path,
        out=report_path,
    )
    text = plan_path.read_text(encoding="utf-8")

    assert report["ok"] is True
    assert report["ready_for_execution"] is True
    assert report["execution_source_of_truth"] is True
    assert report["blocking_reason"] == ""
    assert report["execution_next_steps"]
    assert report["pending_question_count"] == 0
    assert PLAN_UPDATE_START in text
    assert PLAN_UPDATE_END in text
    assert "Status: `ready_for_execution`" in text
    assert "Execution source of truth: `true`" in text
    assert "Ready: use this feedback plan as the source of truth" in text
    assert "Pause after risk summary." in text
    assert "# Existing Plan" in text
    assert json.loads(report_path.read_text(encoding="utf-8"))["ok"] is True


def test_apply_feedback_plan_preserves_pending_clarifications(tmp_path: Path) -> None:
    feedback_plan_path = tmp_path / "briefing_feedback_plan.json"
    plan_path = tmp_path / "plan.md"
    plan = build_feedback_plan("Please clarify my feedback before updating the plan.")
    write_feedback_plan(plan, feedback_plan_path)

    report = apply_feedback_plan_to_markdown(
        feedback_plan_path=feedback_plan_path,
        plan_path=plan_path,
        out=tmp_path / "report.json",
    )
    text = plan_path.read_text(encoding="utf-8")

    assert report["ok"] is True
    assert report["ready_for_execution"] is False
    assert report["execution_source_of_truth"] is False
    assert report["blocking_reason"].startswith(str(report["pending_question_count"]))
    assert report["execution_next_steps"] == []
    assert report["pending_questions"]
    assert report["needs_follow_up"] is True
    assert report["pending_question_count"] >= 1
    assert "Status: `needs_clarification`" in text
    assert "Execution source of truth: `false`" in text
    assert "Blocked: pending clarification questions" in text
    assert "Pending:" in text


def test_apply_feedback_plan_dry_run_does_not_write_plan(tmp_path: Path) -> None:
    feedback_plan_path = tmp_path / "briefing_feedback_plan.json"
    plan_path = tmp_path / "plan.md"
    write_feedback_plan(build_feedback_plan("Please update the plan."), feedback_plan_path)

    report = apply_feedback_plan_to_markdown(
        feedback_plan_path=feedback_plan_path,
        plan_path=plan_path,
        out=tmp_path / "report.json",
        dry_run=True,
    )

    assert report["ok"] is True
    assert report["dry_run"] is True
    assert not plan_path.exists()


def test_replace_marked_section_is_idempotent() -> None:
    original = "# Plan\n\nold\n\n" + PLAN_UPDATE_START + "\nold section\n" + PLAN_UPDATE_END + "\n\nfooter\n"
    section = PLAN_UPDATE_START + "\nnew section\n" + PLAN_UPDATE_END + "\n"

    updated = replace_marked_section(original, section)
    updated_again = replace_marked_section(updated, section)

    assert updated == updated_again
    assert "old section" not in updated
    assert "new section" in updated
    assert updated.count(PLAN_UPDATE_START) == 1
