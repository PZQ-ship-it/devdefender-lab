import json
from pathlib import Path

from scripts.meeting_provisioner_smoke import build_report, local_provisioned_meeting_test_url, write_report


def test_meeting_provisioner_report_requires_creation_join_leave_and_cleanup() -> None:
    before = [{"kind": "manual_voice_command", "source": "existing"}]
    timeline = {
        "thread_id": "thread-1",
        "events": [
            *before,
            {
                "kind": "meeting_created",
                "source": "mock-meeting-provisioner",
                "command": "https://meeting.local/provisioned/abc?join_url=REDACTED&token=REDACTED",
            },
            {
                "kind": "meeting_join_started",
                "source": "local-meeting-test",
                "command": "https://meeting.local/provisioned/abc?join_url=REDACTED&token=REDACTED",
            },
            {
                "kind": "meeting_joined",
                "source": "local-meeting-test",
                "command": "https://meeting.local/provisioned/abc?join_url=REDACTED&token=REDACTED",
            },
            {
                "kind": "meeting_left",
                "source": "local-meeting-test",
                "command": "https://meeting.local/provisioned/abc?join_url=REDACTED&token=REDACTED",
            },
        ],
    }

    report = build_report(
        browser_path="browser",
        room_url="http://room.test",
        target_url=(
            "http://room.test/meeting-test?auto_meeting=1"
            "&meeting_url=https%3A%2F%2Fmeeting.local%2Fprovisioned%2Fabc%3Ftoken%3Dsecret"
        ),
        before_events=before,
        timeline=timeline,
        provisioned_meeting={
            "provider": "mock",
            "meeting_id": "abc",
            "topic": "Defense Session",
            "join_url": "https://meeting.local/provisioned/abc?join_url=REDACTED&token=REDACTED",
            "expires_at": "2026-01-01T00:30:00+00:00",
            "secret_ref": "env:DEVDEFENDER_MEETING_HOST_START_URL:abc",
        },
        teardown_result={"ok": True, "provider": "mock", "meeting_id": "abc"},
        browser_return_code=0,
        used_terminate=False,
        used_kill=False,
        profile_dir=None,
    )

    assert report["ok"] is True
    assert report["new_event_kinds"] == ["meeting_created", "meeting_join_started", "meeting_joined", "meeting_left"]
    assert report["checks"]["meeting_created_recorded"] is True
    assert report["checks"]["meeting_joined_recorded_or_livekit_direct"] is True
    assert report["checks"]["provisioned_meeting_redacted"] is True
    assert report["checks"]["teardown_ok"] is True


def test_meeting_provisioner_report_accepts_livekit_connected_and_published_events() -> None:
    before = [{"kind": "manual_voice_command", "source": "existing"}]
    timeline = {
        "thread_id": "thread-1",
        "events": [
            *before,
            {
                "kind": "meeting_created",
                "source": "livekit-meeting-provisioner",
                "command": "livekit://room/devdefender-abc",
            },
            {
                "kind": "livekit_connected",
                "source": "browser-livekit",
                "command": "devdefender-abc",
            },
            {
                "kind": "audio_track_published",
                "source": "browser-livekit",
                "command": "thread-1-livekit-provisioner",
            },
        ],
    }

    report = build_report(
        browser_path="browser",
        room_url="http://room.test",
        target_url=(
            "http://room.test/?auto_livekit=1&meeting_url=livekit%3A%2F%2Froom%2Fdevdefender-abc"
            "&livekit_room=devdefender-abc&livekit_identity=thread-1-livekit-provisioner"
        ),
        before_events=before,
        timeline=timeline,
        provisioned_meeting={
            "provider": "livekit",
            "meeting_id": "devdefender-abc",
            "topic": "Defense Session",
            "join_url": "livekit://room/devdefender-abc",
            "expires_at": "2026-01-01T00:30:00+00:00",
            "secret_ref": "env:LIVEKIT_API_SECRET:devdefender-abc",
        },
        teardown_result={"ok": True, "provider": "livekit", "meeting_id": "devdefender-abc"},
        browser_return_code=0,
        used_terminate=False,
        used_kill=False,
        profile_dir=None,
    )

    assert report["ok"] is True
    assert report["new_event_kinds"] == ["meeting_created", "livekit_connected", "audio_track_published"]
    assert report["checks"]["meeting_joined_recorded_or_livekit_direct"] is True
    assert report["checks"]["livekit_connected_recorded"] is True
    assert report["checks"]["audio_track_published_recorded"] is True


def test_meeting_provisioner_report_rejects_secret_artifacts() -> None:
    report = build_report(
        browser_path="browser",
        room_url="http://room.test",
        target_url="http://room.test/meeting-test?auto_meeting=1",
        before_events=[],
        timeline={
            "events": [
                {"kind": "meeting_created", "source": "mock-meeting-provisioner"},
                {"kind": "meeting_join_started", "source": "local-meeting-test"},
                {"kind": "meeting_joined", "source": "local-meeting-test"},
                {"kind": "meeting_left", "source": "local-meeting-test"},
            ]
        },
        provisioned_meeting={"provider": "mock", "host_start_url": "https://meeting.local/start?start_token=secret"},
        teardown_result={"ok": True},
        browser_return_code=0,
        used_terminate=False,
        used_kill=False,
        profile_dir=None,
    )

    assert report["ok"] is False
    assert report["checks"]["provisioned_meeting_redacted"] is False
    assert report["checks"]["no_forbidden_artifact_fields"] is False


def test_local_provisioned_meeting_test_url_targets_meeting_fixture() -> None:
    url = local_provisioned_meeting_test_url(
        "http://room.test/root?x=1",
        "https://meeting.local/provisioned/abc?token=secret",
    )

    assert url.startswith("http://room.test/meeting-test?")
    assert "x=1" in url
    assert "auto_meeting=1" in url
    assert "meeting_url=" in url


def test_local_provisioned_meeting_test_url_targets_livekit_room_when_requested() -> None:
    url = local_provisioned_meeting_test_url(
        "http://room.test/root?x=1",
        "livekit://room/devdefender-abc",
        livekit_room="devdefender-abc",
        livekit_identity="identity-1",
    )

    assert url.startswith("http://room.test/?")
    assert "x=1" in url
    assert "auto_livekit=1" in url
    assert "meeting_url=" in url
    assert "livekit_room=devdefender-abc" in url
    assert "livekit_identity=identity-1" in url


def test_meeting_provisioner_writes_report(tmp_path: Path) -> None:
    report = {"ok": True, "checks": {"meeting_created_recorded": True}}
    out = tmp_path / "nested" / "meeting_provisioner_smoke.json"

    write_report(report, out)

    assert json.loads(out.read_text(encoding="utf-8")) == report
