import json
from pathlib import Path

from devdefender_lab.briefing_execution_gate import evaluate_briefing_execution_gate
from scripts.briefing_execution_gate import main


def test_execution_gate_allows_ready_source_of_truth(tmp_path: Path) -> None:
    report_path = tmp_path / "briefing_plan_update.json"
    report_path.write_text(
        json.dumps(
            {
                "ok": True,
                "execution_source_of_truth": True,
                "blocking_reason": "",
                "execution_next_steps": ["Implement the accepted next step."],
                "pending_questions": [],
            }
        ),
        encoding="utf-8",
    )

    report = evaluate_briefing_execution_gate(report_path)

    assert report["ok"] is True
    assert report["can_continue"] is True
    assert report["source_of_truth"] is True
    assert report["next_steps"] == ["Implement the accepted next step."]
    assert report["blocking_reason"] == ""


def test_execution_gate_blocks_pending_questions(tmp_path: Path) -> None:
    report_path = tmp_path / "briefing_plan_update.json"
    report_path.write_text(
        json.dumps(
            {
                "ok": True,
                "execution_source_of_truth": False,
                "blocking_reason": "1 clarification question(s) must be answered before execution continues.",
                "execution_next_steps": [],
                "pending_questions": ["Which risk should block execution?"],
            }
        ),
        encoding="utf-8",
    )

    report = evaluate_briefing_execution_gate(report_path)

    assert report["ok"] is True
    assert report["can_continue"] is False
    assert report["source_of_truth"] is False
    assert report["next_steps"] == []
    assert report["pending_questions"] == ["Which risk should block execution?"]
    assert "clarification" in report["blocking_reason"]


def test_execution_gate_rejects_missing_report(tmp_path: Path) -> None:
    report = evaluate_briefing_execution_gate(tmp_path / "missing.json")

    assert report["ok"] is False
    assert report["can_continue"] is False
    assert report["checks"]["report_loaded"] is False


def test_execution_gate_rejects_unsafe_report(tmp_path: Path) -> None:
    report_path = tmp_path / "briefing_plan_update.json"
    report_path.write_text(json.dumps({"execution_next_steps": ["Bearer abc.def"]}), encoding="utf-8")

    report = evaluate_briefing_execution_gate(report_path)

    assert report["ok"] is False
    assert report["checks"]["no_forbidden_artifact_fields"] is False


def test_briefing_execution_gate_cli_writes_report(tmp_path: Path, monkeypatch) -> None:
    report_path = tmp_path / "briefing_plan_update.json"
    out = tmp_path / "gate.json"
    report_path.write_text(
        json.dumps(
            {
                "ok": True,
                "execution_source_of_truth": True,
                "blocking_reason": "",
                "execution_next_steps": ["Use feedback plan."],
                "pending_questions": [],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "sys.argv",
        ["briefing_execution_gate.py", "--plan-update", str(report_path), "--out", str(out)],
    )

    assert main() == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["can_continue"] is True
    assert payload["next_steps"] == ["Use feedback plan."]
