import json
from pathlib import Path

import pytest

from devdefender_lab.briefing import MockBriefingAdapter, default_briefing_context
from devdefender_lab.briefing_feedback import (
    answer_feedback_clarification,
    build_feedback_plan,
    build_feedback_plan_from_input,
    load_feedback_plan,
    select_feedback_input,
    write_feedback_plan,
)


def test_feedback_plan_turns_dissatisfaction_into_clarification_and_execution_plan() -> None:
    report = MockBriefingAdapter().build_report(default_briefing_context())

    plan = build_feedback_plan(
        "这个闭环我不满意，AI汇报过程中应该重点听取我的反馈，并和我交互澄清我的意见，然后更新之后的执行方案",
        briefing_report=report,
    )

    assert plan.project_name == "DevDefender Lab"
    assert plan.needs_follow_up is True
    assert any(concern.category == "workflow" for concern in plan.interpreted_concerns)
    assert any(question.status == "pending" for question in plan.clarification_questions)
    assert any(change.change_type == "add" for change in plan.plan_changes)
    assert "briefing_feedback_plan.json" in " ".join(plan.updated_execution_plan.acceptance_criteria)
    assert plan.evidence_pointers


def test_feedback_plan_summarizes_feedback_for_stakeholders() -> None:
    plan = build_feedback_plan(
        "I am not satisfied because this is too one-way. It should listen to feedback and update the plan."
    )
    concerns = " ".join(concern.concern for concern in plan.interpreted_concerns)

    assert "Stakeholder is not satisfied" in plan.feedback_summary
    assert "one-way status report" in concerns
    assert "updated execution plan" in concerns
    assert "I am not satisfied" not in plan.feedback_summary


def test_feedback_plan_maps_project_status_language_to_requirement_concern() -> None:
    plan = build_feedback_plan(
        "The briefing needs architecture, progress, requirement coverage, and experiment result explanations."
    )

    assert any(
        "translate technical project status" in concern.concern and concern.category == "requirement"
        for concern in plan.interpreted_concerns
    )


def test_feedback_plan_generates_direction_specific_clarification() -> None:
    plan = build_feedback_plan("The direction is wrong and the priority should change before implementation.")
    questions = [question.question for question in plan.clarification_questions]

    assert questions[0] == "Which direction or priority should change before the AI continues execution?"
    assert any(question.status == "pending" for question in plan.clarification_questions)
    assert plan.needs_follow_up is True


def test_feedback_plan_generates_requirement_specific_clarification() -> None:
    plan = build_feedback_plan("The requirement is not met and the acceptance criterion is unclear.")
    questions = " ".join(question.question for question in plan.clarification_questions)

    assert "Which requirement or acceptance criterion is not satisfied yet?" in questions


def test_feedback_plan_generates_project_status_clarification() -> None:
    plan = build_feedback_plan("Architecture, progress, and experiment result explanations are not clear enough.")
    questions = " ".join(question.question for question in plan.clarification_questions)

    assert "Which project-status explanation needs to be clearer" in questions


def test_feedback_plan_generates_risk_specific_clarification() -> None:
    plan = build_feedback_plan("Privacy and safety risk should block execution until clarified.")
    questions = " ".join(question.question for question in plan.clarification_questions)

    assert "Which risk should block execution" in questions


def test_feedback_plan_generates_write_target_clarification() -> None:
    plan = build_feedback_plan("Where should the feedback write back go, artifact or plan.md?")
    questions = " ".join(question.question for question in plan.clarification_questions)

    assert "Where should this feedback change be written" in questions


def test_select_feedback_input_normalizes_cli_text() -> None:
    feedback_input = select_feedback_input(feedback="  Please listen, clarify, and update the plan.  ")

    assert feedback_input.source == "cli_text"
    assert feedback_input.text == "Please listen, clarify, and update the plan."


def test_select_feedback_input_supports_file_and_stt_sources(tmp_path: Path) -> None:
    feedback_file = tmp_path / "feedback.txt"
    feedback_file.write_text("Please clarify before changing the plan.", encoding="utf-8")

    file_input = select_feedback_input(feedback_file=feedback_file)
    stt_input = select_feedback_input(stt_text="Please pause after risks.")

    assert file_input.source == "file"
    assert file_input.text == "Please clarify before changing the plan."
    assert file_input.path == str(feedback_file)
    assert stt_input.source == "stt_text"
    assert stt_input.text == "Please pause after risks."


def test_build_feedback_plan_from_input_preserves_source() -> None:
    feedback_input = select_feedback_input(
        feedback="The room feedback should clarify my decision before execution.",
        source="room_typed_feedback",
    )

    plan = build_feedback_plan_from_input(feedback_input)

    assert plan.source == "room_typed_feedback"
    assert plan.updated_execution_plan.next_steps


def test_select_feedback_input_rejects_forbidden_file(tmp_path: Path) -> None:
    feedback_file = tmp_path / "feedback.txt"
    feedback_file.write_text("Bearer abc.def", encoding="utf-8")

    with pytest.raises(ValueError):
        select_feedback_input(feedback_file=feedback_file)


def test_select_feedback_input_rejects_full_meeting_transcript() -> None:
    with pytest.raises(ValueError):
        select_feedback_input(
            stt_text=(
                "Full transcript:\n"
                "Speaker 1: Please continue.\n"
                "Speaker 2: I disagree.\n"
                "Speaker 1: Can you clarify?\n"
                "Speaker 2: Update the plan."
            )
        )


def test_feedback_plan_rejects_raw_audio_artifact_reference() -> None:
    with pytest.raises(ValueError):
        build_feedback_plan("The feedback is stored at audio_path=meeting.wav")


def test_feedback_plan_with_clarifications_records_decisions() -> None:
    plan = build_feedback_plan(
        "The AI should listen, clarify, and update the next execution plan.",
        clarification_answers=[
            "Pause after risk and direction summary.",
            "Direction changes and requirement concerns block execution.",
            "Write both the artifact and plan docs.",
        ],
    )

    assert plan.needs_follow_up is False
    assert all(question.status == "answered" for question in plan.clarification_questions)
    assert len(plan.decisions) == 3
    assert "Use the answered feedback plan" in " ".join(plan.updated_execution_plan.next_steps)


def test_answer_feedback_clarification_updates_follow_up_state() -> None:
    plan = build_feedback_plan("The AI should listen, clarify, and update the next execution plan.")

    updated = answer_feedback_clarification(
        plan,
        question_index=1,
        answer="Pause after direction, risk, and requirements summary, then again before the final execution plan.",
    )

    assert updated.needs_follow_up is True
    assert updated.clarification_questions[0].status == "answered"
    assert updated.clarification_questions[0].answer_summary.startswith("Pause after direction")
    assert updated.clarification_questions[1].status == "pending"
    assert any("Pause after direction" in decision for decision in updated.decisions)
    assert any("Set briefing pause policy" in decision for decision in updated.decisions)
    assert any(change.title == "Apply stakeholder-defined briefing pause policy." for change in updated.plan_changes)


def test_answer_feedback_clarification_marks_ready_when_all_answered() -> None:
    plan = build_feedback_plan(
        "The AI should listen, clarify, and update the next execution plan.",
        clarification_answers=[
            "Pause after risk summary.",
            "Direction changes block execution.",
        ],
    )

    updated = answer_feedback_clarification(plan, question_index=3, answer="Write both artifact and plan docs.")

    assert updated.needs_follow_up is False
    assert all(question.status == "answered" for question in updated.clarification_questions)
    assert "Use the answered feedback plan" in " ".join(updated.updated_execution_plan.next_steps)


def test_answer_direction_clarification_reprioritizes_plan() -> None:
    plan = build_feedback_plan("The direction is wrong and the priority should change.")

    updated = answer_feedback_clarification(
        plan,
        question_index=1,
        answer="Prioritize VS Code Codex workflow closure before adding more providers.",
    )

    assert any("Update execution direction or priority" in decision for decision in updated.decisions)
    assert any(
        change.change_type == "reprioritize"
        and change.title == "Reprioritize the next execution step from stakeholder clarification."
        for change in updated.plan_changes
    )
    assert "Reorder the next execution step" in " ".join(updated.updated_execution_plan.next_steps)


def test_answer_requirement_clarification_updates_acceptance_plan() -> None:
    plan = build_feedback_plan("The requirement is not met and the acceptance criterion is unclear.")

    updated = answer_feedback_clarification(
        plan,
        question_index=1,
        answer="Product smoke must fail if the feedback plan has no actionable next step.",
    )

    assert any("Track unmet requirement or acceptance gap" in decision for decision in updated.decisions)
    assert any(
        change.title == "Revise acceptance criteria from stakeholder requirement clarification."
        for change in updated.plan_changes
    )
    assert "Update acceptance criteria" in " ".join(updated.updated_execution_plan.next_steps)


def test_answer_risk_clarification_adds_blocking_mitigation() -> None:
    plan = build_feedback_plan("Privacy and safety risk should block execution until clarified.")

    updated = answer_feedback_clarification(
        plan,
        question_index=1,
        answer="Do not proceed if feedback includes secrets, raw audio, or full transcripts.",
    )

    assert any("Treat clarified risk as an execution blocker" in decision for decision in updated.decisions)
    assert any(change.title == "Add mitigation for clarified blocking risk." for change in updated.plan_changes)


def test_answer_feedback_clarification_rejects_forbidden_answer() -> None:
    plan = build_feedback_plan("The AI should listen, clarify, and update the next execution plan.")

    with pytest.raises(ValueError):
        answer_feedback_clarification(plan, question_index=1, answer="Bearer abc.def")


def test_feedback_plan_rejects_forbidden_feedback() -> None:
    with pytest.raises(ValueError):
        build_feedback_plan("Bearer abc.def should not be stored")


def test_write_and_load_feedback_plan(tmp_path: Path) -> None:
    path = tmp_path / "briefing_feedback_plan.json"
    plan = build_feedback_plan("Please ask clarifying questions and update the plan.")

    written = write_feedback_plan(plan, path)
    loaded = load_feedback_plan(written)
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert loaded == plan
    assert payload["schema_version"] == "1"
    assert payload["updated_execution_plan"]["next_steps"]
