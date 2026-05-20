from scripts.interruption_smoke import build_report


def test_interruption_smoke_report_accepts_matching_replay_state() -> None:
    active_interruption = {
        "active": True,
        "event_count": 2,
        "source": "manual-interrupt",
        "confidence": 1.0,
        "offset_ms": 0,
    }
    handled_interruption = {
        "active": False,
        "event_count": 2,
        "source": "manual-interrupt",
        "confidence": 1.0,
        "offset_ms": 0,
    }

    report = build_report(
        "manual-interrupt",
        1.0,
        0,
        baseline_timeline={"events": [{}], "interruption": {"active": False, "event_count": 1}},
        baseline_slides={"current_slide_index": 4},
        posted={"ok": True, "slide_event": None, "timeline": {"interruption": active_interruption}},
        active_timeline={"events": [{}], "interruption": active_interruption},
        active_session={"timeline": {"interruption": active_interruption}},
        handled={
            "ok": True,
            "slide_event": {"action": "next", "slide_index": 5},
            "timeline": {"interruption": handled_interruption},
        },
        handled_timeline={"events": [{}, {}], "interruption": handled_interruption},
        handled_session={"timeline": {"interruption": handled_interruption}},
        slides={"current_slide_index": 5},
    )

    assert report["ok"] is True
    assert report["active_checks"]["session_matches_replay"] is True
    assert report["handled_checks"]["slide_event_next"] is True
    assert report["handled_checks"]["slide_advanced"] is True
    assert report["active_checks"]["event_count_incremented"] is True
    assert report["expected_interruption_count"] == 2
    assert report["expected_slide_index"] == 5
    assert report["active_interruption"]["source"] == "manual-interrupt"
    assert report["handled_interruption"]["active"] is False


def test_interruption_smoke_report_rejects_missing_active_state() -> None:
    interruption = {
        "active": False,
        "event_count": 0,
        "source": None,
        "confidence": None,
        "offset_ms": None,
    }

    report = build_report(
        "manual-interrupt",
        1.0,
        0,
        baseline_timeline={"events": [], "interruption": {"active": False, "event_count": 0}},
        baseline_slides={"current_slide_index": 1},
        posted={"ok": True, "slide_event": None, "timeline": {"interruption": interruption}},
        active_timeline={"events": [{}], "interruption": interruption},
        active_session={"timeline": {"interruption": interruption}},
        handled={"ok": True, "slide_event": None, "timeline": {"interruption": interruption}},
        handled_timeline={"events": [{}], "interruption": interruption},
        handled_session={"timeline": {"interruption": interruption}},
        slides={"current_slide_index": 1},
    )

    assert report["ok"] is False
    assert report["active_checks"]["replay_interruption_active"] is False
    assert report["active_checks"]["source_matches"] is False
    assert report["handled_checks"]["slide_event_next"] is False
