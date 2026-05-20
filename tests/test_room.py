import json
import socket
import threading
from base64 import urlsafe_b64decode
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen

from devdefender_lab.config import Settings
from devdefender_lab.room import ROOM_SHUTDOWN_TOKEN_ENV, Phase1Room, RoomHandler, _room_html


def test_room_http_api_submits_feedback(tmp_path: Path) -> None:
    room = Phase1Room(Settings(llm_mode="mock", artifact_dir=tmp_path), Path("sample_repo"))
    handler = type("TestRoomHandler", (RoomHandler,), {"room": room})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"

    try:
        with urlopen(f"{base_url}/api/session", timeout=5) as response:
            session = json.loads(response.read().decode("utf-8"))

        payload = json.dumps({"feedback": "Can invalid payment amounts be captured?"}).encode("utf-8")
        request = Request(
            f"{base_url}/api/feedback",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=5) as response:
            result = json.loads(response.read().decode("utf-8"))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert session["status"] == "waiting_for_feedback"
    assert result["ok"] is True
    assert result["state"]["status"] == "complete"
    assert "validate_payment" in result["state"]["defense"]
    assert result["state"]["refinement"]["status"] == "verified"


def test_room_http_api_records_slide_control_events(tmp_path: Path) -> None:
    room = Phase1Room(Settings(llm_mode="mock", artifact_dir=tmp_path), Path("sample_repo"))
    handler = type("TestRoomHandler", (RoomHandler,), {"room": room})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"

    try:
        payload = json.dumps({"action": "next", "source": "test"}).encode("utf-8")
        request = Request(
            f"{base_url}/api/slide-control",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=5) as response:
            result = json.loads(response.read().decode("utf-8"))

        with urlopen(f"{base_url}/api/slide-events", timeout=5) as response:
            events = json.loads(response.read().decode("utf-8"))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert result["ok"] is True
    assert result["event"]["action"] == "next"
    assert result["event"]["slide_index"] == 2
    assert events["current_slide_index"] == 2
    assert events["events"][0]["source"] == "test"
    assert (tmp_path / "slide_events.jsonl").exists()


def test_phase1_room_broadcasts_slide_events_to_registered_clients(tmp_path: Path) -> None:
    room = Phase1Room(Settings(llm_mode="mock", artifact_dir=tmp_path), Path("sample_repo"))
    client, server = socket.socketpair()
    try:
        room.add_slide_client(server)

        room.record_slide_action("next", source="test")
        raw = client.recv(4096)
    finally:
        room.remove_slide_client(server)
        client.close()
        server.close()

    payload = _decode_server_text_frame(raw)
    event = json.loads(payload)
    assert event["action"] == "next"
    assert event["slide_index"] == 2
    assert event["source"] == "test"


def test_room_http_api_records_timeline_event_and_mapped_slide_event(tmp_path: Path) -> None:
    room = Phase1Room(Settings(llm_mode="mock", artifact_dir=tmp_path), Path("sample_repo"))
    handler = type("TestRoomHandler", (RoomHandler,), {"room": room})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"

    try:
        payload = json.dumps({"kind": "tts_word", "token": "next", "source": "test-tts"}).encode("utf-8")
        request = Request(
            f"{base_url}/api/timeline-event",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=5) as response:
            result = json.loads(response.read().decode("utf-8"))

        with urlopen(f"{base_url}/api/timeline-events", timeout=5) as response:
            timeline = json.loads(response.read().decode("utf-8"))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert result["ok"] is True
    assert result["timeline_event"]["kind"] == "tts_word"
    assert result["slide_event"]["action"] == "next"
    assert result["slide_event"]["slide_index"] == 2
    assert result["slide_control"]["current_slide_index"] == 2
    assert timeline["events"][0]["token"] == "next"
    assert (tmp_path / "timeline_events.jsonl").exists()


def test_room_http_api_exposes_interruption_state(tmp_path: Path) -> None:
    room = Phase1Room(Settings(llm_mode="mock", artifact_dir=tmp_path), Path("sample_repo"))
    handler = type("TestRoomHandler", (RoomHandler,), {"room": room})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"

    try:
        payload = json.dumps(
            {"kind": "speech_interrupted", "source": "test-mic", "confidence": 0.92, "offset_ms": 1800}
        ).encode("utf-8")
        request = Request(
            f"{base_url}/api/timeline-event",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=5) as response:
            result = json.loads(response.read().decode("utf-8"))

        with urlopen(f"{base_url}/api/session", timeout=5) as response:
            session = json.loads(response.read().decode("utf-8"))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    interruption = result["timeline"]["interruption"]
    assert result["ok"] is True
    assert result["slide_event"] is None
    assert interruption["active"] is True
    assert interruption["event_count"] == 1
    assert interruption["source"] == "test-mic"
    assert interruption["confidence"] == 0.92
    assert interruption["offset_ms"] == 1800
    assert session["timeline"]["interruption"] == interruption


def test_room_http_api_maps_manual_voice_command_to_slide_event(tmp_path: Path) -> None:
    room = Phase1Room(Settings(llm_mode="mock", artifact_dir=tmp_path), Path("sample_repo"))
    handler = type("TestRoomHandler", (RoomHandler,), {"room": room})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"

    try:
        payload = json.dumps(
            {"kind": "manual_voice_command", "command": "goto", "slide_index": 4, "source": "test-voice"}
        ).encode("utf-8")
        request = Request(
            f"{base_url}/api/timeline-event",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=5) as response:
            result = json.loads(response.read().decode("utf-8"))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert result["ok"] is True
    assert result["timeline_event"]["kind"] == "manual_voice_command"
    assert result["slide_event"]["action"] == "goto"
    assert result["slide_event"]["slide_index"] == 4
    assert result["slide_control"]["current_slide_index"] == 4
    assert result["slide_control"]["events"][0]["source"] == "timeline:test-voice"


def test_room_http_api_issues_livekit_token_without_secret_leak_or_artifact(tmp_path: Path) -> None:
    settings = Settings(
        llm_mode="mock",
        artifact_dir=tmp_path,
        livekit_url="wss://example.livekit.cloud",
        livekit_api_key="test-key",
        livekit_api_secret="test-secret-with-enough-length-for-hs256",
    )
    room = Phase1Room(settings, Path("sample_repo"))
    handler = type("TestRoomHandler", (RoomHandler,), {"room": room})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"

    try:
        payload = json.dumps({"room": "room-1", "identity": "browser-1"}).encode("utf-8")
        request = Request(
            f"{base_url}/api/livekit-token",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=5) as response:
            result = json.loads(response.read().decode("utf-8"))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    dumped = json.dumps(result)
    claims = _decode_jwt_payload(result["token"])
    assert result["ok"] is True
    assert result["url"] == "wss://example.livekit.cloud"
    assert result["room_name"] == "room-1"
    assert result["identity"] == "browser-1"
    assert result["token_length"] == len(result["token"])
    assert claims["sub"] == "browser-1"
    assert claims["video"]["room"] == "room-1"
    assert claims["video"]["roomJoin"] is True
    assert "test-secret" not in dumped
    assert "test-key" not in dumped
    assert not (tmp_path / "livekit_token.json").exists()


def test_room_http_api_livekit_token_fails_cleanly_without_credentials(tmp_path: Path) -> None:
    room = Phase1Room(Settings(llm_mode="mock", artifact_dir=tmp_path), Path("sample_repo"))
    handler = type("TestRoomHandler", (RoomHandler,), {"room": room})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"

    try:
        payload = json.dumps({"room": "room-1", "identity": "browser-1"}).encode("utf-8")
        request = Request(
            f"{base_url}/api/livekit-token",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=5) as response:
            result = json.loads(response.read().decode("utf-8"))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert result["ok"] is False
    assert "LIVEKIT_URL" in result["error"]
    assert "token" not in result


def test_room_shutdown_endpoint_is_disabled_by_default(tmp_path: Path) -> None:
    room = Phase1Room(Settings(llm_mode="mock", artifact_dir=tmp_path), Path("sample_repo"))
    handler = type("TestRoomHandler", (RoomHandler,), {"room": room})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"

    try:
        payload = json.dumps({"token": "anything"}).encode("utf-8")
        request = Request(
            f"{base_url}/api/shutdown",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=5) as response:
            result = json.loads(response.read().decode("utf-8"))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert result["ok"] is False
    assert "disabled" in result["error"]


def test_room_shutdown_endpoint_rejects_invalid_token(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv(ROOM_SHUTDOWN_TOKEN_ENV, "expected-token")
    room = Phase1Room(Settings(llm_mode="mock", artifact_dir=tmp_path), Path("sample_repo"))
    handler = type("TestRoomHandler", (RoomHandler,), {"room": room})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"

    try:
        payload = json.dumps({"token": "wrong-token"}).encode("utf-8")
        request = Request(
            f"{base_url}/api/shutdown",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=5) as response:
            result = json.loads(response.read().decode("utf-8"))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert result["ok"] is False
    assert "Invalid shutdown token" in result["error"]


def test_room_shutdown_endpoint_stops_server_with_valid_token(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv(ROOM_SHUTDOWN_TOKEN_ENV, "expected-token")
    room = Phase1Room(Settings(llm_mode="mock", artifact_dir=tmp_path), Path("sample_repo"))
    handler = type("TestRoomHandler", (RoomHandler,), {"room": room})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"

    payload = json.dumps({"token": "expected-token"}).encode("utf-8")
    request = Request(
        f"{base_url}/api/shutdown",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=5) as response:
        result = json.loads(response.read().decode("utf-8"))

    thread.join(timeout=5)
    server.server_close()

    assert result["ok"] is True
    assert not thread.is_alive()


def test_room_html_contains_livekit_browser_client_hooks(tmp_path: Path) -> None:
    room = Phase1Room(Settings(llm_mode="mock", artifact_dir=tmp_path), Path("sample_repo"))

    html = _room_html(room.summary())

    assert "DevDefender Room" in html
    assert "Phase 2 local sync harness" in html
    assert "role=\"tablist\"" in html
    assert "data-tool-tab=\"control\"" in html
    assert "data-tool-tab=\"audio\"" in html
    assert "data-tool-tab=\"logs\"" in html
    assert "role=\"tab\" aria-selected=\"true\"" in html
    assert "aria-controls=\"tool-panel-control\"" in html
    assert "role=\"tabpanel\" aria-labelledby=\"tool-tab-control\"" in html
    assert "data-tool-panel=\"control\"" in html
    assert "function selectToolTab(name)" in html
    assert "button.setAttribute('aria-selected', String(active))" in html
    assert "livekit browser client" in html
    assert "browser interruption detector" in html
    assert "presenter cue player" in html
    assert "voice command harness" in html
    assert "timeline replay log" in html
    assert "https://cdn.jsdelivr.net/npm/livekit-client/dist/livekit-client.esm.mjs" in html
    assert "async function connectLiveKitRoom()" in html
    assert "createLocalTracks({ audio: true, video: false })" in html
    assert "auto_livekit" in html
    assert "audio_track_published" in html
    assert "auto_interruption" in html
    assert "auto_presenter_cue" in html
    assert "browser-interruption-detector" in html
    assert "browser-presenter-cue" in html
    assert "async function startInterruptionDetector" in html
    assert "async function runPresenterCue" in html
    assert "speech_started" in html
    assert "/api/timeline-event" in html
    assert "function renderTimeline(timeline)" in html
    assert "function renderInterruptionState(interruption)" in html
    assert "interruptionState" in html
    assert "Interruption active" in html
    assert "id=\"interruptButton\"" in html
    assert "manual-interrupt" in html
    assert "speech_interrupted" in html
    assert "renderTimeline(result.timeline)" in html
    assert "data-voice-command=\"next\"" in html
    assert "async function sendVoiceCommand(command)" in html
    assert "manual_voice_command" in html
    assert "manual-tts" in html


def test_room_session_includes_timeline_payload_for_ui(tmp_path: Path) -> None:
    room = Phase1Room(Settings(llm_mode="mock", artifact_dir=tmp_path), Path("sample_repo"))
    room.record_timeline_event(kind="livekit_connected", command="room-1", source="test")

    summary = room.summary()

    assert summary["timeline"]["thread_id"] == summary["thread_id"]
    assert summary["timeline"]["event_path"].endswith("timeline_events.jsonl")
    assert summary["timeline"]["interruption"]["active"] is False
    assert summary["timeline"]["interruption"]["event_count"] == 0
    assert summary["timeline"]["events"][0]["kind"] == "livekit_connected"
    assert summary["timeline"]["events"][0]["command"] == "room-1"


def _decode_jwt_payload(token: str) -> dict:
    parts = token.split(".")
    assert len(parts) == 3
    padded = parts[1] + "=" * (-len(parts[1]) % 4)
    return json.loads(urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))


def _decode_server_text_frame(raw: bytes) -> str:
    assert raw[0] == 0x81
    length = raw[1] & 0x7F
    offset = 2
    if length == 126:
        length = int.from_bytes(raw[offset : offset + 2], "big")
        offset += 2
    elif length == 127:
        length = int.from_bytes(raw[offset : offset + 8], "big")
        offset += 8
    return raw[offset : offset + length].decode("utf-8")
