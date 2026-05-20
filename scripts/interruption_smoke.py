from __future__ import annotations

import argparse
import json
import urllib.request


DEFAULT_ROOM_URL = "http://127.0.0.1:8765"


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify manual interruption replay state against a running room.")
    parser.add_argument("--room-url", default=DEFAULT_ROOM_URL, help="Running DevDefender room URL.")
    parser.add_argument("--source", default="manual-interrupt", help="Timeline source value for the smoke event.")
    parser.add_argument("--confidence", type=float, default=1.0, help="Confidence value for the smoke event.")
    parser.add_argument("--offset-ms", type=int, default=0, help="Offset value for the smoke event.")
    args = parser.parse_args()

    room_url = args.room_url.rstrip("/")
    baseline_timeline = _get_json(f"{room_url}/api/timeline-events")
    baseline_slides = _get_json(f"{room_url}/api/slide-events")
    posted = _post_json(
        f"{room_url}/api/timeline-event",
        {
            "kind": "speech_interrupted",
            "source": args.source,
            "confidence": args.confidence,
            "offset_ms": args.offset_ms,
        },
    )
    active_timeline = _get_json(f"{room_url}/api/timeline-events")
    active_session = _get_json(f"{room_url}/api/session")
    handled = _post_json(
        f"{room_url}/api/timeline-event",
        {
            "kind": "manual_voice_command",
            "source": "manual-interrupt-smoke",
            "command": "next",
        },
    )
    handled_timeline = _get_json(f"{room_url}/api/timeline-events")
    handled_session = _get_json(f"{room_url}/api/session")
    slides = _get_json(f"{room_url}/api/slide-events")
    report = build_report(
        args.source,
        args.confidence,
        args.offset_ms,
        baseline_timeline,
        baseline_slides,
        posted,
        active_timeline,
        active_session,
        handled,
        handled_timeline,
        handled_session,
        slides,
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if not report["ok"]:
        raise SystemExit(1)


def build_report(
    expected_source: str,
    expected_confidence: float,
    expected_offset_ms: int,
    baseline_timeline: dict[str, object],
    baseline_slides: dict[str, object],
    posted: dict[str, object],
    active_timeline: dict[str, object],
    active_session: dict[str, object],
    handled: dict[str, object],
    handled_timeline: dict[str, object],
    handled_session: dict[str, object],
    slides: dict[str, object],
) -> dict[str, object]:
    baseline_interruption = (
        baseline_timeline.get("interruption") if isinstance(baseline_timeline.get("interruption"), dict) else {}
    )
    posted_timeline = posted.get("timeline") if isinstance(posted.get("timeline"), dict) else {}
    posted_interruption = posted_timeline.get("interruption") if isinstance(posted_timeline, dict) else {}
    active_interruption = (
        active_timeline.get("interruption") if isinstance(active_timeline.get("interruption"), dict) else {}
    )
    active_session_timeline = active_session.get("timeline") if isinstance(active_session.get("timeline"), dict) else {}
    active_session_interruption = (
        active_session_timeline.get("interruption") if isinstance(active_session_timeline, dict) else {}
    )
    handled_timeline_payload = handled.get("timeline") if isinstance(handled.get("timeline"), dict) else {}
    handled_post_interruption = (
        handled_timeline_payload.get("interruption") if isinstance(handled_timeline_payload, dict) else {}
    )
    handled_interruption = (
        handled_timeline.get("interruption") if isinstance(handled_timeline.get("interruption"), dict) else {}
    )
    handled_session_timeline = (
        handled_session.get("timeline") if isinstance(handled_session.get("timeline"), dict) else {}
    )
    handled_session_interruption = (
        handled_session_timeline.get("interruption") if isinstance(handled_session_timeline, dict) else {}
    )
    baseline_count = baseline_interruption.get("event_count")
    active_count = active_interruption.get("event_count")
    expected_count = baseline_count + 1 if isinstance(baseline_count, int) else None
    baseline_slide = baseline_slides.get("current_slide_index")
    expected_slide = baseline_slide + 1 if isinstance(baseline_slide, int) else None

    active_checks = {
        "post_ok": posted.get("ok") is True,
        "no_slide_event": posted.get("slide_event") is None,
        "posted_interruption_active": posted_interruption.get("active") is True,
        "replay_interruption_active": active_interruption.get("active") is True,
        "session_interruption_active": active_session_interruption.get("active") is True,
        "event_count_incremented": active_count == expected_count,
        "source_matches": active_interruption.get("source") == expected_source,
        "confidence_matches": active_interruption.get("confidence") == expected_confidence,
        "offset_matches": active_interruption.get("offset_ms") == expected_offset_ms,
        "session_matches_replay": active_session_interruption == active_interruption,
    }
    handled_checks = {
        "post_ok": handled.get("ok") is True,
        "slide_event_next": _nested_get(handled, "slide_event", "action") == "next",
        "posted_interruption_inactive": handled_post_interruption.get("active") is False,
        "replay_interruption_inactive": handled_interruption.get("active") is False,
        "session_interruption_inactive": handled_session_interruption.get("active") is False,
        "session_matches_replay": handled_session_interruption == handled_interruption,
        "slide_advanced": slides.get("current_slide_index") == expected_slide,
    }
    return {
        "ok": all(active_checks.values()) and all(handled_checks.values()),
        "active_checks": active_checks,
        "handled_checks": handled_checks,
        "active_interruption": active_interruption,
        "handled_interruption": handled_interruption,
        "baseline_interruption_count": baseline_count,
        "expected_interruption_count": expected_count,
        "baseline_slide_index": baseline_slide,
        "expected_slide_index": expected_slide,
        "timeline_event_count": len(handled_timeline.get("events", [])),
        "current_slide_index": slides.get("current_slide_index"),
    }


def _nested_get(payload: dict[str, object], *keys: str) -> object:
    current: object = payload
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _post_json(url: str, payload: dict[str, object]) -> dict[str, object]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def _get_json(url: str) -> dict[str, object]:
    with urllib.request.urlopen(url, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


if __name__ == "__main__":
    main()
