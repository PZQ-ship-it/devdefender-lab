import json

from scripts.livekit_browser_smoke import browser_auto_livekit_url, build_report, write_report


def test_livekit_browser_smoke_report_requires_connected_and_published_events() -> None:
    before = [{"kind": "noise", "source": "existing"}]
    timeline = {
        "events": [
            *before,
            {"kind": "livekit_connected", "source": "browser-livekit", "command": "room-1"},
            {"kind": "audio_track_published", "source": "browser-livekit", "command": "identity-1"},
        ]
    }

    report = build_report("browser", "http://room.test", "http://room.test?auto_livekit=1", before, timeline)

    assert report["ok"] is True
    assert report["checks"]["livekit_connected_recorded"] is True
    assert report["checks"]["audio_track_published_recorded"] is True
    assert report["new_event_kinds"] == ["livekit_connected", "audio_track_published"]


def test_livekit_browser_smoke_report_fails_when_error_follows_connect() -> None:
    report = build_report(
        "browser",
        "http://room.test",
        "http://room.test?auto_livekit=1",
        [],
        {
            "events": [
                {"kind": "livekit_connected", "source": "browser-livekit"},
                {"kind": "livekit_error", "source": "browser-livekit"},
            ]
        },
    )

    assert report["ok"] is False
    assert report["checks"]["audio_track_published_recorded"] is False
    assert report["checks"]["no_livekit_error_after_connect"] is False


def test_livekit_browser_smoke_adds_auto_query_param() -> None:
    assert browser_auto_livekit_url("http://room.test/path?x=1") == "http://room.test/path?x=1&auto_livekit=1"


def test_livekit_browser_smoke_can_target_specific_room_and_identity() -> None:
    assert browser_auto_livekit_url(
        "http://room.test/path?x=1",
        livekit_room="devdefender-abc",
        livekit_identity="identity-1",
    ) == "http://room.test/path?x=1&auto_livekit=1&livekit_room=devdefender-abc&livekit_identity=identity-1"


def test_livekit_browser_smoke_writes_report(tmp_path) -> None:
    report = {"ok": True, "checks": {"livekit_connected_recorded": True}}
    out = tmp_path / "nested" / "livekit_browser_smoke.json"

    write_report(report, out)

    assert json.loads(out.read_text(encoding="utf-8")) == report
