from __future__ import annotations

import json
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


DEFAULT_EVIDENCE_POINTER_BUDGET = 24

EVIDENCE_KIND_PRIORITY = {
    "speech_interrupted": 0,
    "audio_track_published": 1,
    "livekit_connected": 2,
    "livekit_error": 3,
    "tts_word": 4,
    "manual_voice_command": 5,
    "livekit_disconnected": 6,
    "speech_started": 7,
    "noise": 8,
}

SAFE_THREAD_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
SAFE_TIMELINE_KINDS = set(EVIDENCE_KIND_PRIORITY)


def load_evidence_packet_pointers(
    artifact_dir: Path,
    max_pointers: int = DEFAULT_EVIDENCE_POINTER_BUDGET,
) -> list[str]:
    return build_evidence_selection(artifact_dir, max_pointers=max_pointers)["selected_pointers"]


def build_evidence_selection(
    artifact_dir: Path,
    max_pointers: int = DEFAULT_EVIDENCE_POINTER_BUDGET,
) -> dict[str, Any]:
    packet_path = artifact_dir / "evidence_packet.json"
    if not packet_path.exists():
        return _empty_selection(max_pointers, "missing_packet")
    try:
        packet = json.loads(packet_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _empty_selection(max_pointers, "invalid_packet_json")
    if not isinstance(packet, dict):
        return _empty_selection(max_pointers, "invalid_packet_shape")
    if packet.get("ok") is not True:
        return _empty_selection(max_pointers, "packet_not_ok")
    checks = packet.get("checks")
    if not isinstance(checks, dict) or checks.get("no_raw_audio_or_transcript") is not True:
        return _empty_selection(max_pointers, "raw_audio_or_transcript_check_failed")

    evidence = packet.get("evidence")
    if not isinstance(evidence, list) or not all(isinstance(item, dict) for item in evidence):
        return _empty_selection(max_pointers, "invalid_evidence_shape")
    if any(_evidence_item_has_raw_payload(item) for item in evidence):
        return _empty_selection(max_pointers, "raw_payload_detected")

    selected_pointers = select_evidence_pointers(evidence, max_pointers=max_pointers)
    all_safe_pointers = _all_safe_pointers(evidence)
    selected_pointer_set = set(selected_pointers)
    omitted_pointers = [pointer for pointer in all_safe_pointers if pointer not in selected_pointer_set]
    return {
        "ok": bool(selected_pointers),
        "reason": "ok" if selected_pointers else "no_safe_pointers_selected",
        "budget": max_pointers,
        "packet_evidence_count": len(evidence),
        "safe_pointer_count": len(all_safe_pointers),
        "selected_pointer_count": len(selected_pointers),
        "omitted_pointer_count": len(omitted_pointers),
        "selected_pointers": selected_pointers,
        "omitted_pointers": omitted_pointers,
    }


def select_evidence_pointers(
    evidence: list[dict[str, Any]],
    max_pointers: int = DEFAULT_EVIDENCE_POINTER_BUDGET,
) -> list[str]:
    if max_pointers <= 0:
        return []
    selected_indexes = _select_evidence_indexes(evidence, max_pointers)
    pointers: list[str] = []
    for index, item in enumerate(evidence):
        if index not in selected_indexes:
            continue
        pointers.extend(_safe_evidence_pointer(value) for value in (item.get("timeline_pointer"), item.get("slide_pointer")))
    return dedupe_strings(pointer for pointer in pointers if pointer)[:max_pointers]


def dedupe_strings(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value or value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _safe_evidence_pointer(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    pointer = value.strip()
    if not is_safe_evidence_pointer(pointer):
        return ""
    return pointer


def is_safe_evidence_pointer(pointer: str) -> bool:
    if not isinstance(pointer, str):
        return False
    if pointer != pointer.strip():
        return False
    lowered = pointer.lower()
    forbidden_fragments = ("data:audio", ".wav", ".mp3", "\\", "..", "transcript://", "audio://")
    if any(fragment in lowered for fragment in forbidden_fragments):
        return False
    parsed = urlparse(pointer)
    if parsed.scheme == "timeline":
        return _is_safe_timeline_pointer(parsed)
    if parsed.scheme == "slide":
        return _is_safe_slide_pointer(parsed)
    return False


def write_evidence_selection(artifact_dir: Path, selection: dict[str, Any] | None = None) -> Path:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    payload = selection if selection is not None else build_evidence_selection(artifact_dir)
    path = artifact_dir / "evidence_selection.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def _empty_selection(max_pointers: int, reason: str) -> dict[str, Any]:
    return {
        "ok": False,
        "reason": reason,
        "budget": max_pointers,
        "packet_evidence_count": 0,
        "safe_pointer_count": 0,
        "selected_pointer_count": 0,
        "omitted_pointer_count": 0,
        "selected_pointers": [],
        "omitted_pointers": [],
    }


def _all_safe_pointers(evidence: list[dict[str, Any]]) -> list[str]:
    pointers: list[str] = []
    for item in evidence:
        pointers.extend(_safe_evidence_pointer(value) for value in (item.get("timeline_pointer"), item.get("slide_pointer")))
    return dedupe_strings(pointer for pointer in pointers if pointer)


def _select_evidence_indexes(evidence: list[dict[str, Any]], max_pointers: int) -> set[int]:
    ranked_indexes = sorted(range(len(evidence)), key=lambda index: _evidence_rank(index, evidence[index]))
    selected_indexes: set[int] = set()
    selected_pointers: set[str] = set()
    for index in ranked_indexes:
        item_pointers = [
            pointer
            for pointer in (
                _safe_evidence_pointer(evidence[index].get("timeline_pointer")),
                _safe_evidence_pointer(evidence[index].get("slide_pointer")),
            )
            if pointer
        ]
        new_pointers = [pointer for pointer in item_pointers if pointer not in selected_pointers]
        if not new_pointers:
            continue
        if selected_pointers and len(selected_pointers) + len(new_pointers) > max_pointers:
            continue
        selected_indexes.add(index)
        selected_pointers.update(new_pointers)
        if len(selected_pointers) >= max_pointers:
            break
    return selected_indexes


def _is_safe_timeline_pointer(parsed) -> bool:
    if not _is_safe_pointer_host(parsed.netloc):
        return False
    if parsed.path not in {"", "/"} or parsed.params or parsed.query:
        return False
    fragment = parse_qs(parsed.fragment, keep_blank_values=True, strict_parsing=True)
    if set(fragment) != {"event", "kind"}:
        return False
    event_values = fragment["event"]
    kind_values = fragment["kind"]
    if len(event_values) != 1 or len(kind_values) != 1:
        return False
    if not event_values[0].isdigit():
        return False
    if int(event_values[0]) < 0:
        return False
    return kind_values[0] in SAFE_TIMELINE_KINDS


def _is_safe_slide_pointer(parsed) -> bool:
    if not _is_safe_pointer_host(parsed.netloc):
        return False
    if parsed.path not in {"", "/"} or parsed.params or parsed.query:
        return False
    fragment = parse_qs(parsed.fragment, keep_blank_values=True, strict_parsing=True)
    if set(fragment) != {"page"}:
        return False
    page_values = fragment["page"]
    if len(page_values) != 1 or not page_values[0].isdigit():
        return False
    return int(page_values[0]) >= 1


def _is_safe_pointer_host(value: str) -> bool:
    return bool(SAFE_THREAD_RE.fullmatch(value))


def _evidence_rank(index: int, item: dict[str, Any]) -> tuple[int, int]:
    kind = item.get("kind")
    priority = EVIDENCE_KIND_PRIORITY.get(kind, 99) if isinstance(kind, str) else 99
    event_index = item.get("event_index")
    if isinstance(event_index, int):
        return (priority, event_index)
    return (priority, index)


def _evidence_item_has_raw_payload(item: dict[str, Any]) -> bool:
    forbidden_keys = {"audio", "audio_path", "audio_url", "raw_audio", "transcript", "text"}
    forbidden_fragments = ("data:audio", ".wav", ".mp3")
    if forbidden_keys & set(item):
        return True
    return any(
        isinstance(value, str) and any(fragment in value.lower() for fragment in forbidden_fragments)
        for value in item.values()
    )
