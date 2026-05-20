import json

from scripts.evidence_packet_smoke import build_evidence_packet, write_packet


def test_evidence_packet_smoke_builds_structured_pointers_without_raw_text() -> None:
    replay = {
        "ok": True,
        "thread_id": "thread-1",
        "thread_id_source": "session.json",
        "timeline_slide_pointers": [
            {
                "timestamp": "2026-01-01T00:00:00+00:00",
                "kind": "speech_interrupted",
                "source": "judge",
                "slide_index_at_event": 3,
            }
        ],
    }

    packet = build_evidence_packet(replay)

    assert packet["ok"] is True
    assert packet["checks"]["no_raw_audio_or_transcript"] is True
    assert packet["evidence"] == [
        {
            "event_index": 0,
            "timestamp": "2026-01-01T00:00:00+00:00",
            "kind": "speech_interrupted",
            "source": "judge",
            "slide_index": 3,
            "timeline_pointer": "timeline://thread-1#event=0&kind=speech_interrupted",
            "slide_pointer": "slide://thread-1#page=3",
        }
    ]


def test_evidence_packet_smoke_builds_meeting_lifecycle_pointers() -> None:
    replay = {
        "ok": True,
        "thread_id": "thread-1",
        "thread_id_source": "session.json",
        "timeline_slide_pointers": [
            {
                "timestamp": "2026-01-01T00:00:00+00:00",
                "kind": "meeting_joined",
                "source": "local-meeting-test",
                "slide_index_at_event": 1,
            }
        ],
    }

    packet = build_evidence_packet(replay)

    assert packet["ok"] is True
    assert packet["evidence"][0]["timeline_pointer"] == "timeline://thread-1#event=0&kind=meeting_joined"


def test_evidence_packet_smoke_builds_meeting_provisioning_pointers() -> None:
    replay = {
        "ok": True,
        "thread_id": "thread-1",
        "thread_id_source": "session.json",
        "timeline_slide_pointers": [
            {
                "timestamp": "2026-01-01T00:00:00+00:00",
                "kind": "meeting_created",
                "source": "mock-meeting-provisioner",
                "slide_index_at_event": 1,
            }
        ],
    }

    packet = build_evidence_packet(replay)

    assert packet["ok"] is True
    assert packet["evidence"][0]["timeline_pointer"] == "timeline://thread-1#event=0&kind=meeting_created"


def test_evidence_packet_smoke_builds_media_route_pointers() -> None:
    replay = {
        "ok": True,
        "thread_id": "thread-1",
        "thread_id_source": "session.json",
        "timeline_slide_pointers": [
            {
                "timestamp": "2026-01-01T00:00:00+00:00",
                "kind": "media_published",
                "source": "mock-media-router",
                "slide_index_at_event": 1,
            }
        ],
    }

    packet = build_evidence_packet(replay)

    assert packet["ok"] is True
    assert packet["evidence"][0]["timeline_pointer"] == "timeline://thread-1#event=0&kind=media_published"


def test_evidence_packet_smoke_rejects_missing_slide_pointer() -> None:
    packet = build_evidence_packet(
        {
            "ok": True,
            "thread_id": "thread-1",
            "timeline_slide_pointers": [
                {
                    "timestamp": "2026-01-01T00:00:00+00:00",
                    "kind": "speech_interrupted",
                    "source": "judge",
                    "slide_index_at_event": None,
                }
            ],
        }
    )

    assert packet["ok"] is False
    assert packet["checks"]["all_events_have_slide_pointer"] is False


def test_evidence_packet_smoke_rejects_failed_replay() -> None:
    packet = build_evidence_packet(
        {
            "ok": False,
            "thread_id": "thread-1",
            "timeline_slide_pointers": [
                {
                    "timestamp": "2026-01-01T00:00:00+00:00",
                    "kind": "speech_interrupted",
                    "source": "judge",
                    "slide_index_at_event": 1,
                }
            ],
        }
    )

    assert packet["ok"] is False
    assert packet["checks"]["replay_ok"] is False


def test_evidence_packet_smoke_writes_packet(tmp_path) -> None:
    packet = {"ok": True, "evidence": [{"slide_pointer": "slide://thread#page=1"}]}
    out = tmp_path / "nested" / "evidence_packet.json"

    write_packet(packet, out)

    assert json.loads(out.read_text(encoding="utf-8")) == packet
