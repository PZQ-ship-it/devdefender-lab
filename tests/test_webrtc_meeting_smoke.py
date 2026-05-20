import json
from pathlib import Path

from scripts.webrtc_meeting_smoke import build_report, local_webrtc_meeting_test_url, write_report


def test_webrtc_meeting_report_requires_meeting_and_media_events() -> None:
    before = [{"kind": "manual_voice_command", "source": "existing"}]
    timeline = {
        "events": [
            *before,
            {"kind": "meeting_join_started", "source": "generic-webrtc-test"},
            {"kind": "virtual_audio_ready", "source": "generic-webrtc-test"},
            {"kind": "virtual_video_ready", "source": "generic-webrtc-test"},
            {"kind": "meeting_joined", "source": "generic-webrtc-test"},
            {"kind": "media_published", "source": "generic-webrtc-test"},
            {"kind": "meeting_left", "source": "generic-webrtc-test"},
        ]
    }

    report = build_report(
        browser_path="browser",
        room_url="http://room.test",
        target_url="http://room.test/webrtc-meeting-test?auto_webrtc_meeting=1&meeting_url=https%3A%2F%2Fwebrtc.local%2Fdevdefender%3Ftoken%3Dsecret",
        before_events=before,
        timeline=timeline,
        browser_return_code=0,
        used_terminate=False,
        used_kill=False,
        profile_dir=None,
    )

    assert report["ok"] is True
    assert report["new_event_kinds"] == [
        "meeting_join_started",
        "virtual_audio_ready",
        "virtual_video_ready",
        "meeting_joined",
        "media_published",
        "meeting_left",
    ]
    assert report["checks"]["target_url_redacted"] is True


def test_webrtc_meeting_report_rejects_errors_and_forbidden_fields() -> None:
    report = build_report(
        browser_path="browser",
        room_url="http://room.test",
        target_url="http://room.test/webrtc-meeting-test?auto_webrtc_meeting=1",
        before_events=[],
        timeline={
            "events": [
                {"kind": "meeting_join_started", "source": "generic-webrtc-test"},
                {"kind": "virtual_audio_ready", "source": "generic-webrtc-test"},
                {"kind": "virtual_video_ready", "source": "manual", "video_path": "raw.webm"},
                {"kind": "meeting_joined", "source": "generic-webrtc-test"},
                {"kind": "media_published", "source": "generic-webrtc-test"},
                {"kind": "meeting_error", "source": "generic-webrtc-test"},
                {"kind": "meeting_left", "source": "generic-webrtc-test"},
            ]
        },
        browser_return_code=0,
        used_terminate=False,
        used_kill=False,
        profile_dir=None,
    )

    assert report["ok"] is False
    assert report["checks"]["webrtc_source_used"] is False
    assert report["checks"]["no_meeting_error"] is False
    assert report["checks"]["no_forbidden_artifact_fields"] is False


def test_webrtc_meeting_url_targets_local_page() -> None:
    url = local_webrtc_meeting_test_url("http://room.test/root?x=1")

    assert url.startswith("http://room.test/webrtc-meeting-test?")
    assert "x=1" in url
    assert "auto_webrtc_meeting=1" in url
    assert "meeting_url=" in url


def test_webrtc_meeting_writes_report(tmp_path: Path) -> None:
    report = {"ok": True, "checks": {"media_published_recorded": True}}
    out = tmp_path / "nested" / "webrtc_meeting_smoke.json"

    write_report(report, out)

    assert json.loads(out.read_text(encoding="utf-8")) == report
