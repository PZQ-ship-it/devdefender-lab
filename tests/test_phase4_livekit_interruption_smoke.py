import json
from pathlib import Path

from scripts.phase4_livekit_interruption_smoke import (
    browser_auto_livekit_interruption_url,
    build_report,
    write_report,
)


def test_phase4_livekit_interruption_report_requires_remote_audio_interruption() -> None:
    baseline = {"events": [{"kind": "noise", "source": "existing"}]}
    timeline = {
        "interruption": {
            "active": True,
            "source": "browser-livekit-remote-interruption",
            "confidence": 0.91,
            "offset_ms": 160,
        },
        "events": [
            *baseline["events"],
            {"kind": "meeting_created", "source": "livekit-meeting-provisioner", "command": "livekit://room/room-1"},
            {"kind": "livekit_connected", "source": "browser-livekit-interruption-detector", "command": "room-1"},
            {"kind": "livekit_connected", "source": "browser-livekit-reviewer", "command": "room-1"},
            {"kind": "audio_track_published", "source": "browser-livekit-reviewer", "command": "reviewer-1"},
            {
                "kind": "speech_started",
                "source": "browser-livekit-remote-interruption",
                "command": "remote-reviewer-audio",
            },
            {"kind": "speech_interrupted", "source": "browser-livekit-remote-interruption", "confidence": 0.92},
        ],
    }

    report = build_report(
        browser_path="browser",
        room_url="http://room.test",
        target_url="http://room.test/livekit-interruption-test?auto_livekit_interruption=1",
        baseline_timeline=baseline,
        timeline=timeline,
        provisioned_meeting={
            "provider": "livekit",
            "meeting_id": "room-1",
            "topic": "topic",
            "join_url": "livekit://room/room-1",
            "expires_at": "2026-05-21T00:00:00+00:00",
            "secret_ref": "env:LIVEKIT_API_SECRET:room-1",
        },
        teardown_result={"ok": True, "provider": "livekit", "meeting_id": "room-1"},
        browser_return_code=0,
    )

    assert report["ok"] is True
    assert report["checks"]["detector_connected_recorded"] is True
    assert report["checks"]["reviewer_connected_recorded"] is True
    assert report["checks"]["reviewer_audio_track_published"] is True
    assert report["checks"]["remote_speech_started_recorded"] is True
    assert report["checks"]["remote_speech_interrupted_recorded"] is True
    assert report["checks"]["interruption_state_active"] is True


def test_phase4_livekit_interruption_report_rejects_raw_audio_or_transcript_fields() -> None:
    report = build_report(
        browser_path="browser",
        room_url="http://room.test",
        target_url="http://room.test/livekit-interruption-test?auto_livekit_interruption=1",
        baseline_timeline={"events": []},
        timeline={
            "interruption": {"active": True, "source": "browser-livekit-remote-interruption"},
            "events": [
                {"kind": "meeting_created", "source": "livekit-meeting-provisioner"},
                {"kind": "livekit_connected", "source": "browser-livekit-interruption-detector"},
                {"kind": "livekit_connected", "source": "browser-livekit-reviewer"},
                {"kind": "audio_track_published", "source": "browser-livekit-reviewer", "audio_path": "raw.wav"},
                {"kind": "speech_started", "source": "browser-livekit-remote-interruption"},
                {"kind": "speech_interrupted", "source": "browser-livekit-remote-interruption"},
            ],
        },
        provisioned_meeting={
            "provider": "livekit",
            "meeting_id": "room-1",
            "topic": "topic",
            "join_url": "livekit://room/room-1",
            "expires_at": "2026-05-21T00:00:00+00:00",
            "secret_ref": "env:LIVEKIT_API_SECRET:room-1",
        },
        teardown_result={"ok": True, "provider": "livekit", "meeting_id": "room-1"},
        browser_return_code=0,
    )

    assert report["ok"] is False
    assert report["checks"]["no_forbidden_artifact_fields"] is False


def test_phase4_livekit_interruption_url_targets_test_page_and_identities() -> None:
    assert (
        browser_auto_livekit_interruption_url(
            "http://room.test/root?x=1",
            livekit_room="devdefender-abc",
            detector_identity="detector-1",
            reviewer_identity="reviewer-1",
        )
        == "http://room.test/livekit-interruption-test?x=1&auto_livekit_interruption=1&livekit_room=devdefender-abc&detector_identity=detector-1&reviewer_identity=reviewer-1"
    )


def test_phase4_livekit_interruption_writes_report(tmp_path: Path) -> None:
    report = {"ok": True, "checks": {"remote_interruption": True}}
    out = tmp_path / "nested" / "phase4_livekit_interruption.json"

    write_report(report, out)

    assert json.loads(out.read_text(encoding="utf-8")) == report
