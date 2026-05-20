import json
import subprocess
from pathlib import Path

from scripts.project_briefing_room_doctor import (
    DEFAULT_INVOCATION,
    build_doctor_report,
    main,
    run_quick_smoke,
)


def test_readme_and_skill_expose_product_invocation() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    skill = Path("skills/project-briefing-room/SKILL.md").read_text(encoding="utf-8")

    assert DEFAULT_INVOCATION in readme
    assert DEFAULT_INVOCATION in skill
    assert "project_briefing_room_doctor.py" in readme
    assert "Project Briefing Room Quick Start" in readme
    assert "Default User Entry" in skill


def test_build_doctor_report_can_skip_quick_smoke(tmp_path: Path) -> None:
    report = build_doctor_report(
        codex_home=tmp_path / "codex",
        require_installed_skill=False,
        skip_quick_smoke=True,
    )

    assert report["ok"] is True
    assert report["invocation"] == DEFAULT_INVOCATION
    assert report["checks"]["source_skill_present"] is True
    assert report["checks"]["source_skill_has_product_invocation"] is True
    assert report["checks"]["required_scripts_present"] is True
    assert report["checks"]["installed_skill_present"] is True
    assert report["checks"]["quick_smoke_ok"] is True


def test_build_doctor_report_can_require_installed_skill(tmp_path: Path) -> None:
    report = build_doctor_report(
        codex_home=tmp_path / "codex",
        require_installed_skill=True,
        skip_quick_smoke=True,
    )

    assert report["ok"] is False
    assert report["checks"]["installed_skill_present"] is False


def test_run_quick_smoke_reports_minimal_closure(tmp_path: Path) -> None:
    report = run_quick_smoke(timeout=60)

    assert report["ok"] is True
    assert report["checks"]["quick_smoke_completed"] is True
    assert report["checks"]["quick_smoke_no_external_room_required"] is True
    assert report["checks"]["feedback_plan_generated"] is True
    assert report["checks"]["plan_update_generated"] is True
    assert report["checks"]["session_markdown_generated"] is True
    assert report["checks"]["advanced_audit_not_required"] is True
    assert report["checks"]["no_forbidden_artifact_fields"] is True


def test_run_quick_smoke_reports_runner_failure() -> None:
    def fake_runner(*_args, **_kwargs):
        return subprocess.CompletedProcess(args=[], returncode=1, stdout=json.dumps({"ok": False}), stderr="failed")

    report = run_quick_smoke(timeout=60, runner=fake_runner)

    assert report["ok"] is False
    assert report["return_code"] == 1
    assert report["checks"]["quick_smoke_completed"] is False


def test_project_briefing_room_doctor_cli_writes_report(tmp_path: Path, monkeypatch) -> None:
    out = tmp_path / "doctor.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "project_briefing_room_doctor.py",
            "--skip-quick-smoke",
            "--out",
            str(out),
        ],
    )

    assert main() == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert payload["invocation"] == DEFAULT_INVOCATION
