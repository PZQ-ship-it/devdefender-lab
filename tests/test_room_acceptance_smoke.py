import json
import sys

from scripts.room_acceptance_smoke import (
    _managed_room_command,
    _parse_json_output,
    _parse_room_url,
    build_report,
    build_sequence,
    managed_room_report,
    write_report,
)


def test_room_acceptance_smoke_report_requires_all_steps_ok() -> None:
    report = build_report(
        [
            {"name": "slide_sync", "ok": True},
            {"name": "tts_anchor", "ok": True},
            {"name": "presenter_cue", "ok": True},
            {"name": "interruption", "ok": True},
            {"name": "browser_interruption", "ok": True},
            {"name": "audio_provider", "ok": True},
            {"name": "visual", "ok": True},
            {"name": "room_replay", "ok": True},
            {"name": "evidence_packet", "ok": True},
            {"name": "artifact_secret", "ok": True},
        ]
    )

    assert report["ok"] is True
    assert report["checks"] == {
        "slide_sync": True,
        "tts_anchor": True,
        "presenter_cue": True,
        "interruption": True,
        "browser_interruption": True,
        "audio_provider": True,
        "visual": True,
        "room_replay": True,
        "evidence_packet": True,
        "artifact_secret": True,
    }


def test_room_acceptance_smoke_report_fails_on_failed_step() -> None:
    report = build_report(
        [
            {"name": "slide_sync", "ok": True},
            {"name": "interruption", "ok": False},
        ]
    )

    assert report["ok"] is False
    assert report["checks"]["interruption"] is False


def test_room_acceptance_sequence_keeps_livekit_token_optional() -> None:
    sequence = build_sequence(room_url="http://room.test", skip_visual=True)

    assert [name for name, _ in sequence] == [
        "slide_sync",
        "tts_anchor",
        "presenter_cue",
        "interruption",
        "browser_interruption",
        "audio_provider",
        "room_replay",
        "evidence_packet",
        "artifact_secret",
    ]


def test_room_acceptance_sequence_can_include_livekit_token_gate() -> None:
    sequence = build_sequence(room_url="http://room.test", include_livekit_token=True)

    assert [name for name, _ in sequence] == [
        "slide_sync",
        "tts_anchor",
        "presenter_cue",
        "interruption",
        "browser_interruption",
        "audio_provider",
        "visual",
        "livekit_token",
        "room_replay",
        "evidence_packet",
        "artifact_secret",
    ]
    assert sequence[-4][1] == ["livekit_token_smoke.py", "--room-url", "http://room.test"]
    assert sequence[-3][1] == ["room_replay_smoke.py"]
    assert sequence[-2][1] == ["evidence_packet_smoke.py"]
    assert sequence[-1][1] == ["artifact_secret_smoke.py"]


def test_room_acceptance_sequence_can_include_livekit_browser_gate() -> None:
    sequence = build_sequence(room_url="http://room.test", include_livekit_browser=True)

    assert [name for name, _ in sequence] == [
        "slide_sync",
        "tts_anchor",
        "presenter_cue",
        "interruption",
        "browser_interruption",
        "audio_provider",
        "visual",
        "livekit_browser",
        "room_replay",
        "evidence_packet",
        "artifact_secret",
    ]
    assert sequence[-4][1] == ["livekit_browser_smoke.py", "--room-url", "http://room.test"]
    assert sequence[-3][1] == ["room_replay_smoke.py"]
    assert sequence[-2][1] == ["evidence_packet_smoke.py"]
    assert sequence[-1][1] == ["artifact_secret_smoke.py"]


def test_room_acceptance_sequence_can_include_evidence_chain_gate() -> None:
    sequence = build_sequence(room_url="http://room.test", skip_visual=True, include_evidence_chain=True)

    assert [name for name, _ in sequence] == [
        "slide_sync",
        "tts_anchor",
        "presenter_cue",
        "interruption",
        "browser_interruption",
        "audio_provider",
        "room_replay",
        "evidence_packet",
        "evidence_chain",
        "artifact_secret",
    ]
    assert sequence[-3][1] == ["evidence_packet_smoke.py"]
    assert sequence[-2][1] == ["evidence_chain_smoke.py"]


def test_room_acceptance_smoke_parses_json_from_noisy_stdout() -> None:
    assert _parse_json_output('log line\n{"ok": true, "value": 2}\n') == {"ok": True, "value": 2}


def test_room_acceptance_smoke_writes_report(tmp_path) -> None:
    report = {"ok": True, "checks": {"slide_sync": True}, "results": []}
    out = tmp_path / "nested" / "room_acceptance_smoke.json"

    write_report(report, out)

    assert json.loads(out.read_text(encoding="utf-8")) == report


def test_room_acceptance_managed_room_command_uses_mock_room() -> None:
    command = _managed_room_command(repo="sample_repo", host="127.0.0.1", port=8765, slidev_port=3030)

    assert command == [
        sys.executable,
        "-m",
        "devdefender_lab.room",
        "--repo",
        "sample_repo",
        "--mock",
        "--host",
        "127.0.0.1",
        "--port",
        "8765",
        "--slidev-port",
        "3030",
    ]


def test_room_acceptance_parse_room_url_requires_explicit_port() -> None:
    assert _parse_room_url("http://127.0.0.1:8765") == ("127.0.0.1", 8765)

    try:
        _parse_room_url("http://127.0.0.1")
    except ValueError as exc:
        assert "explicit port" in str(exc)
    else:
        raise AssertionError("Expected explicit port validation.")


def test_room_acceptance_managed_report_does_not_include_shutdown_token() -> None:
    report = managed_room_report(
        {
            "pid": 123,
            "room_url": "http://127.0.0.1:8765",
            "repo": "sample_repo",
            "room_port": 8765,
            "slidev_port": 3030,
            "stdout": "out.log",
            "stderr": "err.log",
            "command": ["python", "-m", "devdefender_lab.room"],
            "shutdown_token": "secret-token",
        },
        {"ok": True, "shutdown_request_ok": True},
    )

    assert "shutdown_token" not in report
    assert "secret-token" not in json.dumps(report)
    assert report["room_port"] == 8765
    assert report["shutdown"]["ok"] is True
