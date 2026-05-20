import json
from pathlib import Path

from scripts.phase4_livekit_tts_smoke import build_report, browser_auto_livekit_tts_url, write_report


def test_phase4_livekit_tts_report_requires_generated_track_publish_and_slide_anchor() -> None:
    baseline_timeline = {"events": [{"kind": "noise", "source": "existing"}]}
    baseline_slides = {"current_slide_index": 1, "events": []}
    timeline = {
        "events": [
            *baseline_timeline["events"],
            {"kind": "meeting_created", "source": "livekit-meeting-provisioner", "command": "livekit://room/room-1"},
            {"kind": "livekit_connected", "source": "browser-livekit-tts", "command": "room-1"},
            {
                "kind": "tts_audio_track_created",
                "source": "browser-livekit-tts",
                "command": "web-audio-media-stream",
            },
            {"kind": "tts_audio_track_published", "source": "browser-livekit-tts", "command": "identity-1"},
            {"kind": "speech_started", "source": "browser-livekit-tts", "command": "opening"},
            {"kind": "tts_word", "source": "browser-livekit-tts", "token": "next", "offset_ms": 260},
        ]
    }
    slides = {
        "current_slide_index": 2,
        "events": [{"action": "next", "slide_index": 2, "source": "timeline:browser-livekit-tts"}],
    }

    report = build_report(
        browser_path="browser",
        room_url="http://room.test",
        target_url="http://room.test/livekit-tts-test?auto_livekit_tts=1",
        baseline_timeline=baseline_timeline,
        baseline_slides=baseline_slides,
        timeline=timeline,
        slides=slides,
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
    assert report["checks"]["meeting_created_recorded"] is True
    assert report["checks"]["livekit_connected_recorded"] is True
    assert report["checks"]["tts_audio_track_created_recorded"] is True
    assert report["checks"]["tts_audio_track_published_recorded"] is True
    assert report["checks"]["speech_started_recorded"] is True
    assert report["checks"]["tts_anchor_recorded"] is True
    assert report["checks"]["slide_advanced_once"] is True


def test_phase4_livekit_tts_report_rejects_raw_audio_or_transcript_fields() -> None:
    report = build_report(
        browser_path="browser",
        room_url="http://room.test",
        target_url="http://room.test/livekit-tts-test?auto_livekit_tts=1",
        baseline_timeline={"events": []},
        baseline_slides={"current_slide_index": 1, "events": []},
        timeline={
            "events": [
                {"kind": "meeting_created", "source": "livekit-meeting-provisioner"},
                {"kind": "livekit_connected", "source": "browser-livekit-tts"},
                {"kind": "tts_audio_track_created", "source": "browser-livekit-tts", "audio_path": "raw.wav"},
                {"kind": "tts_audio_track_published", "source": "browser-livekit-tts"},
                {"kind": "tts_word", "source": "browser-livekit-tts", "token": "next"},
            ]
        },
        slides={"current_slide_index": 2, "events": [{"source": "timeline:browser-livekit-tts"}]},
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


def test_phase4_livekit_tts_url_targets_test_page_and_identity() -> None:
    assert (
        browser_auto_livekit_tts_url(
            "http://room.test/root?x=1",
            livekit_room="devdefender-abc",
            livekit_identity="identity-1",
        )
        == "http://room.test/livekit-tts-test?x=1&auto_livekit_tts=1&livekit_room=devdefender-abc&livekit_identity=identity-1"
    )


def test_phase4_livekit_tts_writes_report(tmp_path: Path) -> None:
    report = {"ok": True, "checks": {"livekit_tts": True}}
    out = tmp_path / "nested" / "phase4_livekit_tts.json"

    write_report(report, out)

    assert json.loads(out.read_text(encoding="utf-8")) == report
