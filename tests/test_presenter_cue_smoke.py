import json

from scripts.presenter_cue_smoke import browser_auto_presenter_cue_url, build_report, write_report


def test_presenter_cue_smoke_report_requires_cue_timeline_and_slide_mapping() -> None:
    baseline_timeline = {"events": [{"kind": "noise", "source": "existing"}]}
    baseline_slides = {"current_slide_index": 4, "events": []}
    timeline = {
        "events": [
            *baseline_timeline["events"],
            {"kind": "speech_started", "source": "browser-presenter-cue", "command": "phase2-local-cue"},
            {"kind": "tts_word", "source": "browser-presenter-cue", "token": "next", "offset_ms": 180},
        ]
    }
    slides = {
        "current_slide_index": 5,
        "events": [{"action": "next", "slide_index": 5, "source": "timeline:browser-presenter-cue"}],
    }

    report = build_report("browser", "http://room.test", "http://room.test?auto_presenter_cue=1", baseline_timeline, baseline_slides, timeline, slides)

    assert report["ok"] is True
    assert report["checks"]["speech_started_recorded"] is True
    assert report["checks"]["tts_anchor_recorded"] is True
    assert report["checks"]["mapped_slide_recorded"] is True
    assert report["checks"]["slide_advanced"] is True
    assert report["new_event_kinds"] == ["speech_started", "tts_word"]


def test_presenter_cue_smoke_report_rejects_missing_slide_mapping() -> None:
    report = build_report(
        "browser",
        "http://room.test",
        "http://room.test?auto_presenter_cue=1",
        {"events": []},
        {"current_slide_index": 1, "events": []},
        {
            "events": [
                {"kind": "speech_started", "source": "browser-presenter-cue"},
                {"kind": "tts_word", "source": "browser-presenter-cue", "token": "next"},
            ]
        },
        {"current_slide_index": 1, "events": []},
    )

    assert report["ok"] is False
    assert report["checks"]["mapped_slide_recorded"] is False
    assert report["checks"]["slide_advanced"] is False


def test_presenter_cue_smoke_report_rejects_transcript_or_audio_fields() -> None:
    report = build_report(
        "browser",
        "http://room.test",
        "http://room.test?auto_presenter_cue=1",
        {"events": []},
        {"current_slide_index": 1, "events": []},
        {
            "events": [
                {"kind": "speech_started", "source": "browser-presenter-cue", "transcript": "full words"},
                {"kind": "tts_word", "source": "browser-presenter-cue", "token": "next"},
            ]
        },
        {"current_slide_index": 2, "events": [{"action": "next", "source": "timeline:browser-presenter-cue"}]},
    )

    assert report["ok"] is False
    assert report["checks"]["no_audio_or_transcript_fields"] is False


def test_presenter_cue_smoke_adds_auto_query_param() -> None:
    assert (
        browser_auto_presenter_cue_url("http://room.test/path?x=1")
        == "http://room.test/path?x=1&auto_presenter_cue=1"
    )


def test_presenter_cue_smoke_writes_report(tmp_path) -> None:
    report = {"ok": True, "checks": {"tts_anchor_recorded": True}}
    out = tmp_path / "nested" / "presenter_cue_smoke.json"

    write_report(report, out)

    assert json.loads(out.read_text(encoding="utf-8")) == report
