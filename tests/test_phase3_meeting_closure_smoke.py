import json
import sys
from pathlib import Path

from scripts.phase3_meeting_closure_smoke import (
    build_cross_checks,
    build_post_room_steps,
    build_report,
    build_room_steps,
    duplicate_evidence_packet,
    write_report,
)


def test_phase3_meeting_closure_room_sequence_uses_one_managed_room(tmp_path: Path) -> None:
    steps = build_room_steps(
        room_url="http://127.0.0.1:9999",
        room_acceptance_out=tmp_path / "room.json",
        meeting_out=tmp_path / "meeting.json",
        media_out=tmp_path / "media.json",
        webrtc_out=tmp_path / "webrtc.json",
        zoom_out=tmp_path / "zoom.json",
        evidence_packet_out=tmp_path / "evidence_packet.json",
        skip_visual=True,
        include_livekit_token=True,
    )

    assert [step.name for step in steps] == [
        "room_acceptance",
        "meeting_automation",
        "media_route",
        "webrtc_meeting",
        "zoom_web_discovery",
        "room_replay",
        "evidence_packet",
    ]
    assert "--managed-room" not in steps[0].command
    assert "--skip-visual" in steps[0].command
    assert "--include-livekit-token" in steps[0].command
    assert steps[1].command == [
        sys.executable,
        str(Path.cwd() / "scripts" / "meeting_automation_smoke.py"),
        "--room-url",
        "http://127.0.0.1:9999",
        "--out",
        str(tmp_path / "meeting.json"),
    ]


def test_phase3_meeting_closure_post_room_sequence_defaults_to_pytest(tmp_path: Path) -> None:
    steps = build_post_room_steps(
        repo="sample_repo",
        agent_backend="openclaude-cli",
        agent_timeout=300,
        evidence_chain_out=tmp_path / "chain.json",
    )

    assert [step.name for step in steps] == ["phase1_e2e", "evidence_chain", "artifact_secret", "pytest"]
    assert steps[0].timeout == 360
    assert steps[0].env == {
        "DEVDEFENDER_LLM_MODE": "mock",
        "DEVDEFENDER_AGENT_BACKEND": "openclaude-cli",
        "DEVDEFENDER_AGENT_TIMEOUT_SECONDS": "300",
    }
    assert steps[-1].command == [sys.executable, "-m", "pytest", "tests", "-q"]


def test_phase3_meeting_closure_post_room_sequence_can_skip_pytest(tmp_path: Path) -> None:
    steps = build_post_room_steps(evidence_chain_out=tmp_path / "chain.json", skip_pytest=True)

    assert [step.name for step in steps] == ["phase1_e2e", "evidence_chain", "artifact_secret"]


def test_phase3_meeting_closure_report_requires_all_meeting_media_sources() -> None:
    packet = _packet()
    results = [
        {"name": "room_acceptance", "ok": True, "payload": {"ok": True}},
        {"name": "meeting_automation", "ok": True, "payload": {"ok": True}},
        {"name": "media_route", "ok": True, "payload": {"ok": True}},
        {"name": "webrtc_meeting", "ok": True, "payload": {"ok": True}},
        {"name": "zoom_web_discovery", "ok": True, "payload": {"ok": True}},
        {"name": "room_replay", "ok": True, "payload": {"ok": True, "thread_id": "thread-1"}},
        {"name": "evidence_packet", "ok": True, "payload": {"ok": True, "thread_id": "thread-1"}},
        {"name": "phase3d_evidence_copy", "ok": True, "payload": {"ok": True, "evidence_count": 15}},
        {
            "name": "phase1_e2e",
            "ok": True,
            "payload": {
                "issue": {"evidence": ["timeline://thread-1#event=4&kind=meeting_joined"]},
                "refinement": {"status": "verified"},
            },
        },
        {
            "name": "evidence_chain",
            "ok": True,
            "payload": {
                "expected_pointers": [
                    "timeline://thread-1#event=4&kind=meeting_joined",
                    "timeline://thread-1#event=8&kind=media_published",
                ],
                "counts": {"expected_pointers": 10},
                "selection": {"selected_pointer_count": 10, "omitted_pointer_count": 20},
            },
        },
        {"name": "artifact_secret", "ok": True, "payload": {"ok": True, "findings": []}},
        {"name": "pytest", "ok": True, "payload": {"ok": True, "summary": "165 passed"}},
    ]
    expected_steps = [str(result["name"]) for result in results]

    report = build_report(
        results,
        expected_steps,
        managed_room={"shutdown": {"ok": True, "used_terminate": False, "used_kill": False, "lingering_ports": []}},
        evidence_packet=packet,
    )

    assert report["ok"] is True
    assert report["cross_checks"]["local_meeting_lifecycle_in_packet_ok"] is True
    assert report["cross_checks"]["media_route_events_in_packet_ok"] is True
    assert report["cross_checks"]["webrtc_events_in_packet_ok"] is True
    assert report["cross_checks"]["zoom_discovery_events_in_packet_ok"] is True
    assert report["evidence_packet"] == {
        "ok": True,
        "thread_id": "thread-1",
        "evidence_count": 15,
        "kinds": [
            "media_published",
            "meeting_join_started",
            "meeting_joined",
            "meeting_left",
            "virtual_audio_ready",
            "virtual_video_ready",
        ],
    }
    assert report["evidence_chain"] == {
        "expected_pointers": 10,
        "selected_pointer_count": 10,
        "omitted_pointer_count": 20,
    }


def test_phase3_meeting_closure_cross_checks_reject_missing_zoom_source() -> None:
    packet = _packet()
    packet["evidence"] = [
        item for item in packet["evidence"] if not (isinstance(item, dict) and item.get("source") == "zoom-web-discovery")
    ]

    checks = build_cross_checks(
        [
            {"name": "room_replay", "payload": {"thread_id": "thread-1"}},
            {"name": "evidence_packet", "payload": {"thread_id": "thread-1"}},
            {"name": "artifact_secret", "payload": {"findings": []}},
        ],
        managed_room={"shutdown": {"ok": True, "used_terminate": False, "used_kill": False, "lingering_ports": []}},
        evidence_packet=packet,
    )

    assert checks["zoom_discovery_events_in_packet_ok"] is False


def test_phase3_meeting_closure_duplicates_evidence_packet(tmp_path: Path) -> None:
    source = tmp_path / "evidence_packet.json"
    destination = tmp_path / "nested" / "evidence_packet_phase3d.json"
    source.write_text(json.dumps({"ok": True, "evidence": [{"kind": "meeting_joined"}]}), encoding="utf-8")

    result = duplicate_evidence_packet(source, destination)

    assert result["ok"] is True
    assert result["payload"]["evidence_count"] == 1
    assert json.loads(destination.read_text(encoding="utf-8")) == {"ok": True, "evidence": [{"kind": "meeting_joined"}]}


def test_phase3_meeting_closure_writes_report(tmp_path: Path) -> None:
    report = {"ok": True, "checks": {"phase3d": True}}
    out = tmp_path / "nested" / "phase3.json"

    write_report(report, out)

    assert json.loads(out.read_text(encoding="utf-8")) == report


def _packet() -> dict[str, object]:
    events = [
        ("local-meeting-test", "meeting_join_started"),
        ("local-meeting-test", "meeting_joined"),
        ("local-meeting-test", "meeting_left"),
        ("mock-media-router", "virtual_audio_ready"),
        ("mock-media-router", "virtual_video_ready"),
        ("mock-media-router", "media_published"),
        ("generic-webrtc-test", "meeting_join_started"),
        ("generic-webrtc-test", "virtual_audio_ready"),
        ("generic-webrtc-test", "virtual_video_ready"),
        ("generic-webrtc-test", "meeting_joined"),
        ("generic-webrtc-test", "media_published"),
        ("generic-webrtc-test", "meeting_left"),
        ("zoom-web-discovery", "meeting_join_started"),
        ("zoom-web-discovery", "meeting_joined"),
        ("zoom-web-discovery", "meeting_left"),
    ]
    return {
        "ok": True,
        "thread_id": "thread-1",
        "evidence": [
            {
                "event_index": index,
                "kind": kind,
                "source": source,
                "timeline_pointer": f"timeline://thread-1#event={index}&kind={kind}",
                "slide_pointer": "slide://thread-1#page=1",
            }
            for index, (source, kind) in enumerate(events)
        ],
    }
