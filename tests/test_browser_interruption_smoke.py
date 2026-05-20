import json

from scripts.browser_interruption_smoke import browser_auto_interruption_url, build_report, write_report


def test_browser_interruption_smoke_report_requires_detector_events_and_active_state() -> None:
    before = [{"kind": "noise", "source": "existing"}]
    timeline = {
        "interruption": {
            "active": True,
            "event_count": 1,
            "source": "browser-interruption-detector",
            "confidence": 0.91,
            "offset_ms": 0,
        },
        "events": [
            *before,
            {"kind": "speech_started", "source": "browser-interruption-detector", "confidence": 0.55},
            {"kind": "speech_interrupted", "source": "browser-interruption-detector", "confidence": 0.91},
        ],
    }

    report = build_report("browser", "http://room.test", "http://room.test?auto_interruption=1", before, timeline)

    assert report["ok"] is True
    assert report["checks"]["speech_started_recorded"] is True
    assert report["checks"]["speech_interrupted_recorded"] is True
    assert report["checks"]["interruption_active"] is True
    assert report["new_event_kinds"] == ["speech_started", "speech_interrupted"]


def test_browser_interruption_smoke_report_rejects_wrong_source() -> None:
    report = build_report(
        "browser",
        "http://room.test",
        "http://room.test?auto_interruption=1",
        [],
        {
            "interruption": {"active": True},
            "events": [
                {"kind": "speech_started", "source": "browser-interruption-detector"},
                {"kind": "speech_interrupted", "source": "manual-interrupt"},
            ],
        },
    )

    assert report["ok"] is False
    assert report["checks"]["detector_source_used"] is False


def test_browser_interruption_smoke_report_rejects_audio_artifact_fields() -> None:
    report = build_report(
        "browser",
        "http://room.test",
        "http://room.test?auto_interruption=1",
        [],
        {
            "interruption": {"active": True},
            "events": [
                {"kind": "speech_started", "source": "browser-interruption-detector"},
                {
                    "kind": "speech_interrupted",
                    "source": "browser-interruption-detector",
                    "audio_path": "artifacts/raw.wav",
                },
            ],
        },
    )

    assert report["ok"] is False
    assert report["checks"]["no_audio_artifact_fields"] is False


def test_browser_interruption_smoke_adds_auto_query_param() -> None:
    assert (
        browser_auto_interruption_url("http://room.test/path?x=1")
        == "http://room.test/path?x=1&auto_interruption=1"
    )


def test_browser_interruption_smoke_writes_report(tmp_path) -> None:
    report = {"ok": True, "checks": {"speech_interrupted_recorded": True}}
    out = tmp_path / "nested" / "browser_interruption_smoke.json"

    write_report(report, out)

    assert json.loads(out.read_text(encoding="utf-8")) == report
