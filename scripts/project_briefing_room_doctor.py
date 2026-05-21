from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_DIR = ROOT / "artifacts"
DEFAULT_OUT = ARTIFACT_DIR / "project_briefing_room_doctor.json"
DEFAULT_INVOCATION = "Use $project-briefing-room to brief me and update the execution plan from my feedback."

REQUIRED_SCRIPT_NAMES = [
    "agent_briefing_input.py",
    "project_briefing_room.py",
    "project_briefing_room_smoke.py",
    "briefing_feedback_plan.py",
    "apply_briefing_feedback_plan.py",
    "briefing_execution_gate.py",
    "answer_briefing_clarification.py",
]
REQUIRED_ENTRY_POINTS = [
    "project-briefing-room",
    "project-briefing-room-doctor",
    "project-briefing-agent-input",
]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from devdefender_lab.briefing import contains_forbidden_briefing_artifact_fields  # noqa: E402


Runner = Callable[..., subprocess.CompletedProcess[str]]


def main() -> int:
    parser = argparse.ArgumentParser(description="Check that Project Briefing Room is installed and usable.")
    parser.add_argument("--codex-home", type=Path, default=_default_codex_home())
    parser.add_argument("--require-installed-skill", action="store_true")
    parser.add_argument("--skip-quick-smoke", action="store_true")
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    report = build_doctor_report(
        codex_home=args.codex_home,
        require_installed_skill=args.require_installed_skill,
        skip_quick_smoke=args.skip_quick_smoke,
        timeout=args.timeout,
    )
    write_report(report, args.out)
    output = json.dumps(report, indent=2, ensure_ascii=False)
    if not report.get("ok"):
        print(output, file=sys.stderr)
        return 1
    print(output)
    return 0


def build_doctor_report(
    *,
    codex_home: Path | None = None,
    require_installed_skill: bool = False,
    skip_quick_smoke: bool = False,
    timeout: float = 120.0,
    runner: Runner = subprocess.run,
) -> dict[str, object]:
    codex = codex_home or _default_codex_home()
    source_skill = ROOT / "skills" / "project-briefing-room" / "SKILL.md"
    bootstrap_runtime = ROOT / "skills" / "project-briefing-room" / "bootstrap_runtime.ps1"
    installed_skill = codex / "skills" / "project-briefing-room" / "SKILL.md"
    required_scripts = [ROOT / "scripts" / name for name in REQUIRED_SCRIPT_NAMES]
    skill_text = _read_text(source_skill)
    readme_text = _read_text(ROOT / "README.md")
    pyproject_text = _read_text(ROOT / "pyproject.toml")
    release_checklist = ROOT / "RELEASE_CHECKLIST.md"
    quick_smoke = (
        {"ok": True, "skipped": True, "checks": {"quick_smoke_skipped": True}}
        if skip_quick_smoke
        else run_quick_smoke(timeout=timeout, runner=runner)
    )

    checks = {
        "source_skill_present": source_skill.exists(),
        "source_skill_has_product_invocation": DEFAULT_INVOCATION in skill_text,
        "bootstrap_runtime_present": bootstrap_runtime.exists(),
        "bootstrap_runtime_trusted_repo": "https://github.com/PZQ-ship-it/devdefender-lab.git" in _read_text(bootstrap_runtime),
        "required_scripts_present": all(path.exists() for path in required_scripts),
        "cli_entry_points_present": all(name in pyproject_text for name in REQUIRED_ENTRY_POINTS),
        "release_checklist_present": release_checklist.exists(),
        "readme_has_release_scope": "## Release Scope" in readme_text,
        "installed_skill_present": installed_skill.exists(),
        "quick_smoke_ok": bool(quick_smoke.get("ok")),
        "quick_smoke_no_external_room_required": bool(
            quick_smoke.get("skipped") is True
            or _dict(quick_smoke.get("checks")).get("quick_smoke_no_external_room_required")
        ),
        "feedback_plan_generated": bool(
            quick_smoke.get("skipped") is True
            or _dict(quick_smoke.get("checks")).get("feedback_plan_generated")
        ),
        "plan_update_generated": bool(
            quick_smoke.get("skipped") is True
            or _dict(quick_smoke.get("checks")).get("plan_update_generated")
        ),
        "advanced_audit_not_required": bool(
            quick_smoke.get("skipped") is True
            or _dict(quick_smoke.get("checks")).get("advanced_audit_not_required")
        ),
    }
    if not require_installed_skill:
        checks["installed_skill_present"] = True

    report = {
        "schema_version": "1",
        "ok": all(checks.values()),
        "invocation": DEFAULT_INVOCATION,
        "source_skill": _display_path(source_skill),
        "bootstrap_runtime": _display_path(bootstrap_runtime),
        "installed_skill": str(installed_skill),
        "required_scripts": [_display_path(path) for path in required_scripts],
        "required_entry_points": REQUIRED_ENTRY_POINTS,
        "release_checklist": _display_path(release_checklist),
        "quick_smoke": quick_smoke,
        "checks": checks,
    }
    report["checks"]["no_forbidden_artifact_fields"] = not contains_forbidden_briefing_artifact_fields(report)
    report["ok"] = bool(report["ok"] and report["checks"]["no_forbidden_artifact_fields"])
    return report


def run_quick_smoke(*, timeout: float = 120.0, runner: Runner = subprocess.run) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="project-briefing-room-doctor-") as temp_dir:
        temp_root = Path(temp_dir)
        temp_repo = temp_root / "workspace"
        temp_artifacts = temp_root / "artifacts"
        temp_report = temp_root / "project_briefing_room_session.json"
        temp_session = temp_root / "project_briefing_room_session.md"
        temp_repo.mkdir(parents=True, exist_ok=True)
        temp_repo.joinpath("README.md").write_text("# Doctor Workspace\n", encoding="utf-8")
        temp_repo.joinpath("plan.md").write_text("# Doctor Plan\n", encoding="utf-8")
        command = [
            sys.executable,
            str(ROOT / "scripts" / "project_briefing_room.py"),
            "--agent-backend",
            "workspace",
            "--repo",
            str(temp_repo),
            "--artifact-dir",
            str(temp_artifacts),
            "--use-default-clarifications",
            "--session-md",
            str(temp_session),
            "--out",
            str(temp_report),
            "--timeout",
            str(max(30, int(timeout))),
        ]
        try:
            process = runner(
                command,
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                timeout=max(60, int(timeout) + 60),
            )
        except subprocess.TimeoutExpired as exc:
            return {
                "ok": False,
                "skipped": False,
                "return_code": None,
                "command": _display_command(command),
                "error": _safe_text(str(exc)),
                "checks": {
                    "quick_smoke_completed": False,
                    "quick_smoke_no_external_room_required": False,
                    "feedback_plan_generated": False,
                    "plan_update_generated": False,
                    "advanced_audit_not_required": False,
                },
            }

        payload = _load_json(temp_report) or _parse_json(process.stdout)
        checks = {
            "quick_smoke_completed": process.returncode == 0 and bool(payload.get("ok")),
            "quick_smoke_no_external_room_required": payload.get("can_continue") is True,
            "feedback_plan_generated": (temp_artifacts / "briefing_feedback_plan.json").exists(),
            "plan_update_generated": (temp_artifacts / "briefing_plan_update.json").exists(),
            "execution_gate_generated": (temp_artifacts / "briefing_execution_gate.json").exists(),
            "session_markdown_generated": temp_session.exists(),
            "advanced_audit_not_required": True,
            "no_forbidden_artifact_fields": bool(payload)
            and not contains_forbidden_briefing_artifact_fields(payload),
        }
        return {
            "ok": all(checks.values()),
            "skipped": False,
            "return_code": process.returncode,
            "command": _display_command(command),
            "checks": checks,
            "stderr": _safe_text(process.stderr),
        }


def write_report(report: dict[str, object], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _default_codex_home() -> Path:
    return Path.home() / ".codex"


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _load_json(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _parse_json(text: str) -> dict[str, object]:
    value = text.strip()
    if not value:
        return {}
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        start = value.find("{")
        end = value.rfind("}")
        if start < 0 or end < start:
            return {}
        try:
            payload = json.loads(value[start : end + 1])
        except json.JSONDecodeError:
            return {}
    return payload if isinstance(payload, dict) else {}


def _dict(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def _display_command(command: list[str]) -> list[str]:
    display = list(command)
    for index, value in enumerate(display):
        try:
            path = Path(value)
            if path.is_absolute():
                display[index] = _display_path(path)
        except OSError:
            pass
    return display


def _safe_text(text: str) -> str:
    value = " ".join(text.split())
    replacements = {
        "LIVEKIT_API_SECRET": "LIVEKIT_SECRET_ENV",
        "LIVEKIT_API_KEY": "LIVEKIT_KEY_ENV",
        "OPENAI_API_KEY": "OPENAI_KEY_ENV",
    }
    for source, replacement in replacements.items():
        value = value.replace(source, replacement)
    return value[:500]


if __name__ == "__main__":
    raise SystemExit(main())
