from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from devdefender_lab.media_router import (  # noqa: E402
    MEDIA_SOURCE,
    contains_forbidden_media_artifact_fields,
    default_mock_media_route_script,
)
from scripts.room_acceptance_smoke import managed_room_report, start_managed_room, stop_managed_room  # noqa: E402


DEFAULT_ROOM_URL = "http://127.0.0.1:8765"
DEFAULT_REPORT_PATH = ROOT / "artifacts" / "media_route_smoke.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Phase 3B deterministic media-route timeline events.")
    parser.add_argument("--room-url", default=DEFAULT_ROOM_URL, help="Running DevDefender room URL.")
    parser.add_argument("--managed-room", action="store_true", help="Start and stop a local mock room for this run.")
    parser.add_argument("--repo", default="sample_repo", help="Repository path used when --managed-room starts a room.")
    parser.add_argument("--slidev-port", type=int, default=3030, help="Slidev port used by --managed-room.")
    parser.add_argument("--startup-timeout", type=float, default=45.0, help="Seconds to wait for a managed room.")
    parser.add_argument("--timeout", type=float, default=15.0, help="Seconds to wait for media route events.")
    parser.add_argument("--out", type=Path, default=DEFAULT_REPORT_PATH, help="Path for the JSON smoke report.")
    args = parser.parse_args()

    managed_room: dict[str, object] | None = None
    try:
        if args.managed_room:
            managed_room = start_managed_room(
                room_url=args.room_url,
                repo=args.repo,
                slidev_port=args.slidev_port,
                startup_timeout=args.startup_timeout,
            )
        report = run_smoke(args.room_url.rstrip("/"), args.out, args.timeout)
    except Exception as exc:
        report = {"ok": False, "error": str(exc)}
    finally:
        if managed_room:
            shutdown = stop_managed_room(managed_room)
            report["managed_room"] = managed_room_report(managed_room, shutdown)
            report["ok"] = bool(report.get("ok")) and bool(shutdown.get("ok"))

    write_report(report, args.out)
    if not report.get("ok"):
        print(json.dumps(report, indent=2, ensure_ascii=False), file=sys.stderr)
        return 1

    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


def run_smoke(room_url: str, out: Path, timeout: float = 15.0) -> dict[str, object]:
    _post_json(
        f"{room_url}/api/timeline-event",
        {
            "kind": "manual_voice_command",
            "command": "goto",
            "slide_index": 1,
            "source": "media-route-smoke",
        },
    )
    before = _get_json(f"{room_url}/api/timeline-events")
    before_events = _events(before)
    for event in default_mock_media_route_script():
        _post_json(f"{room_url}/api/timeline-event", event.model_dump(exclude_none=True))
    timeline = wait_for_media_events(room_url, len(before_events), timeout)
    report = build_report(room_url=room_url, before_events=before_events, timeline=timeline)
    report["report_path"] = str(out)
    write_report(report, out)
    return report


def build_report(
    *,
    room_url: str,
    before_events: list[dict[str, object]],
    timeline: dict[str, object],
) -> dict[str, object]:
    new_events = _events(timeline)[len(before_events) :]
    kinds = [str(event.get("kind")) for event in new_events]
    audio_ready = _last_event(new_events, "virtual_audio_ready")
    video_ready = _last_event(new_events, "virtual_video_ready")
    published = _last_event(new_events, "media_published")
    error = _last_event(new_events, "media_route_error")
    source_ok = all(_event_source(event) == MEDIA_SOURCE for event in new_events if _is_media_event(event))
    checks = {
        "timeline_reachable": bool(timeline),
        "virtual_audio_ready_recorded": audio_ready is not None,
        "virtual_video_ready_recorded": video_ready is not None,
        "media_published_recorded": published is not None,
        "no_media_route_error": error is None,
        "media_source_used": source_ok,
        "no_forbidden_artifact_fields": not contains_forbidden_media_artifact_fields(new_events),
    }
    return {
        "ok": all(checks.values()),
        "checks": checks,
        "room_url": room_url,
        "new_event_count": len(new_events),
        "new_event_kinds": kinds,
        "audio_ready_event": audio_ready,
        "video_ready_event": video_ready,
        "published_event": published,
        "last_media_route_error": error,
    }


def wait_for_media_events(room_url: str, baseline_count: int, timeout: float) -> dict[str, object]:
    deadline = time.monotonic() + timeout
    last_timeline: dict[str, object] = {}
    while time.monotonic() < deadline:
        last_timeline = _get_json(f"{room_url}/api/timeline-events")
        new_events = _events(last_timeline)[baseline_count:]
        if (
            _last_event(new_events, "virtual_audio_ready")
            and _last_event(new_events, "virtual_video_ready")
            and _last_event(new_events, "media_published")
        ):
            return last_timeline
        time.sleep(0.4)
    return last_timeline


def write_report(report: dict[str, object], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _last_event(events: list[dict[str, object]], kind: str) -> dict[str, object] | None:
    for event in reversed(events):
        if event.get("kind") == kind:
            return event
    return None


def _event_source(event: dict[str, object] | None) -> object:
    return event.get("source") if isinstance(event, dict) else None


def _is_media_event(event: dict[str, object]) -> bool:
    return str(event.get("kind")) in {
        "virtual_audio_ready",
        "virtual_video_ready",
        "media_published",
        "media_route_error",
    }


def _events(timeline: dict[str, object]) -> list[dict[str, object]]:
    events = timeline.get("events")
    return events if isinstance(events, list) else []


def _get_json(url: str) -> dict[str, object]:
    with urllib.request.urlopen(url, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


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


if __name__ == "__main__":
    raise SystemExit(main())
