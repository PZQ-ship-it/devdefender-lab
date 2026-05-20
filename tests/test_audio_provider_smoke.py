from scripts.audio_provider_smoke import build_report


def test_audio_provider_smoke_report_requires_interruption_contract() -> None:
    report = build_report(
        "mock-audio",
        posted=[
            {"timeline_event": {"kind": "speech_started"}},
            {"timeline_event": {"kind": "noise"}},
            {"timeline_event": {"kind": "tts_word"}, "slide_event": {"action": "next"}},
            {"timeline_event": {"kind": "speech_interrupted"}},
        ],
        baseline_timeline={"interruption": {"active": False, "event_count": 3}},
        timeline={
            "events": [{}, {}, {}, {}],
            "interruption": {
                "active": True,
                "event_count": 4,
                "source": "mock-audio",
                "offset_ms": 2200,
            },
        },
        slides={"current_slide_index": 2, "events": [{}]},
    )

    assert report["ok"] is True
    assert report["checks"]["timeline_interruption_active"] is True
    assert report["interruption"]["source"] == "mock-audio"


def test_audio_provider_smoke_report_fails_without_interruption_state() -> None:
    report = build_report(
        "mock-audio",
        posted=[{"timeline_event": {"kind": "speech_started"}}],
        baseline_timeline={"interruption": {"active": False, "event_count": 0}},
        timeline={"events": [{}], "interruption": {"active": False, "event_count": 0}},
        slides={"current_slide_index": 1, "events": []},
    )

    assert report["ok"] is False
    assert report["checks"]["timeline_interruption_active"] is False
    assert report["checks"]["timeline_interruption_count_incremented"] is False
