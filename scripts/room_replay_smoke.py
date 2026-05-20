from __future__ import annotations

import argparse
import json
from pathlib import Path
from datetime import datetime

from devdefender_lab.slide_control import replay_slide_events
from devdefender_lab.timeline import replay_timeline_events, timeline_event_slide_action, timeline_interruption_state


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACT_DIR = ROOT / "artifacts"


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay room slide/timeline JSONL artifacts without a running room.")
    parser.add_argument("--artifact-dir", type=Path, default=DEFAULT_ARTIFACT_DIR, help="Artifact directory to replay.")
    parser.add_argument("--thread-id", help="Optional thread_id filter. Defaults to artifact session.json.")
    args = parser.parse_args()

    report = build_report(args.artifact_dir, args.thread_id)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if not report["ok"]:
        raise SystemExit(1)


def build_report(artifact_dir: Path, thread_id: str | None = None) -> dict[str, object]:
    resolved_thread_id = thread_id or load_session_thread_id(artifact_dir)
    slide_path = artifact_dir / "slide_events.jsonl"
    timeline_path = artifact_dir / "timeline_events.jsonl"
    slides = replay_slide_events(slide_path, thread_id=resolved_thread_id)
    timeline = replay_timeline_events(timeline_path, thread_id=resolved_thread_id)
    interruption = timeline_interruption_state(timeline)
    slide_threads = {event.thread_id for event in slides}
    timeline_threads = {event.thread_id for event in timeline}
    expected_mappings = expected_timeline_slide_mappings(timeline)
    mapped_slide_identities = [_timeline_slide_identity(event) for event in slides if event.source.startswith("timeline:")]
    missing_mappings = _missing_items(expected_mappings, mapped_slide_identities)
    unexpected_mappings = _missing_items(mapped_slide_identities, expected_mappings)
    slide_sequence_violations = slide_replay_violations(slides)
    timeline_slide_pointers = correlate_timeline_to_slides(timeline, slides)
    timeline_pointer_violations = [
        pointer
        for pointer in timeline_slide_pointers
        if not isinstance(pointer.get("slide_index_at_event"), int) or pointer.get("slide_index_at_event", 0) < 1
    ]
    current_slide_index = slides[-1].slide_index if slides else 1
    mapped_slide_count = sum(1 for event in slides if event.source.startswith("timeline:"))
    checks = {
        "slide_log_exists": slide_path.exists(),
        "timeline_log_exists": timeline_path.exists(),
        "slide_events_present": bool(slides),
        "timeline_events_present": bool(timeline),
        "thread_id_resolved": bool(resolved_thread_id),
        "thread_sets_overlap": not slide_threads or not timeline_threads or bool(slide_threads & timeline_threads),
        "timeline_mapped_slides_present": mapped_slide_count > 0,
        "timeline_mapped_event_count_matches": mapped_slide_count == len(expected_mappings),
        "timeline_mappings_match_slide_events": not missing_mappings and not unexpected_mappings,
        "slide_event_sequence_replayable": not slide_sequence_violations,
        "timeline_events_have_slide_pointers": not timeline_pointer_violations,
        "current_slide_index_valid": current_slide_index >= 1,
    }
    return {
        "ok": all(checks.values()),
        "checks": checks,
        "artifact_dir": str(artifact_dir),
        "slide_path": str(slide_path),
        "timeline_path": str(timeline_path),
        "thread_id": resolved_thread_id,
        "thread_id_source": "argument" if thread_id else "session.json" if resolved_thread_id else None,
        "slide_event_count": len(slides),
        "timeline_event_count": len(timeline),
        "mapped_slide_count": mapped_slide_count,
        "current_slide_index": current_slide_index,
        "interruption": interruption.model_dump(),
        "slide_threads": sorted(slide_threads),
        "timeline_threads": sorted(timeline_threads),
        "expected_mappings": expected_mappings,
        "actual_mappings": mapped_slide_identities,
        "missing_mappings": missing_mappings,
        "unexpected_mappings": unexpected_mappings,
        "slide_sequence_violations": slide_sequence_violations,
        "timeline_slide_pointers": timeline_slide_pointers,
        "timeline_pointer_violations": timeline_pointer_violations,
    }


def expected_timeline_slide_mappings(timeline: list[object]) -> list[dict[str, object]]:
    mappings: list[dict[str, object]] = []
    for event in timeline:
        action = timeline_event_slide_action(event)
        if not action:
            continue
        mappings.append(
            {
                "action": action,
                "source": f"timeline:{event.source}",
            }
        )
    return mappings


def slide_replay_violations(slides: list[object]) -> list[dict[str, object]]:
    violations: list[dict[str, object]] = []
    current_slide_index = 1
    for event in slides:
        expected_index = _expected_slide_index(event.action, current_slide_index, event.slide_index)
        if event.slide_index != expected_index:
            violations.append(
                {
                    "timestamp": event.timestamp,
                    "action": event.action,
                    "source": event.source,
                    "expected_slide_index": expected_index,
                    "actual_slide_index": event.slide_index,
                }
            )
        current_slide_index = event.slide_index
    return violations


def correlate_timeline_to_slides(timeline: list[object], slides: list[object]) -> list[dict[str, object]]:
    pointers: list[dict[str, object]] = []
    ordered_slides = sorted(slides, key=lambda event: _timestamp_sort_key(event.timestamp))
    slide_cursor = 0
    current_slide_index = 1
    for event in sorted(timeline, key=lambda item: _timestamp_sort_key(item.timestamp)):
        event_time = _timestamp_sort_key(event.timestamp)
        while slide_cursor < len(ordered_slides) and _timestamp_sort_key(ordered_slides[slide_cursor].timestamp) <= event_time:
            current_slide_index = ordered_slides[slide_cursor].slide_index
            slide_cursor += 1
        pointers.append(
            {
                "timestamp": event.timestamp,
                "kind": event.kind,
                "source": event.source,
                "slide_index_at_event": current_slide_index,
            }
        )
    return pointers


def _expected_slide_index(action: str, current_slide_index: int, requested_slide_index: int | None) -> int:
    if action == "next":
        return current_slide_index + 1
    if action == "prev":
        return max(1, current_slide_index - 1)
    if action == "goto":
        return requested_slide_index or current_slide_index
    return current_slide_index


def _timestamp_sort_key(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _timeline_slide_identity(event) -> dict[str, object]:
    return {
        "action": event.action,
        "source": event.source,
    }


def _missing_items(expected: list[dict[str, object]], actual: list[dict[str, object]]) -> list[dict[str, object]]:
    remaining = [dict(item) for item in actual]
    missing: list[dict[str, object]] = []
    for item in expected:
        if item in remaining:
            remaining.remove(item)
        else:
            missing.append(item)
    return missing


def load_session_thread_id(artifact_dir: Path) -> str | None:
    session_path = artifact_dir / "session.json"
    if not session_path.exists():
        return None
    try:
        session = json.loads(session_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    thread_id = session.get("thread_id")
    return str(thread_id) if thread_id else None


if __name__ == "__main__":
    main()
