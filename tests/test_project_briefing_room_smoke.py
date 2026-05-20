import json
import sys
from pathlib import Path

from scripts.project_briefing_room_smoke import (
    Step,
    build_briefing_artifacts,
    build_cross_checks,
    build_feedback_execution_steps,
    build_feedback_plan_steps,
    build_report,
    run_smoke,
    run_step,
    run_step_with_retries,
    summarize_feedback_plan_artifact,
    write_report,
)


def test_project_briefing_room_generates_codex_native_closure(tmp_path: Path) -> None:
    report = run_smoke(
        agent_backend="mock",
        artifact_dir=tmp_path,
        out=tmp_path / "project.json",
    )

    deck_path = tmp_path / "briefing_deck" / "slides.md"
    script_path = tmp_path / "briefing_deck" / "presenter_script.md"
    briefing_report_path = tmp_path / "briefing_deck" / "briefing_report.json"
    feedback_plan_path = tmp_path / "briefing_feedback_plan.json"

    assert report["ok"] is True
    assert report["checks"] == {
        "briefing_artifacts": True,
        "briefing_feedback_plan": True,
        "briefing_plan_update": True,
        "briefing_execution_gate": True,
    }
    assert report["mode"] == "codex_native"
    assert report["external_room_gates"] == "skipped"
    assert report["cross_checks"]["external_room_gates_skipped"] is True
    assert report["cross_checks"]["advanced_audit_included"] is False
    assert report["cross_checks"]["feedback_plan_has_updated_execution_plan_ok"] is True
    assert report["cross_checks"]["briefing_execution_gate_can_continue_ok"] is True
    assert deck_path.exists()
    assert script_path.exists()
    assert briefing_report_path.exists()
    assert feedback_plan_path.exists()
    assert (tmp_path / "briefing_plan_update.json").exists()
    assert (tmp_path / "briefing_execution_gate.json").exists()
    assert "```mermaid" in deck_path.read_text(encoding="utf-8")
    assert json.loads(feedback_plan_path.read_text(encoding="utf-8"))["updated_execution_plan"]["next_steps"]
    assert json.loads((tmp_path / "project.json").read_text(encoding="utf-8"))["ok"] is True


def test_project_briefing_room_supports_workspace_backend(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Workspace\n", encoding="utf-8")

    report = run_smoke(
        agent_backend="workspace",
        repo=tmp_path,
        artifact_dir=tmp_path / "artifacts",
        out=tmp_path / "project.json",
    )

    assert report["ok"] is True
    assert report["results"][0]["payload"]["generated_by"] == "workspace-briefing-adapter"
    assert report["checks"]["briefing_feedback_plan"] is True
    assert report["checks"]["briefing_execution_gate"] is True


def test_project_briefing_room_empty_clarifications_blocks_continuation(tmp_path: Path) -> None:
    report = run_smoke(
        agent_backend="mock",
        artifact_dir=tmp_path,
        clarification_answers=[],
        out=tmp_path / "project.json",
    )

    gate_payload = next(item["payload"] for item in report["results"] if item["name"] == "briefing_execution_gate")

    assert report["ok"] is False
    assert report["checks"]["briefing_feedback_plan"] is True
    assert report["cross_checks"]["briefing_execution_gate_can_continue_ok"] is False
    assert gate_payload["can_continue"] is False
    assert gate_payload["pending_questions"]


def test_build_briefing_artifacts_reports_required_sections(tmp_path: Path) -> None:
    result = build_briefing_artifacts(agent_backend="mock", artifact_dir=tmp_path)
    checks = result["payload"]["checks"]

    assert result["ok"] is True
    assert checks["briefing_report_written"] is True
    assert checks["deck_written"] is True
    assert checks["presenter_script_written"] is True
    assert checks["mermaid_present"] is True
    assert checks["summary_present"] is True
    assert checks["progress_present"] is True
    assert checks["requirements_present"] is True
    assert checks["experiments_present"] is True
    assert checks["risks_present"] is True
    assert checks["questions_present"] is True
    assert checks["next_asks_present"] is True
    assert checks["evidence_pointers_present"] is True
    assert checks["no_forbidden_artifact_fields"] is True


def test_build_briefing_artifacts_passes_agent_input_to_workspace_backend(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Workspace\n", encoding="utf-8")
    agent_input = tmp_path / "agent.json"
    agent_input.write_text(
        json.dumps(
            {
                "schema_version": "1",
                "agent_kind": "codex",
                "project_name": "Contract Driven Briefing",
                "task_goal": "Accept agent-supplied task context.",
                "current_task": "Wire CLI --agent-input into workspace backend.",
                "completed_work": ["CLI option added."],
            }
        ),
        encoding="utf-8",
    )

    result = build_briefing_artifacts(
        agent_backend="workspace",
        artifact_dir=tmp_path / "artifacts",
        repo=tmp_path,
        agent_input=agent_input,
    )
    briefing_report = json.loads((tmp_path / "artifacts" / "briefing_deck" / "briefing_report.json").read_text(encoding="utf-8"))

    assert result["ok"] is True
    assert briefing_report["project_name"] == "Contract Driven Briefing"
    assert "Current task focus" in briefing_report["audience_summary"]


def test_build_feedback_plan_steps_supports_all_feedback_sources(tmp_path: Path) -> None:
    feedback_file = tmp_path / "feedback.txt"
    steps = build_feedback_plan_steps(
        artifact_dir=tmp_path,
        timeout=90,
        feedback="typed feedback",
        feedback_file=feedback_file,
        stt_text="spoken feedback",
        clarification_answers=["answer 1", "answer 2"],
        feedback_plan_out=tmp_path / "briefing_feedback_plan.json",
    )

    assert [step.name for step in steps] == ["briefing_feedback_plan"]
    command = steps[0].command
    assert command[:2] == [sys.executable, str(Path.cwd() / "scripts" / "briefing_feedback_plan.py")]
    assert "--feedback" in command
    assert "--feedback-file" in command
    assert "--stt-text" in command
    assert command.count("--clarification") == 2
    assert steps[0].report_path == tmp_path / "briefing_feedback_plan.smoke.json"


def test_build_feedback_execution_steps_runs_plan_update_then_gate(tmp_path: Path) -> None:
    steps = build_feedback_execution_steps(
        timeout=90,
        feedback_plan_out=tmp_path / "briefing_feedback_plan.json",
        feedback_plan_update_out=tmp_path / "briefing_plan_update.json",
        feedback_execution_gate_out=tmp_path / "briefing_execution_gate.json",
        plan_path=tmp_path / "plan.md",
    )

    assert [step.name for step in steps] == ["briefing_plan_update", "briefing_execution_gate"]
    assert steps[0].command == [
        sys.executable,
        str(Path.cwd() / "scripts" / "apply_briefing_feedback_plan.py"),
        "--feedback-plan",
        str(tmp_path / "briefing_feedback_plan.json"),
        "--plan",
        str(tmp_path / "plan.md"),
        "--out",
        str(tmp_path / "briefing_plan_update.json"),
    ]
    assert steps[1].command == [
        sys.executable,
        str(Path.cwd() / "scripts" / "briefing_execution_gate.py"),
        "--plan-update",
        str(tmp_path / "briefing_plan_update.json"),
        "--out",
        str(tmp_path / "briefing_execution_gate.json"),
    ]


def test_build_report_rejects_damaged_feedback_plan_artifact(tmp_path: Path) -> None:
    briefing = build_briefing_artifacts(agent_backend="mock", artifact_dir=tmp_path)
    feedback_plan_path = tmp_path / "briefing_feedback_plan.json"
    feedback_plan_path.write_text(
        json.dumps(
            {
                "interpreted_concerns": [{"concern": "Listen", "category": "workflow", "priority": "high"}],
                "clarification_questions": [{"question": "Where should we pause?", "status": "pending"}],
                "plan_changes": [{"title": "Update plan"}],
                "updated_execution_plan": {"next_steps": []},
            }
        ),
        encoding="utf-8",
    )
    results = [
        briefing,
        {
            "name": "briefing_feedback_plan",
            "ok": True,
            "return_code": 0,
            "payload": {
                "ok": True,
                "checks": {
                    "has_clarification_questions": True,
                    "has_updated_execution_plan": True,
                    "has_plan_changes": True,
                },
            },
        },
    ]

    report = build_report(
        results,
        ["briefing_artifacts", "briefing_feedback_plan"],
        feedback_plan_path=feedback_plan_path,
    )

    assert report["ok"] is False
    assert report["checks"]["briefing_feedback_plan"] is True
    assert report["cross_checks"]["feedback_plan_artifact_has_actionable_next_steps_ok"] is False


def test_build_cross_checks_rejects_blocked_execution_gate(tmp_path: Path) -> None:
    briefing = build_briefing_artifacts(agent_backend="mock", artifact_dir=tmp_path)
    feedback_plan_path = tmp_path / "briefing_feedback_plan.json"
    feedback_plan_path.write_text(
        json.dumps(
            {
                "interpreted_concerns": [{"concern": "Listen", "category": "workflow", "priority": "high"}],
                "clarification_questions": [{"question": "Where should we pause?", "status": "pending"}],
                "plan_changes": [{"title": "Update plan"}],
                "updated_execution_plan": {"next_steps": ["Capture feedback."]},
            }
        ),
        encoding="utf-8",
    )
    results = [
        briefing,
        {
            "name": "briefing_feedback_plan",
            "ok": True,
            "return_code": 0,
            "payload": {"ok": True, "checks": {"has_clarification_questions": True, "has_updated_execution_plan": True, "has_plan_changes": True}},
        },
        {"name": "briefing_plan_update", "ok": True, "return_code": 0, "payload": {"ok": True, "execution_source_of_truth": False}},
        {
            "name": "briefing_execution_gate",
            "ok": True,
            "return_code": 0,
            "payload": {"ok": True, "can_continue": False, "source_of_truth": False},
        },
    ]

    checks = build_cross_checks(results, feedback_plan_path=feedback_plan_path)

    assert checks["briefing_execution_gate_ok"] is True
    assert checks["briefing_execution_gate_can_continue_ok"] is False


def test_build_cross_checks_rejects_forbidden_summary_payload(tmp_path: Path) -> None:
    briefing = build_briefing_artifacts(agent_backend="mock", artifact_dir=tmp_path)
    results = [
        briefing,
        {
            "name": "briefing_feedback_plan",
            "ok": True,
            "return_code": 0,
            "payload": {"ok": True, "checks": {"bad": "Bearer abc.def"}},
        },
    ]

    checks = build_cross_checks(results, skip_feedback_plan=False)

    assert checks["no_forbidden_artifact_fields_ok"] is False


def test_feedback_plan_artifact_summary_requires_actionable_next_steps(tmp_path: Path) -> None:
    feedback_plan_path = tmp_path / "briefing_feedback_plan.json"
    feedback_plan_path.write_text(
        json.dumps(
            {
                "interpreted_concerns": [{"concern": "Listen", "category": "workflow", "priority": "high"}],
                "clarification_questions": [{"question": "Where should we pause?", "status": "pending"}],
                "plan_changes": [{"title": "Update plan"}],
                "updated_execution_plan": {"next_steps": []},
            }
        ),
        encoding="utf-8",
    )

    summary = summarize_feedback_plan_artifact(feedback_plan_path)

    assert summary["present"] is True
    assert summary["has_interpreted_concerns"] is True
    assert summary["has_actionable_next_steps"] is False


def test_run_step_prefers_current_stdout_when_report_file_is_stale(tmp_path: Path) -> None:
    report_path = tmp_path / "replay.json"
    report_path.write_text(json.dumps({"ok": True, "thread_id": "old-thread"}), encoding="utf-8")
    stdout_json = json.dumps({"ok": True, "thread_id": "fresh-thread"})
    command = [sys.executable, "-c", f"print({stdout_json!r})"]

    result = run_step(Step("room_replay", command, timeout=30, report_path=report_path))

    assert result["ok"] is True
    assert result["payload"]["thread_id"] == "fresh-thread"
    assert json.loads(report_path.read_text(encoding="utf-8"))["thread_id"] == "fresh-thread"


def test_run_step_with_retries_reports_previous_failure(tmp_path: Path) -> None:
    state_path = tmp_path / "attempt.txt"
    report_path = tmp_path / "step.json"
    command = [
        sys.executable,
        "-c",
        (
            "from pathlib import Path; import json, sys; "
            f"state=Path({str(state_path)!r}); out=Path({str(report_path)!r}); "
            "attempt=int(state.read_text()) if state.exists() else 0; "
            "state.write_text(str(attempt+1)); "
            "payload={'ok': attempt > 0}; "
            "out.write_text(json.dumps(payload)); "
            "sys.exit(0 if payload['ok'] else 1)"
        ),
    ]

    result = run_step_with_retries(Step("briefing_feedback_plan", command, timeout=30, report_path=report_path, retries=1))

    assert result["ok"] is True
    assert result["attempt_count"] == 2
    assert result["previous_failures"][0]["return_code"] == 1


def test_project_briefing_room_writes_report(tmp_path: Path) -> None:
    report = {"ok": True, "checks": {"project_briefing_room": True}}
    out = tmp_path / "nested" / "project.json"

    write_report(report, out)

    assert json.loads(out.read_text(encoding="utf-8")) == report
