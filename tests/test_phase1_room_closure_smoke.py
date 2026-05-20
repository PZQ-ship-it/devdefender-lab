import json
import sys
from pathlib import Path

from scripts.phase1_room_closure_smoke import build_cross_checks, build_report, build_sequence, summarize_results, write_report


def test_phase1_room_closure_sequence_includes_managed_room_and_livekit_flags(tmp_path: Path) -> None:
    room_out = tmp_path / "room.json"
    sequence = build_sequence(
        room_url="http://127.0.0.1:9999",
        repo="sample_repo",
        slidev_port=4040,
        include_livekit_token=True,
        include_livekit_browser=True,
        agent_backend="openclaude-cli",
        agent_timeout=300,
        room_acceptance_out=room_out,
    )

    assert [step.name for step in sequence] == [
        "room_acceptance",
        "phase1_e2e",
        "evidence_chain",
        "artifact_secret",
    ]
    assert sequence[0].command == [
        sys.executable,
        str(Path.cwd() / "scripts" / "room_acceptance_smoke.py"),
        "--managed-room",
        "--room-url",
        "http://127.0.0.1:9999",
        "--repo",
        "sample_repo",
        "--slidev-port",
        "4040",
        "--out",
        str(room_out),
        "--include-livekit-token",
        "--include-livekit-browser",
    ]
    assert sequence[1].timeout == 360
    assert sequence[1].env == {
        "DEVDEFENDER_LLM_MODE": "mock",
        "DEVDEFENDER_AGENT_BACKEND": "openclaude-cli",
        "DEVDEFENDER_AGENT_TIMEOUT_SECONDS": "300",
    }


def test_phase1_room_closure_sequence_defaults_to_mock_agent(tmp_path: Path) -> None:
    sequence = build_sequence(
        room_url="http://127.0.0.1:9999",
        repo="sample_repo",
        slidev_port=4040,
        room_acceptance_out=tmp_path / "room.json",
    )

    assert sequence[1].timeout == 240
    assert sequence[1].env == {
        "DEVDEFENDER_LLM_MODE": "mock",
        "DEVDEFENDER_AGENT_BACKEND": "mock",
        "DEVDEFENDER_AGENT_TIMEOUT_SECONDS": "180",
    }


def test_phase1_room_closure_report_summarizes_success() -> None:
    report = build_report(
        [
            {
                "name": "room_acceptance",
                "ok": True,
                "payload": {
                    "checks": {"livekit_browser": True},
                    "results": [
                        {"name": "room_replay", "payload": {"thread_id": "thread"}},
                        {"name": "evidence_packet", "payload": {"thread_id": "thread"}},
                    ],
                    "managed_room": {
                        "shutdown": {
                            "ok": True,
                            "used_terminate": False,
                            "used_kill": False,
                            "lingering_ports": [],
                        }
                    },
                },
            },
            {
                "name": "phase1_e2e",
                "ok": True,
                "payload": {
                    "issue": {
                        "title": "Issue",
                        "evidence": [
                            "timeline://thread#event=1&kind=livekit_connected",
                            "timeline://thread#event=2&kind=audio_track_published",
                            "slide://thread#page=2",
                        ],
                    },
                    "refinement": {"status": "verified"},
                },
            },
            {
                "name": "evidence_chain",
                "ok": True,
                "payload": {
                    "expected_pointers": [
                        "timeline://thread#event=1&kind=livekit_connected",
                        "timeline://thread#event=2&kind=audio_track_published",
                        "slide://thread#page=2",
                    ],
                    "counts": {"expected_pointers": 18},
                    "selection": {"selected_pointer_count": 18, "omitted_pointer_count": 0},
                },
            },
            {"name": "artifact_secret", "ok": True, "payload": {"ok": True}},
        ],
        ["room_acceptance", "phase1_e2e", "evidence_chain", "artifact_secret"],
    )

    assert report["ok"] is True
    assert report["checks"] == {
        "room_acceptance": True,
        "phase1_e2e": True,
        "evidence_chain": True,
        "artifact_secret": True,
    }
    assert report["cross_checks"] == {
        "managed_room_clean_shutdown_ok": True,
        "livekit_browser_ran": True,
        "livekit_pointers_in_evidence_chain_ok": True,
        "livekit_pointers_in_issue_ok": True,
        "room_replay_and_packet_thread_match_ok": True,
        "evidence_chain_thread_matches_packet_ok": True,
        "issue_evidence_thread_matches_packet_ok": True,
        "artifact_secret_clean_ok": True,
    }
    assert report["results"][0] == {
        "name": "room_acceptance",
        "ok": True,
        "return_code": None,
        "summary": {
            "ok": None,
            "checks": {"livekit_browser": True},
            "managed_shutdown": {
                "ok": True,
                "used_terminate": False,
                "used_kill": False,
                "lingering_ports": [],
            },
        },
    }
    assert report["managed_room_shutdown"] == {
        "ok": True,
        "used_terminate": False,
        "used_kill": False,
        "lingering_ports": [],
    }
    assert report["evidence_chain"] == {
        "expected_pointers": 18,
        "selected_pointer_count": 18,
        "omitted_pointer_count": 0,
    }


def test_phase1_room_closure_report_can_keep_full_results() -> None:
    results = [{"name": "artifact_secret", "ok": True, "return_code": 0, "payload": {"ok": True, "findings": []}}]

    report = build_report(results, ["artifact_secret"], compact=False)

    assert report["ok"] is True
    assert report["results"] == results


def test_phase1_room_closure_cross_checks_require_livekit_evidence_when_browser_ran() -> None:
    cross_checks = build_cross_checks(
        [
            {
                "name": "room_acceptance",
                "payload": {
                    "checks": {"livekit_browser": True},
                    "results": [
                        {"name": "room_replay", "payload": {"thread_id": "thread"}},
                        {"name": "evidence_packet", "payload": {"thread_id": "thread"}},
                    ],
                    "managed_room": {
                        "shutdown": {
                            "ok": True,
                            "used_terminate": False,
                            "used_kill": False,
                            "lingering_ports": [],
                        }
                    },
                },
            },
            {"name": "phase1_e2e", "payload": {"issue": {"evidence": []}}},
            {"name": "evidence_chain", "payload": {"expected_pointers": []}},
            {"name": "artifact_secret", "payload": {"findings": []}},
        ]
    )

    assert cross_checks["livekit_browser_ran"] is True
    assert cross_checks["livekit_pointers_in_evidence_chain_ok"] is False
    assert cross_checks["livekit_pointers_in_issue_ok"] is False


def test_phase1_room_closure_cross_checks_do_not_require_livekit_when_browser_skipped() -> None:
    cross_checks = build_cross_checks(
        [
            {
                "name": "room_acceptance",
                "payload": {
                    "checks": {"livekit_browser": False},
                    "results": [
                        {"name": "room_replay", "payload": {"thread_id": "thread"}},
                        {"name": "evidence_packet", "payload": {"thread_id": "thread"}},
                    ],
                    "managed_room": {
                        "shutdown": {
                            "ok": True,
                            "used_terminate": False,
                            "used_kill": False,
                            "lingering_ports": [],
                        }
                    },
                },
            },
            {"name": "phase1_e2e", "payload": {"issue": {"evidence": []}}},
            {"name": "evidence_chain", "payload": {"expected_pointers": []}},
            {"name": "artifact_secret", "payload": {"findings": []}},
        ]
    )

    assert cross_checks["livekit_browser_ran"] is False
    assert cross_checks["livekit_pointers_in_evidence_chain_ok"] is True
    assert cross_checks["livekit_pointers_in_issue_ok"] is True


def test_phase1_room_closure_cross_checks_reject_mixed_thread_artifacts() -> None:
    cross_checks = build_cross_checks(
        [
            {
                "name": "room_acceptance",
                "payload": {
                    "checks": {"livekit_browser": True},
                    "results": [
                        {"name": "room_replay", "payload": {"thread_id": "fresh-thread"}},
                        {"name": "evidence_packet", "payload": {"thread_id": "fresh-thread"}},
                    ],
                    "managed_room": {
                        "shutdown": {
                            "ok": True,
                            "used_terminate": False,
                            "used_kill": False,
                            "lingering_ports": [],
                        }
                    },
                },
            },
            {
                "name": "phase1_e2e",
                "payload": {"issue": {"evidence": ["timeline://old-thread#event=1&kind=livekit_connected"]}},
            },
            {
                "name": "evidence_chain",
                "payload": {"expected_pointers": ["timeline://fresh-thread#event=1&kind=livekit_connected"]},
            },
            {"name": "artifact_secret", "payload": {"findings": []}},
        ]
    )

    assert cross_checks["room_replay_and_packet_thread_match_ok"] is True
    assert cross_checks["evidence_chain_thread_matches_packet_ok"] is True
    assert cross_checks["issue_evidence_thread_matches_packet_ok"] is False


def test_phase1_room_closure_summarizes_payloads() -> None:
    summaries = summarize_results(
        [
            {
                "name": "phase1_e2e",
                "ok": True,
                "return_code": 0,
                "payload": {
                    "issue": {"title": "Issue", "evidence": ["a", "b"]},
                    "refinement": {"status": "verified", "agent_backend": "mock", "violations": []},
                },
                "stderr": "x" * 600,
            },
            {
                "name": "artifact_secret",
                "ok": True,
                "return_code": 0,
                "payload": {"ok": True, "loaded_secret_count": 3, "scanned_file_count": 20, "findings": []},
                "stderr": "",
            },
        ]
    )

    assert summaries[0]["summary"] == {
        "issue_title": "Issue",
        "issue_evidence_count": 2,
        "refinement_status": "verified",
        "agent_backend": "mock",
        "violations": [],
    }
    assert summaries[0]["stderr_tail"] == "x" * 500
    assert summaries[1]["summary"] == {
        "ok": True,
        "loaded_secret_count": 3,
        "scanned_file_count": 20,
        "finding_count": 0,
    }


def test_phase1_room_closure_report_marks_unrun_steps_false() -> None:
    report = build_report(
        [{"name": "room_acceptance", "ok": False, "payload": {"ok": False}}],
        ["room_acceptance", "phase1_e2e", "evidence_chain", "artifact_secret"],
    )

    assert report["ok"] is False
    assert report["checks"] == {
        "room_acceptance": False,
        "phase1_e2e": False,
        "evidence_chain": False,
        "artifact_secret": False,
    }


def test_phase1_room_closure_writes_report(tmp_path: Path) -> None:
    report = {"ok": True, "checks": {"room_acceptance": True}, "results": []}
    out = tmp_path / "nested" / "closure.json"

    write_report(report, out)

    assert json.loads(out.read_text(encoding="utf-8")) == report
