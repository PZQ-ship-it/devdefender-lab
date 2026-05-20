from scripts.slide_sync_smoke import build_report


def test_slide_sync_smoke_report_accepts_matching_broadcast_and_replay() -> None:
    event = {
        "action": "next",
        "slide_index": 6,
        "source": "slide-sync-smoke",
        "timestamp": "2026-01-01T00:00:00+00:00",
    }

    report = build_report(
        snapshot={"action": "goto", "slide_index": 5, "source": "snapshot"},
        posted={"ok": True, "event": event},
        broadcast=event,
        replay={"current_slide_index": 6, "events": [event]},
    )

    assert report["ok"] is True
    assert report["checks"]["posted_event_advances_snapshot"] is True
    assert report["checks"]["broadcast_matches_posted"] is True
    assert report["checks"]["replay_last_matches_broadcast"] is True
    assert report["expected_next_slide_index"] == 6
    assert report["current_slide_index"] == 6


def test_slide_sync_smoke_report_rejects_mismatched_replay() -> None:
    posted = {"action": "next", "slide_index": 2, "source": "slide-sync-smoke"}
    replayed = {"action": "next", "slide_index": 3, "source": "other"}

    report = build_report(
        snapshot={"action": "goto", "slide_index": 1, "source": "snapshot"},
        posted={"ok": True, "event": posted},
        broadcast=posted,
        replay={"current_slide_index": 3, "events": [replayed]},
    )

    assert report["ok"] is False
    assert report["checks"]["replay_current_matches_broadcast"] is False
    assert report["checks"]["replay_last_matches_broadcast"] is False
