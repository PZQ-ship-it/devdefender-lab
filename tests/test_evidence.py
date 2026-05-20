import json
from pathlib import Path

from devdefender_lab.evidence import (
    build_evidence_selection,
    is_safe_evidence_pointer,
    load_evidence_packet_pointers,
    select_evidence_pointers,
    write_evidence_selection,
)


def test_load_evidence_packet_pointers_accepts_structured_pointers(tmp_path: Path) -> None:
    _write_packet(
        tmp_path,
        ok=True,
        evidence=[
            {
                "timeline_pointer": "timeline://thread-1#event=0&kind=speech_interrupted",
                "slide_pointer": "slide://thread-1#page=3",
            },
            {
                "timeline_pointer": "transcript://thread-1#t=12.3",
                "slide_pointer": "slide://thread-1#page=3",
            },
        ],
    )

    pointers = load_evidence_packet_pointers(tmp_path)

    assert pointers == [
        "timeline://thread-1#event=0&kind=speech_interrupted",
        "slide://thread-1#page=3",
    ]


def test_load_evidence_packet_pointers_fails_closed_on_raw_payload(tmp_path: Path) -> None:
    _write_packet(
        tmp_path,
        ok=True,
        evidence=[
            {
                "timeline_pointer": "timeline://thread-1#event=0&kind=speech_interrupted",
                "slide_pointer": "slide://thread-1#page=3",
                "transcript": "raw spoken text",
            }
        ],
    )

    assert load_evidence_packet_pointers(tmp_path) == []


def test_load_evidence_packet_pointers_ignores_failed_packet(tmp_path: Path) -> None:
    _write_packet(
        tmp_path,
        ok=False,
        evidence=[
            {
                "timeline_pointer": "timeline://thread-1#event=0&kind=speech_interrupted",
                "slide_pointer": "slide://thread-1#page=3",
            }
        ],
    )

    assert load_evidence_packet_pointers(tmp_path) == []


def test_select_evidence_pointers_prioritizes_high_value_events_with_budget() -> None:
    evidence = [
        _item(0, "noise", 2),
        _item(1, "speech_started", 2),
        _item(2, "tts_word", 3),
        _item(3, "speech_interrupted", 4),
        _item(4, "audio_track_published", 4),
        _item(5, "manual_voice_command", 5),
    ]

    pointers = select_evidence_pointers(evidence, max_pointers=6)

    assert pointers == [
        "timeline://thread#event=2&kind=tts_word",
        "slide://thread#page=3",
        "timeline://thread#event=3&kind=speech_interrupted",
        "slide://thread#page=4",
        "timeline://thread#event=4&kind=audio_track_published",
    ]
    assert "timeline://thread#event=3&kind=speech_interrupted" in pointers
    assert "timeline://thread#event=4&kind=audio_track_published" in pointers
    assert all("noise" not in pointer for pointer in pointers)
    assert len(pointers) <= 6


def test_load_evidence_packet_pointers_applies_default_budget(tmp_path: Path) -> None:
    _write_packet(
        tmp_path,
        ok=True,
        evidence=[_item(index, "speech_interrupted", index + 1) for index in range(30)],
    )

    pointers = load_evidence_packet_pointers(tmp_path)

    assert len(pointers) == 24
    assert pointers[0] == "timeline://thread#event=0&kind=speech_interrupted"
    assert pointers[-1] == "slide://thread#page=12"


def test_build_evidence_selection_reports_omitted_pointers(tmp_path: Path) -> None:
    _write_packet(
        tmp_path,
        ok=True,
        evidence=[_item(index, "speech_interrupted", index + 1) for index in range(4)],
    )

    selection = build_evidence_selection(tmp_path, max_pointers=4)

    assert selection["ok"] is True
    assert selection["budget"] == 4
    assert selection["packet_evidence_count"] == 4
    assert selection["safe_pointer_count"] == 8
    assert selection["selected_pointer_count"] == 4
    assert selection["omitted_pointer_count"] == 4
    assert selection["selected_pointers"] == [
        "timeline://thread#event=0&kind=speech_interrupted",
        "slide://thread#page=1",
        "timeline://thread#event=1&kind=speech_interrupted",
        "slide://thread#page=2",
    ]


def test_write_evidence_selection_persists_report(tmp_path: Path) -> None:
    _write_packet(
        tmp_path,
        ok=True,
        evidence=[_item(0, "speech_interrupted", 1)],
    )

    path = write_evidence_selection(tmp_path)

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["selected_pointers"] == [
        "timeline://thread#event=0&kind=speech_interrupted",
        "slide://thread#page=1",
    ]


def test_is_safe_evidence_pointer_enforces_pointer_grammar() -> None:
    valid = [
        "timeline://thread-1#event=0&kind=speech_interrupted",
        "timeline://phase1:fallback_01#kind=audio_track_published&event=23",
        "slide://thread-1#page=3",
    ]
    invalid = [
        "timeline://thread-1#event=-1&kind=speech_interrupted",
        "timeline://thread-1#event=0&kind=unknown",
        "timeline://thread-1#event=0&kind=speech_interrupted&token=secret",
        "timeline://thread-1/path#event=0&kind=speech_interrupted",
        "timeline://../thread#event=0&kind=speech_interrupted",
        "slide://thread-1#page=0",
        "slide://thread-1#page=3&token=secret",
        "slide://thread-1/path#page=3",
        "transcript://thread-1#t=12.3",
        " timeline://thread-1#event=0&kind=speech_interrupted",
    ]

    assert all(is_safe_evidence_pointer(pointer) for pointer in valid)
    assert not any(is_safe_evidence_pointer(pointer) for pointer in invalid)


def test_load_evidence_packet_pointers_filters_invalid_pointer_grammar(tmp_path: Path) -> None:
    _write_packet(
        tmp_path,
        ok=True,
        evidence=[
            {
                "timeline_pointer": "timeline://thread-1#event=0&kind=speech_interrupted&token=secret",
                "slide_pointer": "slide://thread-1#page=3",
            }
        ],
    )

    assert load_evidence_packet_pointers(tmp_path) == ["slide://thread-1#page=3"]


def _write_packet(tmp_path: Path, ok: bool, evidence: list[dict[str, object]]) -> None:
    packet = {
        "ok": ok,
        "checks": {
            "no_raw_audio_or_transcript": True,
        },
        "evidence": evidence,
    }
    (tmp_path / "evidence_packet.json").write_text(json.dumps(packet), encoding="utf-8")


def _item(index: int, kind: str, slide_index: int) -> dict[str, object]:
    return {
        "event_index": index,
        "kind": kind,
        "slide_index": slide_index,
        "timeline_pointer": f"timeline://thread#event={index}&kind={kind}",
        "slide_pointer": f"slide://thread#page={slide_index}",
    }
