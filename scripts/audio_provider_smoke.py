from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from devdefender_lab.audio_provider import MockAudioProvider, audio_event_payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Send mock audio provider events to the DevDefender timeline API.")
    parser.add_argument("--room-url", default="http://127.0.0.1:8765", help="Running DevDefender room URL.")
    args = parser.parse_args()

    baseline = _get_json(f"{args.room_url.rstrip('/')}/api/timeline-events")
    provider = MockAudioProvider()
    provider.start_session()
    posted: list[dict[str, object]] = []
    try:
        while True:
            event = provider.emit_timeline_event()
            if event is None:
                break
            response = _post_json(f"{args.room_url.rstrip('/')}/api/timeline-event", audio_event_payload(event))
            posted.append(response)
    finally:
        provider.stop_session()

    timeline = _get_json(f"{args.room_url.rstrip('/')}/api/timeline-events")
    slides = _get_json(f"{args.room_url.rstrip('/')}/api/slide-events")
    report = build_report(provider.backend, posted, baseline, timeline, slides)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if not report["ok"]:
        raise SystemExit(1)


def build_report(
    provider_backend: str,
    posted: list[dict[str, object]],
    baseline_timeline: dict[str, object],
    timeline: dict[str, object],
    slides: dict[str, object],
) -> dict[str, object]:
    baseline_interruption = (
        baseline_timeline.get("interruption") if isinstance(baseline_timeline.get("interruption"), dict) else {}
    )
    interruption = timeline.get("interruption") or {}
    baseline_count = baseline_interruption.get("event_count")
    expected_count = baseline_count + 1 if isinstance(baseline_count, int) else None
    checks = {
        "events_posted": len(posted) >= 4,
        "mapped_slide_event": sum(1 for item in posted if item.get("slide_event")) >= 1,
        "timeline_interruption_active": interruption.get("active") is True,
        "timeline_interruption_count_incremented": interruption.get("event_count") == expected_count,
        "timeline_interruption_source": interruption.get("source") == "mock-audio",
        "timeline_interruption_offset": interruption.get("offset_ms") == 2200,
    }
    return {
        "ok": all(checks.values()),
        "provider": provider_backend,
        "checks": checks,
        "events_posted": len(posted),
        "mapped_slide_events": sum(1 for item in posted if item.get("slide_event")),
        "current_slide_index": slides.get("current_slide_index"),
        "timeline_event_count": len(timeline.get("events", [])),
        "slide_event_count": len(slides.get("events", [])),
        "baseline_interruption_count": baseline_count,
        "expected_interruption_count": expected_count,
        "interruption": interruption,
    }


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
