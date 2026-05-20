from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import socket
import urllib.parse
import urllib.request


DEFAULT_ROOM_URL = "http://127.0.0.1:8765"


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify slide WebSocket broadcast and replay consistency.")
    parser.add_argument("--room-url", default=DEFAULT_ROOM_URL, help="Running DevDefender room URL.")
    args = parser.parse_args()

    room_url = args.room_url.rstrip("/")
    with open_slide_socket(room_url) as ws:
        snapshot = recv_json_frame(ws)
        posted = _post_json(f"{room_url}/api/slide-control", {"action": "next", "source": "slide-sync-smoke"})
        broadcast = recv_json_frame(ws)
    replay = _get_json(f"{room_url}/api/slide-events")
    report = build_report(snapshot, posted, broadcast, replay)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if not report["ok"]:
        raise SystemExit(1)


def build_report(
    snapshot: dict[str, object],
    posted: dict[str, object],
    broadcast: dict[str, object],
    replay: dict[str, object],
) -> dict[str, object]:
    posted_event = posted.get("event") if isinstance(posted.get("event"), dict) else {}
    replay_events = replay.get("events") if isinstance(replay.get("events"), list) else []
    last_replay = replay_events[-1] if replay_events and isinstance(replay_events[-1], dict) else {}
    snapshot_index = snapshot.get("slide_index")
    expected_next = snapshot_index + 1 if isinstance(snapshot_index, int) else None
    checks = {
        "snapshot_is_goto": snapshot.get("action") == "goto",
        "snapshot_slide_index_valid": isinstance(snapshot_index, int) and snapshot_index >= 1,
        "post_ok": posted.get("ok") is True,
        "posted_event_next": posted_event.get("action") == "next",
        "posted_event_advances_snapshot": posted_event.get("slide_index") == expected_next,
        "broadcast_matches_posted": _event_identity(broadcast) == _event_identity(posted_event),
        "replay_current_matches_broadcast": replay.get("current_slide_index") == broadcast.get("slide_index"),
        "replay_last_matches_broadcast": _event_identity(last_replay) == _event_identity(broadcast),
    }
    return {
        "ok": all(checks.values()),
        "checks": checks,
        "snapshot": snapshot,
        "broadcast": broadcast,
        "expected_next_slide_index": expected_next,
        "current_slide_index": replay.get("current_slide_index"),
        "slide_event_count": len(replay_events),
    }


def open_slide_socket(room_url: str) -> socket.socket:
    parsed = urllib.parse.urlparse(room_url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"Unsupported room URL scheme: {parsed.scheme}")
    if parsed.scheme == "https":
        raise ValueError("slide_sync_smoke only supports local http rooms.")

    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 80
    path_prefix = parsed.path.rstrip("/")
    ws_path = f"{path_prefix}/ws/slides" if path_prefix else "/ws/slides"
    key = base64.b64encode(os.urandom(16)).decode("ascii")
    request = (
        f"GET {ws_path} HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        "Sec-WebSocket-Version: 13\r\n"
        "\r\n"
    ).encode("ascii")

    sock = socket.create_connection((host, port), timeout=10)
    sock.settimeout(10)
    sock.sendall(request)
    response = _recv_until(sock, b"\r\n\r\n")
    accept = base64.b64encode(
        hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")).digest()
    ).decode("ascii")
    if b" 101 " not in response or f"Sec-WebSocket-Accept: {accept}".encode("ascii") not in response:
        sock.close()
        raise RuntimeError(f"WebSocket upgrade failed: {response.decode('iso-8859-1', errors='replace')}")
    return sock


def recv_json_frame(sock: socket.socket) -> dict[str, object]:
    return json.loads(recv_text_frame(sock))


def recv_text_frame(sock: socket.socket) -> str:
    header = _recv_exact(sock, 2)
    opcode = header[0] & 0x0F
    if opcode == 8:
        raise RuntimeError("WebSocket closed before data frame.")
    if opcode != 1:
        raise RuntimeError(f"Expected text frame, got opcode {opcode}.")

    length = header[1] & 0x7F
    if length == 126:
        length = int.from_bytes(_recv_exact(sock, 2), "big")
    elif length == 127:
        length = int.from_bytes(_recv_exact(sock, 8), "big")
    payload = _recv_exact(sock, length) if length else b""
    return payload.decode("utf-8")


def _event_identity(event: dict[str, object]) -> dict[str, object]:
    return {
        "action": event.get("action"),
        "slide_index": event.get("slide_index"),
        "source": event.get("source"),
    }


def _recv_until(sock: socket.socket, delimiter: bytes) -> bytes:
    data = b""
    while delimiter not in data:
        chunk = sock.recv(4096)
        if not chunk:
            break
        data += chunk
    return data


def _recv_exact(sock: socket.socket, length: int) -> bytes:
    chunks = []
    remaining = length
    while remaining > 0:
        chunk = sock.recv(remaining)
        if not chunk:
            raise RuntimeError("Socket closed while reading WebSocket frame.")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


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


def _get_json(url: str) -> dict[str, object]:
    with urllib.request.urlopen(url, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


if __name__ == "__main__":
    main()
