from scripts.tts_anchor_smoke import build_report


def test_tts_anchor_smoke_report_accepts_timeline_to_ws_to_replay_chain() -> None:
    slide_event = {
        "action": "next",
        "slide_index": 5,
        "source": "timeline:tts-anchor-smoke",
        "timestamp": "2026-01-01T00:00:00+00:00",
    }
    timeline_event = {
        "kind": "tts_word",
        "source": "tts-anchor-smoke",
        "token": "next",
        "offset_ms": 1250,
    }

    report = build_report(
        snapshot={"action": "goto", "slide_index": 4, "source": "snapshot"},
        posted={"ok": True, "timeline_event": timeline_event, "slide_event": slide_event},
        broadcast=slide_event,
        replay={"current_slide_index": 5, "events": [slide_event]},
        baseline_timeline={"events": [{"kind": "speech_started"}]},
        timeline={"events": [{"kind": "speech_started"}, timeline_event]},
    )

    assert report["ok"] is True
    assert report["checks"]["broadcast_matches_slide_event"] is True
    assert report["checks"]["timeline_replay_contains_new_anchor"] is True
    assert report["expected_next_slide_index"] == 5


def test_tts_anchor_smoke_report_rejects_missing_broadcast_match() -> None:
    report = build_report(
        snapshot={"action": "goto", "slide_index": 2, "source": "snapshot"},
        posted={
            "ok": True,
            "timeline_event": {"kind": "tts_word", "source": "tts-anchor-smoke", "token": "next", "offset_ms": 1250},
            "slide_event": {"action": "next", "slide_index": 3, "source": "timeline:tts-anchor-smoke"},
        },
        broadcast={"action": "next", "slide_index": 4, "source": "other"},
        replay={"current_slide_index": 4, "events": [{"action": "next", "slide_index": 4, "source": "other"}]},
        baseline_timeline={"events": []},
        timeline={"events": [{"kind": "tts_word", "source": "tts-anchor-smoke", "token": "next", "offset_ms": 1250}]},
    )

    assert report["ok"] is False
    assert report["checks"]["broadcast_matches_slide_event"] is False
    assert report["checks"]["replay_current_matches_broadcast"] is True
