import json
from pathlib import Path

from scripts.media_route_smoke import build_report, write_report


def test_media_route_report_requires_required_events() -> None:
    before = [{"kind": "manual_voice_command", "source": "existing"}]
    timeline = {
        "events": [
            *before,
            {"kind": "virtual_audio_ready", "source": "mock-media-router", "command": "deterministic-audio"},
            {"kind": "virtual_video_ready", "source": "mock-media-router", "command": "slidev-canvas"},
            {"kind": "media_published", "source": "mock-media-router", "command": "local-test-target"},
        ]
    }

    report = build_report(room_url="http://room.test", before_events=before, timeline=timeline)

    assert report["ok"] is True
    assert report["new_event_kinds"] == ["virtual_audio_ready", "virtual_video_ready", "media_published"]
    assert report["checks"]["no_forbidden_artifact_fields"] is True


def test_media_route_report_rejects_wrong_source_and_forbidden_fields() -> None:
    report = build_report(
        room_url="http://room.test",
        before_events=[],
        timeline={
            "events": [
                {"kind": "virtual_audio_ready", "source": "mock-media-router"},
                {"kind": "virtual_video_ready", "source": "manual", "audio_path": "raw.wav"},
                {"kind": "media_published", "source": "mock-media-router"},
            ]
        },
    )

    assert report["ok"] is False
    assert report["checks"]["media_source_used"] is False
    assert report["checks"]["no_forbidden_artifact_fields"] is False


def test_media_route_report_rejects_media_route_error() -> None:
    report = build_report(
        room_url="http://room.test",
        before_events=[],
        timeline={
            "events": [
                {"kind": "virtual_audio_ready", "source": "mock-media-router"},
                {"kind": "virtual_video_ready", "source": "mock-media-router"},
                {"kind": "media_published", "source": "mock-media-router"},
                {"kind": "media_route_error", "source": "mock-media-router"},
            ]
        },
    )

    assert report["ok"] is False
    assert report["checks"]["no_media_route_error"] is False


def test_media_route_writes_report(tmp_path: Path) -> None:
    report = {"ok": True, "checks": {"media_published_recorded": True}}
    out = tmp_path / "nested" / "media_route_smoke.json"

    write_report(report, out)

    assert json.loads(out.read_text(encoding="utf-8")) == report
