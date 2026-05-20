import json
from pathlib import Path

from scripts.meeting_automation_smoke import build_report, local_meeting_test_url, write_report
from scripts.room_acceptance_smoke import managed_room_report


def test_meeting_automation_report_requires_join_leave_and_cleanup() -> None:
    before = [{"kind": "noise", "source": "existing"}]
    timeline = {
        "events": [
            *before,
            {
                "kind": "meeting_join_started",
                "source": "local-meeting-test",
                "command": "https://meeting.local/devdefender?token=REDACTED",
            },
            {
                "kind": "meeting_joined",
                "source": "local-meeting-test",
                "command": "https://meeting.local/devdefender?token=REDACTED",
            },
            {
                "kind": "meeting_left",
                "source": "local-meeting-test",
                "command": "https://meeting.local/devdefender?token=REDACTED",
            },
        ]
    }

    report = build_report(
        browser_path="browser",
        room_url="http://room.test",
        target_url="http://room.test?auto_meeting=1&meeting_url=https%3A%2F%2Fmeeting.local%2Fdevdefender%3Ftoken%3Dsecret",
        before_events=before,
        timeline=timeline,
        browser_return_code=0,
        used_terminate=False,
        used_kill=False,
        profile_dir=None,
    )

    assert report["ok"] is True
    assert report["new_event_kinds"] == ["meeting_join_started", "meeting_joined", "meeting_left"]
    assert report["checks"]["target_url_redacted"] is True


def test_meeting_automation_report_rejects_wrong_source_and_forbidden_fields() -> None:
    report = build_report(
        browser_path="browser",
        room_url="http://room.test",
        target_url="http://room.test?auto_meeting=1",
        before_events=[],
        timeline={
            "events": [
                {"kind": "meeting_join_started", "source": "local-meeting-test"},
                {"kind": "meeting_joined", "source": "manual", "cookies": "secret"},
                {"kind": "meeting_left", "source": "local-meeting-test"},
            ]
        },
        browser_return_code=0,
        used_terminate=False,
        used_kill=False,
        profile_dir=None,
    )

    assert report["ok"] is False
    assert report["checks"]["meeting_source_used"] is False
    assert report["checks"]["no_forbidden_artifact_fields"] is False


def test_meeting_automation_report_rejects_missing_browser_exit() -> None:
    report = build_report(
        browser_path="browser",
        room_url="http://room.test",
        target_url="http://room.test?auto_meeting=1",
        before_events=[],
        timeline={
            "events": [
                {"kind": "meeting_join_started", "source": "local-meeting-test"},
                {"kind": "meeting_joined", "source": "local-meeting-test"},
                {"kind": "meeting_left", "source": "local-meeting-test"},
            ]
        },
        browser_return_code=None,
        used_terminate=False,
        used_kill=False,
        profile_dir=None,
    )

    assert report["ok"] is False
    assert report["checks"]["browser_process_exited"] is False


def test_local_meeting_test_url_adds_auto_query_and_redacted_seed() -> None:
    url = local_meeting_test_url("http://room.test/path?x=1")

    assert "x=1" in url
    assert "auto_meeting=1" in url
    assert "meeting_url=" in url


def test_meeting_automation_writes_report(tmp_path: Path) -> None:
    report = {"ok": True, "checks": {"meeting_joined_recorded": True}}
    out = tmp_path / "nested" / "meeting_automation_smoke.json"

    write_report(report, out)

    assert json.loads(out.read_text(encoding="utf-8")) == report


def test_meeting_managed_room_report_does_not_include_shutdown_token() -> None:
    report = managed_room_report(
        {
            "pid": 123,
            "room_url": "http://127.0.0.1:8765",
            "repo": "sample_repo",
            "room_port": 8765,
            "slidev_port": 3030,
            "stdout": "out.log",
            "stderr": "err.log",
            "command": ["python", "-m", "devdefender_lab.room"],
            "shutdown_token": "secret-token",
        },
        {"ok": True, "shutdown_request_ok": True},
    )

    assert "shutdown_token" not in report
    assert "secret-token" not in json.dumps(report)
