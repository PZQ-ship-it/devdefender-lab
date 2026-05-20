import json
import sys
from pathlib import Path

from scripts.project_briefing_room_smoke import (
    build_briefing_artifacts,
    build_closure_steps,
    build_cross_checks,
    build_livekit_steps,
    build_report,
    run_smoke,
    write_report,
)


def test_project_briefing_room_skip_livekit_generates_artifacts(tmp_path: Path) -> None:
    report = run_smoke(
        room_url="http://127.0.0.1:8765",
        skip_livekit_gates=True,
        artifact_dir=tmp_path,
        tts_out=tmp_path / "tts.json",
        interruption_out=tmp_path / "interruption.json",
        out=tmp_path / "project.json",
    )

    deck_path = tmp_path / "briefing_deck" / "slides.md"
    script_path = tmp_path / "briefing_deck" / "presenter_script.md"
    briefing_report_path = tmp_path / "briefing_deck" / "briefing_report.json"

    assert report["ok"] is True
    assert report["checks"] == {"briefing_artifacts": True}
    assert report["cross_checks"]["livekit_gates_skipped"] is True
    assert report["cross_checks"]["closure_gates_skipped"] is True
    assert report["cross_checks"]["briefing_deck_has_required_sections_ok"] is True
    assert deck_path.exists()
    assert script_path.exists()
    assert briefing_report_path.exists()
    assert "```mermaid" in deck_path.read_text(encoding="utf-8")
    assert "Opening. This briefing is for DevDefender Lab." in script_path.read_text(encoding="utf-8")
    assert json.loads((tmp_path / "project.json").read_text(encoding="utf-8"))["ok"] is True


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


def test_build_livekit_steps_reuses_one_room_url_and_child_reports(tmp_path: Path) -> None:
    steps = build_livekit_steps(
        room_url="http://room.test",
        browser="browser.exe",
        timeout=120,
        tts_timeout=75,
        interruption_timeout=90,
        tts_out=tmp_path / "tts.json",
        interruption_out=tmp_path / "interruption.json",
        skip_livekit_room_create=True,
    )

    assert [step.name for step in steps] == ["livekit_tts", "livekit_interruption"]
    assert steps[0].command == [
        sys.executable,
        str(Path.cwd() / "scripts" / "phase4_livekit_tts_smoke.py"),
        "--room-url",
        "http://room.test",
        "--topic",
        "Project Briefing Room TTS",
        "--timeout",
        "75",
        "--out",
        str(tmp_path / "tts.json"),
        "--browser",
        "browser.exe",
        "--skip-livekit-room-create",
    ]
    assert steps[1].command == [
        sys.executable,
        str(Path.cwd() / "scripts" / "phase4_livekit_interruption_smoke.py"),
        "--room-url",
        "http://room.test",
        "--topic",
        "Project Briefing Room interruption",
        "--timeout",
        "90",
        "--out",
        str(tmp_path / "interruption.json"),
        "--browser",
        "browser.exe",
        "--skip-livekit-room-create",
    ]
    assert steps[0].timeout == 120
    assert steps[1].timeout == 120


def test_project_briefing_report_requires_livekit_children_when_not_skipped(tmp_path: Path) -> None:
    briefing = build_briefing_artifacts(agent_backend="mock", artifact_dir=tmp_path)
    report = build_report(
        [briefing],
        ["briefing_artifacts", "livekit_tts", "livekit_interruption", "room_replay", "evidence_packet", "artifact_secret"],
        skip_livekit_gates=False,
    )

    assert report["ok"] is False
    assert report["checks"]["briefing_artifacts"] is True
    assert report["checks"]["livekit_tts"] is False
    assert report["checks"]["room_replay"] is False
    assert report["cross_checks"]["livekit_tts_ok"] is False
    assert report["cross_checks"]["room_replay_ok"] is False


def test_project_briefing_report_accepts_successful_child_summaries(tmp_path: Path) -> None:
    briefing = build_briefing_artifacts(agent_backend="mock", artifact_dir=tmp_path)
    results = [
        briefing,
        {
            "name": "livekit_tts",
            "ok": True,
            "return_code": 0,
            "report_path": str(tmp_path / "tts.json"),
            "payload": {"ok": True, "checks": {"livekit": True}, "new_event_kinds": ["meeting_created"]},
        },
        {
            "name": "livekit_interruption",
            "ok": True,
            "return_code": 0,
            "report_path": str(tmp_path / "interruption.json"),
            "payload": {"ok": True, "checks": {"interruption": True}, "new_event_kinds": ["speech_interrupted"]},
        },
        {
            "name": "room_replay",
            "ok": True,
            "return_code": 0,
            "report_path": str(tmp_path / "replay.json"),
            "payload": {"ok": True, "thread_id": "thread-1", "timeline_event_count": 12, "slide_event_count": 2},
        },
        {
            "name": "evidence_packet",
            "ok": True,
            "return_code": 0,
            "report_path": str(tmp_path / "evidence.json"),
            "payload": {
                "ok": True,
                "thread_id": "thread-1",
                "evidence": [
                    {"kind": "meeting_created"},
                    {"kind": "livekit_connected"},
                    {"kind": "tts_audio_track_published"},
                    {"kind": "speech_interrupted"},
                ],
            },
        },
        {
            "name": "artifact_secret",
            "ok": True,
            "return_code": 0,
            "report_path": str(tmp_path / "secret.json"),
            "payload": {"ok": True, "findings": [], "scanned_file_count": 10},
        },
    ]

    report = build_report(
        results,
        ["briefing_artifacts", "livekit_tts", "livekit_interruption", "room_replay", "evidence_packet", "artifact_secret"],
    )

    assert report["ok"] is True
    assert report["cross_checks"]["livekit_tts_ok"] is True
    assert report["cross_checks"]["livekit_interruption_ok"] is True
    assert report["cross_checks"]["room_replay_ok"] is True
    assert report["cross_checks"]["evidence_packet_contains_project_events_ok"] is True
    assert report["cross_checks"]["artifact_secret_findings_clean_ok"] is True
    assert "provisioned_meeting" not in str(report)


def test_project_briefing_cross_checks_reject_forbidden_summary_payload(tmp_path: Path) -> None:
    briefing = build_briefing_artifacts(agent_backend="mock", artifact_dir=tmp_path)
    results = [
        briefing,
        {
            "name": "livekit_tts",
            "ok": True,
            "return_code": 0,
            "payload": {"ok": True, "checks": {"bad": "Bearer abc.def"}},
        },
    ]

    checks = build_cross_checks(results, skip_livekit_gates=True)

    assert checks["no_forbidden_artifact_fields_ok"] is False


def test_build_closure_steps_runs_replay_evidence_and_secret_scan(tmp_path: Path) -> None:
    steps = build_closure_steps(
        artifact_dir=tmp_path,
        timeout=90,
        evidence_packet_out=tmp_path / "evidence.json",
        secret_scan_out=tmp_path / "secret.json",
    )

    assert [step.name for step in steps] == ["room_replay", "evidence_packet", "artifact_secret"]
    assert steps[0].command == [
        sys.executable,
        str(Path.cwd() / "scripts" / "room_replay_smoke.py"),
        "--artifact-dir",
        str(tmp_path),
    ]
    assert steps[1].command == [
        sys.executable,
        str(Path.cwd() / "scripts" / "evidence_packet_smoke.py"),
        "--artifact-dir",
        str(tmp_path),
        "--out",
        str(tmp_path / "evidence.json"),
    ]
    assert steps[2].command == [
        sys.executable,
        str(Path.cwd() / "scripts" / "artifact_secret_smoke.py"),
        "--artifact-dir",
        str(tmp_path),
    ]
    assert steps[0].report_path == tmp_path / "project_briefing_room_replay.stdout.json"
    assert steps[1].report_path == tmp_path / "evidence.json"
    assert steps[2].report_path == tmp_path / "secret.json"


def test_project_briefing_cross_checks_reject_missing_required_evidence_kind(tmp_path: Path) -> None:
    briefing = build_briefing_artifacts(agent_backend="mock", artifact_dir=tmp_path)
    results = [
        briefing,
        {"name": "livekit_tts", "ok": True, "payload": {"ok": True}},
        {"name": "livekit_interruption", "ok": True, "payload": {"ok": True}},
        {"name": "room_replay", "ok": True, "payload": {"ok": True, "thread_id": "thread-1"}},
        {
            "name": "evidence_packet",
            "ok": True,
            "payload": {
                "ok": True,
                "thread_id": "thread-1",
                "evidence": [{"kind": "meeting_created"}, {"kind": "livekit_connected"}],
            },
        },
        {"name": "artifact_secret", "ok": True, "payload": {"ok": True, "findings": []}},
    ]

    checks = build_cross_checks(results, skip_livekit_gates=False, skip_closure_gates=False)

    assert checks["evidence_packet_contains_project_events_ok"] is False


def test_project_briefing_room_writes_report(tmp_path: Path) -> None:
    report = {"ok": True, "checks": {"project_briefing_room": True}}
    out = tmp_path / "nested" / "project.json"

    write_report(report, out)

    assert json.loads(out.read_text(encoding="utf-8")) == report
