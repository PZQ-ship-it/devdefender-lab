from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACT_DIR = ROOT / "artifacts"
DEFAULT_OUT = DEFAULT_ARTIFACT_DIR / "evidence_packet.json"


if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.room_replay_smoke import build_report  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a replay-derived evidence pointer packet.")
    parser.add_argument("--artifact-dir", type=Path, default=DEFAULT_ARTIFACT_DIR, help="Artifact directory to replay.")
    parser.add_argument("--thread-id", help="Optional thread_id filter. Defaults to artifact session.json.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Path for the evidence packet JSON.")
    args = parser.parse_args()

    replay = build_report(args.artifact_dir, args.thread_id)
    packet = build_evidence_packet(replay)
    write_packet(packet, args.out)
    result = {
        "ok": packet["ok"],
        "checks": packet["checks"],
        "thread_id": packet["thread_id"],
        "evidence_count": len(packet["evidence"]),
        "out": str(args.out),
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if not packet["ok"]:
        raise SystemExit(1)


def build_evidence_packet(replay: dict[str, object]) -> dict[str, object]:
    thread_id = str(replay.get("thread_id") or "")
    timeline_pointers = replay.get("timeline_slide_pointers")
    pointers = timeline_pointers if isinstance(timeline_pointers, list) else []
    evidence = [
        _pointer_to_evidence(thread_id, index, pointer)
        for index, pointer in enumerate(pointers)
        if isinstance(pointer, dict)
    ]
    checks = {
        "replay_ok": replay.get("ok") is True,
        "thread_id_present": bool(thread_id),
        "evidence_present": bool(evidence),
        "all_events_have_slide_pointer": all(isinstance(item.get("slide_index"), int) and item["slide_index"] >= 1 for item in evidence),
        "all_pointers_structured": all(_has_structured_pointers(item) for item in evidence),
        "no_raw_audio_or_transcript": _no_raw_audio_or_transcript(evidence),
    }
    return {
        "ok": all(checks.values()),
        "checks": checks,
        "thread_id": thread_id,
        "thread_id_source": replay.get("thread_id_source"),
        "evidence": evidence,
    }


def write_packet(packet: dict[str, object], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(packet, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _pointer_to_evidence(thread_id: str, index: int, pointer: dict[str, object]) -> dict[str, object]:
    timestamp = str(pointer.get("timestamp") or "")
    kind = str(pointer.get("kind") or "")
    source = str(pointer.get("source") or "")
    slide_index = pointer.get("slide_index_at_event")
    return {
        "event_index": index,
        "timestamp": timestamp,
        "kind": kind,
        "source": source,
        "slide_index": slide_index,
        "timeline_pointer": f"timeline://{thread_id}#event={index}&kind={kind}",
        "slide_pointer": f"slide://{thread_id}#page={slide_index}",
    }


def _has_structured_pointers(item: dict[str, object]) -> bool:
    timeline_pointer = item.get("timeline_pointer")
    slide_pointer = item.get("slide_pointer")
    return (
        isinstance(timeline_pointer, str)
        and timeline_pointer.startswith("timeline://")
        and isinstance(slide_pointer, str)
        and slide_pointer.startswith("slide://")
    )


def _no_raw_audio_or_transcript(evidence: list[dict[str, object]]) -> bool:
    forbidden_keys = {"audio", "audio_path", "audio_url", "raw_audio", "transcript", "text"}
    forbidden_fragments = ("data:audio", ".wav", ".mp3")
    for item in evidence:
        if forbidden_keys & set(item):
            return False
        for value in item.values():
            if isinstance(value, str) and any(fragment in value.lower() for fragment in forbidden_fragments):
                return False
    return True


if __name__ == "__main__":
    main()
