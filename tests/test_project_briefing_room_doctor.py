import json
import subprocess
import tomllib
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


def test_readme_and_skill_use_formal_feedback_artifact_paths() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    skill = Path("skills/project-briefing-room/SKILL.md").read_text(encoding="utf-8")
    docs = readme + "\n" + skill

    assert "artifacts/project_briefing_room/briefing_feedback_plan.json" in docs
    assert "artifacts/project_briefing_room/briefing_plan_update.json" in docs
    assert "artifacts/project_briefing_room/briefing_execution_gate.json" in docs
    assert "artifacts\\project_briefing_room\\briefing_feedback_plan.json" in docs
    assert "pending_questions" in docs
    assert "can_continue: false" in docs
    assert "artifacts/briefing_feedback_plan.json" not in docs
    assert "artifacts\\briefing_feedback_plan.json" not in docs
    assert "artifacts/briefing_plan_update.json" not in docs
    assert "artifacts\\briefing_plan_update.json" not in docs
    assert "artifacts/briefing_execution_gate.json" not in docs
    assert "artifacts\\briefing_execution_gate.json" not in docs


def test_readme_and_skill_keep_feedback_judgment_in_codex() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    skill = Path("skills/project-briefing-room/SKILL.md").read_text(encoding="utf-8")
    docs = readme + "\n" + skill

    assert "Codex should present" in readme
    assert "listen to the user's feedback" in readme
    assert "Scripts are only for recording" in readme
    assert "Codex owns the semantic work" in skill
    assert "Scripts own deterministic persistence and checks only" in skill
    assert "discuss them with the stakeholder in the Codex chat" in skill
    assert "resolve_briefing_feedback.py" not in docs
    assert "automatically interpret feedback" not in docs.casefold()


def test_release_packaging_contract_is_documented() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    scripts = pyproject["project"]["scripts"]
    readme = Path("README.md").read_text(encoding="utf-8")
    checklist = Path("RELEASE_CHECKLIST.md").read_text(encoding="utf-8")
    plan_head = "\n".join(Path("plan.md").read_text(encoding="utf-8", errors="ignore").splitlines()[:25])

    assert scripts["project-briefing-room"] == "devdefender_lab.cli:project_briefing_room"
    assert scripts["project-briefing-room-doctor"] == "devdefender_lab.cli:project_briefing_room_doctor"
    assert scripts["project-briefing-agent-input"] == "devdefender_lab.cli:project_briefing_agent_input"
    assert "project-briefing-room --agent-backend workspace" in readme
    assert "## Release Scope" in readme
    assert "Out of scope for the default package" in readme
    assert "RELEASE_CHECKLIST.md" in readme
    assert "Project Briefing Room Release Checklist" in checklist
    assert "live meeting rooms" in checklist
    assert "Codex owns stakeholder interpretation" in checklist
    assert "bootstrap_runtime.ps1" in readme
    assert "bootstrap_runtime.ps1" in checklist
    assert "https://github.com/PZQ-ship-it/devdefender-lab.git" in readme
    assert "## Current Product Scope" in plan_head
    assert "Not included by default" in plan_head


def test_skill_bootstraps_trusted_runtime_when_missing() -> None:
    skill = Path("skills/project-briefing-room/SKILL.md").read_text(encoding="utf-8")

    assert "If the runtime command or repo scripts are missing" in skill
    assert "bootstrap_runtime.ps1" in skill
    assert "https://github.com/PZQ-ship-it/devdefender-lab.git" in skill
    assert "Do not clone or install runtime code from any other URL unless the user explicitly approves" in skill


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
    assert report["checks"]["bootstrap_runtime_present"] is True
    assert report["checks"]["bootstrap_runtime_trusted_repo"] is True
    assert report["checks"]["required_scripts_present"] is True
    assert report["checks"]["cli_entry_points_present"] is True
    assert report["checks"]["release_checklist_present"] is True
    assert report["checks"]["readme_has_release_scope"] is True
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
