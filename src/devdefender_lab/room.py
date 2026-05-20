from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from devdefender_lab.config import Settings, load_settings
from devdefender_lab.models import Phase1Status
from devdefender_lab.audio_provider import LiveKitAudioProvider, LiveKitBrowserToken
from devdefender_lab.meeting import redact_meeting_url
from devdefender_lab.slide_control import SlideControlEvent, SlideEventLog
from devdefender_lab.timeline import (
    TimelineEventLog,
    TimelineMappingResult,
    VoiceTimelineAdapter,
    timeline_interruption_state,
)
from devdefender_lab.workflow import DefenseState, resume_phase1, start_phase1


ROOM_SHUTDOWN_TOKEN_ENV = "DEVDEFENDER_ROOM_SHUTDOWN_TOKEN"


class Phase1Room:
    def __init__(self, settings: Settings, repo_path: Path) -> None:
        self.settings = settings
        self.repo_path = repo_path
        self.lock = threading.Lock()
        self.session = start_phase1(settings, repo_path)
        self.state: DefenseState | None = None
        self.last_error: str | None = None
        self.slidev_process: subprocess.Popen | None = None
        self.slide_events = SlideEventLog(
            self.settings.artifact_dir / "slide_events.jsonl",
            thread_id=str(self.session["thread_id"]),
        )
        self.timeline_events = TimelineEventLog(
            self.settings.artifact_dir / "timeline_events.jsonl",
            thread_id=str(self.session["thread_id"]),
        )
        self.voice_timeline = VoiceTimelineAdapter(self.timeline_events, self.slide_events)
        self._slide_clients: set[socket.socket] = set()
        self._slide_clients_lock = threading.Lock()

    @property
    def status(self) -> str:
        if self.last_error:
            return "error"
        if self.state:
            return Phase1Status.COMPLETE.value
        return Phase1Status.WAITING_FOR_FEEDBACK.value

    def start_slidev(self) -> None:
        deck_path = Path(self.session["interrupt"].deck_path)
        npx = _resolve_npx()
        command = [
            npx,
            "slidev",
            str(deck_path),
            "--remote",
            "127.0.0.1",
            "--port",
            str(self.settings.slidev_port),
            "--log",
            "warn",
        ]
        creationflags = 0
        if os.name == "nt":
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        else:
            creationflags = 0
        self.slidev_process = subprocess.Popen(
            command,
            cwd=Path.cwd(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
            start_new_session=os.name != "nt",
        )

    def stop_slidev(self) -> None:
        if not self.slidev_process:
            return
        if self.slidev_process.poll() is not None:
            return
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(self.slidev_process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            return
        try:
            os.killpg(self.slidev_process.pid, 15)
        except ProcessLookupError:
            return
        try:
            self.slidev_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(self.slidev_process.pid, 9)

    def submit_feedback(self, feedback: str) -> dict[str, Any]:
        if not feedback.strip():
            return {"ok": False, "error": "Feedback cannot be empty."}
        with self.lock:
            if self.state:
                return {"ok": True, "state": self.summary()}
            try:
                self.state = resume_phase1(
                    self.session["app"],
                    self.settings,
                    str(self.session["thread_id"]),
                    feedback.strip(),
                )
            except Exception as exc:
                self.last_error = str(exc)
                return {"ok": False, "error": self.last_error}
        return {"ok": True, "state": self.summary()}

    def record_slide_action(self, action: str, slide_index: int | None = None, source: str = "manual") -> SlideControlEvent:
        event = self.slide_events.record(action, slide_index=slide_index, source=source)
        self.broadcast_slide_event(event)
        return event

    def slide_event_payload(self) -> dict[str, Any]:
        events = [event.model_dump() for event in self.slide_events.events()]
        return {
            "thread_id": self.session["thread_id"],
            "current_slide_index": self.slide_events.current_slide_index(),
            "event_path": str(self.slide_events.path),
            "events": events,
        }

    def record_timeline_event(
        self,
        kind: str,
        source: str = "manual",
        token: str | None = None,
        command: str | None = None,
        slide_index: int | None = None,
        confidence: float | None = None,
        offset_ms: int | None = None,
    ) -> TimelineMappingResult:
        result = self.voice_timeline.ingest(
            kind=kind,
            source=source,
            token=token,
            command=command,
            slide_index=slide_index,
            confidence=confidence,
            offset_ms=offset_ms,
        )
        if result.slide_event:
            self.broadcast_slide_event(result.slide_event)
        return result

    def timeline_event_payload(self) -> dict[str, Any]:
        timeline_events = self.timeline_events.events()
        events = [event.model_dump() for event in timeline_events]
        return {
            "thread_id": self.session["thread_id"],
            "event_path": str(self.timeline_events.path),
            "interruption": timeline_interruption_state(timeline_events).model_dump(),
            "events": events,
        }

    def livekit_browser_token(self, identity: str | None = None, room_name: str | None = None) -> LiveKitBrowserToken:
        provider = LiveKitAudioProvider(
            settings=self.settings,
            room_name=room_name or "devdefender-phase2",
            identity=identity or f"{self.session['thread_id']}-browser",
        )
        return provider.create_browser_token()

    def add_slide_client(self, client: socket.socket) -> None:
        with self._slide_clients_lock:
            self._slide_clients.add(client)

    def remove_slide_client(self, client: socket.socket) -> None:
        with self._slide_clients_lock:
            self._slide_clients.discard(client)

    def broadcast_slide_event(self, event: SlideControlEvent) -> None:
        message = _websocket_text_frame(json.dumps(event.model_dump(), ensure_ascii=False))
        with self._slide_clients_lock:
            clients = list(self._slide_clients)
        for client in clients:
            try:
                client.sendall(message)
            except OSError:
                self.remove_slide_client(client)

    def summary(self) -> dict[str, Any]:
        interrupt = self.session["interrupt"]
        state = self.state
        issue = state.get("issue") if state else None
        refinement = state.get("refinement") if state else None
        return {
            "thread_id": self.session["thread_id"],
            "status": self.status,
            "slidev_url": interrupt.slidev_url,
            "graph_path": str(interrupt.graph_path),
            "deck_path": str(interrupt.deck_path),
            "node_count": interrupt.node_count,
            "edge_count": interrupt.edge_count,
            "slide_control": self.slide_event_payload(),
            "timeline": self.timeline_event_payload(),
            "defense": state.get("defense") if state else "",
            "issue": issue.model_dump() if issue else None,
            "refinement": refinement.model_dump(mode="json") if refinement else None,
            "error": self.last_error,
        }


class RoomHandler(BaseHTTPRequestHandler):
    room: Phase1Room

    def log_message(self, format: str, *args: object) -> None:
        return

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/":
            self._send_html(_room_html(self.room.summary()))
            return
        if parsed.path == "/meeting-test":
            self._send_html(_meeting_test_html())
            return
        if parsed.path == "/webrtc-meeting-test":
            self._send_html(_webrtc_meeting_test_html())
            return
        if parsed.path == "/zoom-discovery-test":
            self._send_html(_zoom_discovery_test_html())
            return
        if parsed.path == "/api/session":
            self._send_json(self.room.summary())
            return
        if parsed.path == "/api/slide-events":
            self._send_json(self.room.slide_event_payload())
            return
        if parsed.path == "/api/timeline-events":
            self._send_json(self.room.timeline_event_payload())
            return
        if parsed.path == "/ws/slides":
            self._serve_slide_websocket()
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/feedback":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8")
            feedback = self._feedback_from_body(raw)
            self._send_json(self.room.submit_feedback(feedback))
            return
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8")
        if parsed.path == "/api/slide-control":
            self._send_json(self._slide_control_from_body(raw))
            return
        if parsed.path == "/api/timeline-event":
            self._send_json(self._timeline_event_from_body(raw))
            return
        if parsed.path == "/api/livekit-token":
            self._send_json(self._livekit_token_from_body(raw))
            return
        if parsed.path == "/api/shutdown":
            self._send_json(self._shutdown_from_body(raw))
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def _feedback_from_body(self, raw: str) -> str:
        content_type = self.headers.get("Content-Type", "")
        if "application/json" in content_type:
            payload = json.loads(raw or "{}")
            return str(payload.get("feedback", ""))
        payload = urllib.parse.parse_qs(raw)
        return payload.get("feedback", [""])[0]

    def _send_json(self, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _slide_control_from_body(self, raw: str) -> dict[str, Any]:
        try:
            payload = json.loads(raw or "{}")
            event = self.room.record_slide_action(
                str(payload.get("action", "")),
                slide_index=payload.get("slide_index"),
                source=str(payload.get("source", "manual")),
            )
        except (TypeError, ValueError) as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "event": event.model_dump(), "slide_control": self.room.slide_event_payload()}

    def _timeline_event_from_body(self, raw: str) -> dict[str, Any]:
        try:
            payload = json.loads(raw or "{}")
            result = self.room.record_timeline_event(
                kind=str(payload.get("kind", "")),
                source=str(payload.get("source", "manual")),
                token=payload.get("token"),
                command=_safe_timeline_command(str(payload.get("kind", "")), payload.get("command")),
                slide_index=payload.get("slide_index"),
                confidence=payload.get("confidence"),
                offset_ms=payload.get("offset_ms"),
            )
        except (TypeError, ValueError) as exc:
            return {"ok": False, "error": str(exc)}
        return {
            "ok": True,
            "timeline_event": result.timeline_event.model_dump(),
            "slide_event": result.slide_event.model_dump() if result.slide_event else None,
            "timeline": self.room.timeline_event_payload(),
            "slide_control": self.room.slide_event_payload(),
        }

    def _livekit_token_from_body(self, raw: str) -> dict[str, Any]:
        try:
            payload = json.loads(raw or "{}")
            token = self.room.livekit_browser_token(
                identity=str(payload.get("identity") or "") or None,
                room_name=str(payload.get("room") or "") or None,
            )
        except (RuntimeError, ValueError) as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True, **token.model_dump()}

    def _shutdown_from_body(self, raw: str) -> dict[str, Any]:
        expected_token = os.getenv(ROOM_SHUTDOWN_TOKEN_ENV)
        if not expected_token:
            return {"ok": False, "error": "Room shutdown endpoint is disabled."}
        try:
            payload = json.loads(raw or "{}")
        except json.JSONDecodeError:
            return {"ok": False, "error": "Invalid shutdown payload."}
        if str(payload.get("token") or "") != expected_token:
            return {"ok": False, "error": "Invalid shutdown token."}
        threading.Thread(target=self.server.shutdown, daemon=True).start()
        return {"ok": True}

    def _serve_slide_websocket(self) -> None:
        key = self.headers.get("Sec-WebSocket-Key")
        if not key:
            self.send_error(HTTPStatus.BAD_REQUEST, "Missing Sec-WebSocket-Key")
            return
        accept = base64.b64encode(
            hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")).digest()
        ).decode("ascii")
        self.send_response(HTTPStatus.SWITCHING_PROTOCOLS)
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", accept)
        self.end_headers()

        client = self.connection
        self.room.add_slide_client(client)
        try:
            snapshot = {
                "thread_id": self.room.session["thread_id"],
                "action": "goto",
                "slide_index": self.room.slide_events.current_slide_index(),
                "source": "snapshot",
            }
            client.sendall(_websocket_text_frame(json.dumps(snapshot, ensure_ascii=False)))
            while True:
                header = client.recv(2)
                if not header:
                    break
                opcode = header[0] & 0x0F
                length = header[1] & 0x7F
                if length == 126:
                    length = int.from_bytes(client.recv(2), "big")
                elif length == 127:
                    length = int.from_bytes(client.recv(8), "big")
                mask = client.recv(4)
                payload = client.recv(length) if length else b""
                if mask:
                    payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
                if opcode == 8:
                    break
                if opcode == 1:
                    self._handle_slide_websocket_message(payload.decode("utf-8"))
        finally:
            self.room.remove_slide_client(client)

    def _handle_slide_websocket_message(self, raw: str) -> None:
        payload = json.loads(raw or "{}")
        self.room.record_slide_action(
            str(payload.get("action", "")),
            slide_index=payload.get("slide_index"),
            source=str(payload.get("source", "websocket")),
        )


def serve(settings: Settings, repo_path: Path, open_browser: bool = False) -> None:
    room = Phase1Room(settings, repo_path)
    room.start_slidev()
    server_address = (settings.room_host, settings.room_port)
    RoomHandler.room = room
    httpd = ThreadingHTTPServer(server_address, RoomHandler)
    url = f"http://{settings.room_host}:{settings.room_port}"
    print(f"Defense room: {url}")
    print(f"Slidev deck:   {room.session['interrupt'].slidev_url}")
    if open_browser:
        import webbrowser

        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        room.stop_slidev()
        httpd.server_close()


def _resolve_npx() -> str:
    candidates = ["npx.cmd", "npx"] if os.name == "nt" else ["npx"]
    for candidate in candidates:
        path = shutil.which(candidate)
        if path:
            return path
    raise RuntimeError("npx was not found on PATH. Run npm install, then start the room from a shell with Node.js on PATH.")


def _websocket_text_frame(text: str) -> bytes:
    payload = text.encode("utf-8")
    header = bytearray([0x81])
    length = len(payload)
    if length < 126:
        header.append(length)
    elif length < 65536:
        header.append(126)
        header.extend(length.to_bytes(2, "big"))
    else:
        header.append(127)
        header.extend(length.to_bytes(8, "big"))
    return bytes(header) + payload


def _safe_timeline_command(kind: str, command: object) -> object:
    if isinstance(command, str) and kind.startswith("meeting_"):
        return redact_meeting_url(command)
    return command


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Phase 1 local defense room.")
    parser.add_argument("--repo", default="sample_repo", help="Repository path to defend.")
    parser.add_argument("--mock", action="store_true", help="Use deterministic mock LLM responses.")
    parser.add_argument("--open", action="store_true", help="Open the room in the default browser.")
    parser.add_argument("--host", help="Defense room host. Defaults to DEVDEFENDER_ROOM_HOST.")
    parser.add_argument("--port", type=int, help="Defense room port. Defaults to DEVDEFENDER_ROOM_PORT.")
    parser.add_argument("--slidev-port", type=int, help="Slidev port. Defaults to DEVDEFENDER_SLIDEV_PORT.")
    args = parser.parse_args()

    settings = load_settings()
    if args.mock:
        settings.llm_mode = "mock"
    if args.host:
        settings.room_host = args.host
    if args.port:
        settings.room_port = args.port
    if args.slidev_port:
        settings.slidev_port = args.slidev_port
    serve(settings, Path(args.repo), open_browser=args.open)


def _room_html(summary: dict[str, Any]) -> str:
    initial_json = json.dumps(summary, ensure_ascii=False)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>DevDefender Phase 1</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #17202a;
      --muted: #627083;
      --line: #d7dde6;
      --panel: #f8fafc;
      --accent: #0f766e;
      --accent-2: #b45309;
      --danger: #b42318;
      --code: #111827;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #eef2f6;
      color: var(--ink);
    }}
    header {{
      height: 56px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 0 18px;
      border-bottom: 1px solid var(--line);
      background: #ffffff;
    }}
    .title-row {{
      display: flex;
      align-items: baseline;
      gap: 10px;
      min-width: 0;
    }}
    h1 {{
      margin: 0;
      font-size: 18px;
      font-weight: 720;
      letter-spacing: 0;
    }}
    .subtitle {{
      color: var(--muted);
      font-size: 12px;
      white-space: nowrap;
    }}
    main {{
      height: calc(100vh - 56px);
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(320px, 430px);
      gap: 0;
    }}
    iframe {{
      width: 100%;
      height: 100%;
      border: 0;
      background: white;
    }}
    aside {{
      display: flex;
      flex-direction: column;
      gap: 14px;
      padding: 16px;
      overflow: auto;
      border-left: 1px solid var(--line);
      background: var(--panel);
    }}
    .metrics {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 10px;
    }}
    .tool-tabs {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 8px;
      padding: 4px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #ffffff;
    }}
    .tool-tab {{
      height: 36px;
      margin: 0;
      border-radius: 6px;
      background: #f1f5f9;
      color: #334155;
      font-weight: 720;
    }}
    .tool-tab.active {{
      background: var(--accent);
      color: #ffffff;
    }}
    .tool-panel[hidden] {{
      display: none;
    }}
    .slide-controls {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
      margin-top: 10px;
    }}
    .goto-row {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) 96px;
      gap: 8px;
      margin-top: 8px;
    }}
    .livekit-row {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
      gap: 8px;
      margin-top: 8px;
    }}
    .metric, .block {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #ffffff;
      padding: 12px;
    }}
    .metric strong {{
      display: block;
      font-size: 24px;
      line-height: 1.1;
    }}
    .metric span, .label, .path, .status {{
      color: var(--muted);
      font-size: 12px;
    }}
    .status {{
      display: inline-flex;
      align-items: center;
      min-height: 30px;
      padding: 5px 10px;
      border: 1px solid var(--line);
      border-radius: 999px;
      background: #f9fafb;
      color: var(--accent);
      font-weight: 700;
    }}
    textarea {{
      width: 100%;
      min-height: 150px;
      resize: vertical;
      border: 1px solid #b9c2cf;
      border-radius: 8px;
      padding: 10px;
      font: inherit;
      line-height: 1.45;
      color: var(--ink);
      background: #ffffff;
    }}
    input[type="number"] {{
      width: 100%;
      height: 42px;
      border: 1px solid #b9c2cf;
      border-radius: 8px;
      padding: 0 10px;
      font: inherit;
      color: var(--ink);
      background: #ffffff;
    }}
    input[type="text"] {{
      width: 100%;
      height: 42px;
      border: 1px solid #b9c2cf;
      border-radius: 8px;
      padding: 0 10px;
      font: inherit;
      color: var(--ink);
      background: #ffffff;
    }}
    button {{
      width: 100%;
      height: 42px;
      margin-top: 10px;
      border: 0;
      border-radius: 8px;
      background: var(--accent);
      color: white;
      font: inherit;
      font-weight: 740;
      cursor: pointer;
    }}
    .slide-controls button, .goto-row button {{
      margin-top: 0;
    }}
    .livekit-actions {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
      gap: 8px;
      margin-top: 10px;
    }}
    .livekit-actions button {{
      margin-top: 0;
    }}
    .interruption-detector {{
      margin-top: 14px;
      padding-top: 12px;
      border-top: 1px solid var(--line);
    }}
    .presenter-cues {{
      margin-top: 14px;
      padding-top: 12px;
      border-top: 1px solid var(--line);
    }}
    .detector-meter {{
      height: 8px;
      margin-top: 8px;
      overflow: hidden;
      border-radius: 999px;
      background: #e5e7eb;
    }}
    .detector-meter span {{
      display: block;
      width: 0%;
      height: 100%;
      border-radius: inherit;
      background: var(--accent-2);
      transition: width 120ms ease;
    }}
    .voice-actions {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 8px;
      margin-top: 10px;
    }}
    .voice-actions button {{
      margin-top: 0;
    }}
    .secondary {{
      background: #334155;
    }}
    button:disabled {{
      cursor: progress;
      background: #8795a5;
    }}
    pre {{
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      margin: 8px 0 0;
      padding: 10px;
      border-radius: 8px;
      background: #111827;
      color: #f8fafc;
      font-size: 13px;
      line-height: 1.45;
    }}
    .issue-title {{
      margin: 8px 0 4px;
      font-weight: 740;
      color: var(--accent-2);
    }}
    .event-list {{
      max-height: 190px;
      overflow: auto;
      margin-top: 8px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #f9fafb;
    }}
    .event-item {{
      display: grid;
      grid-template-columns: minmax(86px, 120px) minmax(0, 1fr);
      gap: 8px;
      padding: 8px 10px;
      border-bottom: 1px solid var(--line);
      font-size: 13px;
    }}
    .event-item:last-child {{
      border-bottom: 0;
    }}
    .interruption-state {{
      margin-top: 8px;
      padding: 8px 10px;
      border: 1px solid #f4c7a0;
      border-radius: 8px;
      background: #fff7ed;
      color: #9a3412;
      font-size: 13px;
      line-height: 1.35;
    }}
    .interruption-state.idle {{
      border-color: var(--line);
      background: #f9fafb;
      color: var(--muted);
    }}
    .slide-number {{
      font-weight: 740;
      color: var(--accent);
      overflow-wrap: anywhere;
    }}
    .result-block {{
      min-height: 0;
    }}
    .error {{ color: var(--danger); font-weight: 700; }}
    @media (max-width: 860px) {{
      header {{ height: auto; min-height: 56px; align-items: flex-start; flex-direction: column; padding: 12px 14px; }}
      .title-row {{ flex-direction: column; gap: 2px; }}
      main {{ height: auto; min-height: calc(100vh - 80px); grid-template-columns: 1fr; }}
      iframe {{ height: 56vh; min-height: 360px; }}
      aside {{ border-left: 0; border-top: 1px solid var(--line); }}
      .metrics {{ grid-template-columns: 1fr; }}
      .event-item {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <header>
    <div class="title-row">
      <h1>DevDefender Room</h1>
      <span class="subtitle">Phase 2 local sync harness</span>
    </div>
    <div class="status" id="status">waiting</div>
  </header>
  <main>
    <iframe id="slides" src="{summary['slidev_url']}" title="Slidev defense deck"></iframe>
    <aside>
      <section class="metrics">
        <div class="metric"><strong id="nodeCount">0</strong><span>nodes</span></div>
        <div class="metric"><strong id="edgeCount">0</strong><span>edges</span></div>
        <div class="metric"><strong id="currentSlideMetric">1</strong><span>slide</span></div>
      </section>
      <section class="block">
        <div class="label">thread</div>
        <div class="path" id="threadId"></div>
        <div class="label" style="margin-top:8px">graph</div>
        <div class="path" id="graphPath"></div>
      </section>
      <section class="block result-block">
        <form id="feedbackForm">
          <label class="label" for="feedback">reviewer feedback</label>
          <textarea id="feedback" name="feedback">Payment capture looks risky. Explain why invalid amounts cannot be captured, then create an issue if evidence is weak.</textarea>
          <button id="submitButton" type="submit">Submit Feedback</button>
        </form>
        <div id="result"></div>
      </section>
      <nav class="tool-tabs" role="tablist" aria-label="Room tools">
        <button class="tool-tab active" type="button" role="tab" aria-selected="true" aria-controls="tool-panel-control" id="tool-tab-control" data-tool-tab="control">Control</button>
        <button class="tool-tab" type="button" role="tab" aria-selected="false" aria-controls="tool-panel-audio" id="tool-tab-audio" data-tool-tab="audio">Audio</button>
        <button class="tool-tab" type="button" role="tab" aria-selected="false" aria-controls="tool-panel-logs" id="tool-tab-logs" data-tool-tab="logs">Logs</button>
      </nav>
      <section class="block tool-panel" id="tool-panel-control" role="tabpanel" aria-labelledby="tool-tab-control" data-tool-panel="control">
        <div class="label">slide control</div>
        <div class="slide-controls">
          <button class="secondary" type="button" data-slide-action="prev">Prev</button>
          <button type="button" data-slide-action="next">Next</button>
        </div>
        <div class="goto-row">
          <input id="gotoSlide" type="number" min="1" value="1" aria-label="Slide number">
          <button class="secondary" id="gotoButton" type="button">Goto</button>
        </div>
        <div class="label" style="margin-top:14px">voice command harness</div>
        <div class="voice-actions">
          <button class="secondary" type="button" data-voice-command="prev">Prev</button>
          <button type="button" data-voice-command="next">Next</button>
          <button class="secondary" type="button" data-voice-command="goto">Goto</button>
        </div>
        <div class="goto-row">
          <input id="voiceGotoSlide" type="number" min="1" value="1" aria-label="Voice goto slide number">
          <button class="secondary" id="ttsNextButton" type="button">TTS word: next</button>
        </div>
        <button class="secondary" id="interruptButton" type="button">Interrupt</button>
      </section>
      <section class="block tool-panel" id="tool-panel-audio" role="tabpanel" aria-labelledby="tool-tab-audio" data-tool-panel="audio" hidden>
        <div class="label">livekit browser client</div>
        <div class="livekit-row">
          <input id="livekitRoom" type="text" value="devdefender-phase2" aria-label="LiveKit room">
          <input id="livekitIdentity" type="text" value="devdefender-browser" aria-label="LiveKit identity">
        </div>
        <div class="livekit-actions">
          <button id="livekitButton" type="button">Connect</button>
          <button class="secondary" id="livekitDisconnectButton" type="button" disabled>Disconnect</button>
        </div>
        <div class="path" id="livekitStatus" style="margin-top:8px">Not connected.</div>
        <div class="interruption-detector">
          <div class="label">browser interruption detector</div>
          <div class="livekit-actions">
            <button class="secondary" id="detectorButton" type="button">Start detector</button>
            <button class="secondary" id="detectorTestButton" type="button">Test burst</button>
          </div>
          <div class="detector-meter" aria-hidden="true"><span id="detectorMeter"></span></div>
          <div class="path" id="detectorStatus" style="margin-top:8px">Detector idle.</div>
        </div>
        <div class="presenter-cues">
          <div class="label">presenter cue player</div>
          <div class="livekit-actions">
            <button id="presenterCueButton" type="button">Run cue</button>
            <button class="secondary" id="presenterResetButton" type="button">Reset cue</button>
          </div>
          <div class="path" id="presenterCueStatus" style="margin-top:8px">Cue idle.</div>
        </div>
      </section>
      <section class="block tool-panel" id="tool-panel-logs" role="tabpanel" aria-labelledby="tool-tab-logs" data-tool-panel="logs" hidden>
        <div class="label">slide replay log</div>
        <div class="path" id="slideEventPath"></div>
        <div class="event-list" id="slideEvents"></div>
        <div class="label" style="margin-top:14px">timeline replay log</div>
        <div class="path" id="timelineEventPath"></div>
        <div class="interruption-state idle" id="interruptionState">No interruption recorded.</div>
        <div class="event-list" id="timelineEvents"></div>
      </section>
    </aside>
  </main>
  <script>
    const initial = {initial_json};
    const slideBaseUrl = initial.slidev_url.replace(/\\/$/, '');
    const statusEl = document.getElementById('status');
    const resultEl = document.getElementById('result');
    const submitButton = document.getElementById('submitButton');
    const form = document.getElementById('feedbackForm');
    const slideFrame = document.getElementById('slides');
    const currentSlideMetricEl = document.getElementById('currentSlideMetric');
    const gotoSlideEl = document.getElementById('gotoSlide');
    const slideEventsEl = document.getElementById('slideEvents');
    const slideEventPathEl = document.getElementById('slideEventPath');
    const timelineEventsEl = document.getElementById('timelineEvents');
    const timelineEventPathEl = document.getElementById('timelineEventPath');
    const interruptionStateEl = document.getElementById('interruptionState');
    const livekitButton = document.getElementById('livekitButton');
    const livekitDisconnectButton = document.getElementById('livekitDisconnectButton');
    const livekitStatusEl = document.getElementById('livekitStatus');
    const livekitRoomEl = document.getElementById('livekitRoom');
    const livekitIdentityEl = document.getElementById('livekitIdentity');
    const detectorButton = document.getElementById('detectorButton');
    const detectorTestButton = document.getElementById('detectorTestButton');
    const detectorStatusEl = document.getElementById('detectorStatus');
    const detectorMeterEl = document.getElementById('detectorMeter');
    const presenterCueButton = document.getElementById('presenterCueButton');
    const presenterResetButton = document.getElementById('presenterResetButton');
    const presenterCueStatusEl = document.getElementById('presenterCueStatus');
    const livekitSdkUrl = 'https://cdn.jsdelivr.net/npm/livekit-client/dist/livekit-client.esm.mjs';
    let livekitRoomHandle = null;
    let livekitModulePromise = null;
    let detectorRunning = false;
    let detectorSawSpeech = false;
    let detectorContext = null;
    let detectorStream = null;
    let detectorSource = null;
    let detectorAnalyser = null;
    let detectorFrame = null;
    let slideEvents = [];
    let timelineEvents = [];

    function render(data) {{
      statusEl.textContent = data.status;
      document.getElementById('nodeCount').textContent = data.node_count;
      document.getElementById('edgeCount').textContent = data.edge_count;
      document.getElementById('threadId').textContent = data.thread_id;
      document.getElementById('graphPath').textContent = data.graph_path;
      renderSlideControl(data.slide_control || {{ current_slide_index: 1, events: [] }});
      renderTimeline(data.timeline || {{ events: [] }});
      if (data.error) {{
        resultEl.innerHTML = `<p class="error">${{escapeHtml(data.error)}}</p>`;
        submitButton.disabled = false;
        return;
      }}
      if (data.status === 'complete') {{
        submitButton.disabled = true;
        const issue = data.issue || {{}};
        const refinement = data.refinement || {{}};
        resultEl.innerHTML = `
          <div class="issue-title">${{escapeHtml(issue.title || 'Issue')}}</div>
          <pre>${{escapeHtml(JSON.stringify(issue, null, 2))}}</pre>
          <div class="issue-title">TDAD Report</div>
          <pre>${{escapeHtml(JSON.stringify(refinement, null, 2))}}</pre>
          <div class="issue-title">Defense</div>
          <pre>${{escapeHtml(data.defense || '')}}</pre>
        `;
      }}
    }}

    function renderSlideControl(control) {{
      slideEvents = control.events || slideEvents;
      const current = control.current_slide_index || 1;
      currentSlideMetricEl.textContent = current;
      gotoSlideEl.value = current;
      slideEventPathEl.textContent = control.event_path || '';
      slideEventsEl.innerHTML = slideEvents.length
        ? slideEvents.slice(-12).reverse().map(renderSlideEvent).join('')
        : '<div class="event-item"><span></span><span>No events recorded.</span></div>';
      setSlide(current);
    }}

    function renderSlideEvent(event) {{
      const time = event.timestamp ? new Date(event.timestamp).toLocaleTimeString() : '';
      return `<div class="event-item"><span class="slide-number">#${{escapeHtml(event.slide_index)}}</span><span>${{escapeHtml(event.action)}} · ${{escapeHtml(event.source)}} · ${{escapeHtml(time)}}</span></div>`;
    }}

    function renderTimeline(timeline) {{
      timelineEvents = timeline.events || timelineEvents;
      timelineEventPathEl.textContent = timeline.event_path || timelineEventPathEl.textContent || '';
      renderInterruptionState(timeline.interruption || {{ active: false, event_count: 0 }});
      timelineEventsEl.innerHTML = timelineEvents.length
        ? timelineEvents.slice(-12).reverse().map(renderTimelineEvent).join('')
        : '<div class="event-item"><span></span><span>No timeline events recorded.</span></div>';
    }}

    function renderInterruptionState(interruption) {{
      const count = interruption.event_count || 0;
      if (!count) {{
        interruptionStateEl.classList.add('idle');
        interruptionStateEl.textContent = 'No interruption recorded.';
        return;
      }}
      interruptionStateEl.classList.toggle('idle', !interruption.active);
      const status = interruption.active ? 'Interruption active' : 'Last interruption handled';
      const confidence = interruption.confidence == null ? 'n/a' : Number(interruption.confidence).toFixed(2);
      const offset = interruption.offset_ms == null ? 'n/a' : `${{interruption.offset_ms}}ms`;
      interruptionStateEl.textContent = `${{status}} 路 source=${{interruption.source || 'unknown'}} 路 confidence=${{confidence}} 路 offset=${{offset}}`;
    }}

    function renderTimelineEvent(event) {{
      const time = event.timestamp ? new Date(event.timestamp).toLocaleTimeString() : '';
      const primary = event.kind || 'event';
      const detail = event.command || event.token || event.slide_index || '';
      return `<div class="event-item"><span class="slide-number">${{escapeHtml(primary)}}</span><span>${{escapeHtml(event.source || 'manual')}} · ${{escapeHtml(detail)}} · ${{escapeHtml(time)}}</span></div>`;
    }}

    function setSlide(index) {{
      const nextSrc = `${{slideBaseUrl}}/${{index}}`;
      if (slideFrame.src !== nextSrc) {{
        slideFrame.src = nextSrc;
      }}
    }}

    async function sendSlideAction(action, slideIndex = null) {{
      const response = await fetch('/api/slide-control', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ action, slide_index: slideIndex, source: 'manual' }})
      }});
      const payload = await response.json();
      if (payload.ok) {{
        renderSlideControl(payload.slide_control);
      }}
    }}

    function applySlideEvent(event) {{
      slideEvents = [...slideEvents, event];
      renderSlideControl({{
        current_slide_index: event.slide_index,
        event_path: slideEventPathEl.textContent,
        events: slideEvents
      }});
    }}

    function escapeHtml(value) {{
      return String(value)
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#039;');
    }}

    form.addEventListener('submit', async (event) => {{
      event.preventDefault();
      submitButton.disabled = true;
      statusEl.textContent = 'answering';
      const feedback = document.getElementById('feedback').value;
      const response = await fetch('/api/feedback', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ feedback }})
      }});
      const payload = await response.json();
      if (!payload.ok) {{
        render({{ ...initial, status: 'error', error: payload.error }});
        return;
      }}
      render(payload.state);
    }});

    document.querySelectorAll('[data-slide-action]').forEach((button) => {{
      button.addEventListener('click', () => sendSlideAction(button.dataset.slideAction));
    }});
    document.querySelectorAll('[data-tool-tab]').forEach((button) => {{
      button.addEventListener('click', () => selectToolTab(button.dataset.toolTab));
    }});
    document.getElementById('gotoButton').addEventListener('click', () => {{
      sendSlideAction('goto', Number(gotoSlideEl.value || 1));
    }});
    document.querySelectorAll('[data-voice-command]').forEach((button) => {{
      button.addEventListener('click', () => sendVoiceCommand(button.dataset.voiceCommand));
    }});
    document.getElementById('ttsNextButton').addEventListener('click', () => {{
      recordTimelineEvent({{ kind: 'tts_word', token: 'next', source: 'manual-tts', offset_ms: 0 }});
    }});
    document.getElementById('interruptButton').addEventListener('click', () => {{
      recordTimelineEvent({{ kind: 'speech_interrupted', source: 'manual-interrupt', confidence: 1, offset_ms: 0 }});
    }});
    livekitButton.addEventListener('click', connectLiveKitRoom);
    livekitDisconnectButton.addEventListener('click', disconnectLiveKitRoom);
    detectorButton.addEventListener('click', toggleInterruptionDetector);
    detectorTestButton.addEventListener('click', runDetectorTestBurst);
    presenterCueButton.addEventListener('click', runPresenterCue);
    presenterResetButton.addEventListener('click', resetPresenterCue);

    async function sendVoiceCommand(command) {{
      const payload = {{
        kind: 'manual_voice_command',
        command,
        source: 'browser-voice-command'
      }};
      if (command === 'goto') {{
        payload.slide_index = Number(document.getElementById('voiceGotoSlide').value || 1);
      }}
      return recordTimelineEvent(payload);
    }}

    function selectToolTab(name) {{
      document.querySelectorAll('[data-tool-tab]').forEach((button) => {{
        const active = button.dataset.toolTab === name;
        button.classList.toggle('active', active);
        button.setAttribute('aria-selected', String(active));
      }});
      document.querySelectorAll('[data-tool-panel]').forEach((panel) => {{
        panel.hidden = panel.dataset.toolPanel !== name;
      }});
    }}

    async function requestLiveKitToken() {{
      livekitButton.disabled = true;
      livekitStatusEl.textContent = 'Requesting token...';
      const response = await fetch('/api/livekit-token', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{
          room: livekitRoomEl.value,
          identity: livekitIdentityEl.value
        }})
      }});
      const payload = await response.json();
      if (!payload.ok) {{
        livekitStatusEl.textContent = payload.error || 'LiveKit token request failed.';
        livekitButton.disabled = false;
        return;
      }}
      return payload;
    }}

    async function loadLiveKitModule() {{
      if (!livekitModulePromise) {{
        livekitModulePromise = import(livekitSdkUrl);
      }}
      return livekitModulePromise;
    }}

    async function connectLiveKitRoom() {{
      if (livekitRoomHandle) {{
        return;
      }}
      const tokenPayload = await requestLiveKitToken();
      if (!tokenPayload) {{
        return;
      }}
      try {{
        livekitStatusEl.textContent = 'Loading LiveKit client...';
        const LiveKit = await loadLiveKitModule();
        const room = new LiveKit.Room({{
          adaptiveStream: true,
          dynacast: true
        }});
        room.on(LiveKit.RoomEvent.Disconnected, () => {{
          livekitRoomHandle = null;
          livekitButton.disabled = false;
          livekitDisconnectButton.disabled = true;
          livekitStatusEl.textContent = 'Disconnected.';
          recordTimelineEvent({{ kind: 'livekit_disconnected', source: 'browser-livekit', command: tokenPayload.room_name }});
        }});
        livekitStatusEl.textContent = 'Connecting to LiveKit...';
        await room.connect(tokenPayload.url, tokenPayload.token);
        livekitRoomHandle = room;
        livekitDisconnectButton.disabled = false;
        livekitStatusEl.textContent = `Connected: ${{tokenPayload.url}} · room=${{tokenPayload.room_name}} · identity=${{tokenPayload.identity}} · token_length=${{tokenPayload.token_length}}`;
        await recordTimelineEvent({{ kind: 'livekit_connected', source: 'browser-livekit', command: tokenPayload.room_name }});
        try {{
          const tracks = await LiveKit.createLocalTracks({{ audio: true, video: false }});
          for (const track of tracks) {{
            await room.localParticipant.publishTrack(track);
          }}
          await recordTimelineEvent({{ kind: 'audio_track_published', source: 'browser-livekit', command: tokenPayload.identity }});
        }} catch (mediaError) {{
          livekitStatusEl.textContent = `Connected without microphone: ${{mediaError.message || mediaError}}`;
          await recordTimelineEvent({{
            kind: 'livekit_error',
            source: 'browser-livekit',
            command: `microphone:${{mediaError.message || mediaError}}`
          }});
        }}
      }} catch (error) {{
        livekitRoomHandle = null;
        livekitButton.disabled = false;
        livekitDisconnectButton.disabled = true;
        livekitStatusEl.textContent = error.message || String(error);
        await recordTimelineEvent({{
          kind: 'livekit_error',
          source: 'browser-livekit',
          command: error.message || String(error)
        }});
      }}
    }}

    async function disconnectLiveKitRoom() {{
      if (!livekitRoomHandle) {{
        return;
      }}
      const room = livekitRoomHandle;
      livekitRoomHandle = null;
      livekitDisconnectButton.disabled = true;
      room.disconnect();
    }}

    async function toggleInterruptionDetector() {{
      if (detectorRunning) {{
        stopInterruptionDetector('Detector stopped.');
        return;
      }}
      await startInterruptionDetector(false);
    }}

    async function startInterruptionDetector(useTestTone = false) {{
      if (detectorRunning) {{
        return;
      }}
      detectorRunning = true;
      detectorSawSpeech = false;
      detectorButton.textContent = 'Stop detector';
      detectorStatusEl.textContent = useTestTone ? 'Detector test tone running...' : 'Requesting microphone...';
      try {{
        const AudioContextClass = window.AudioContext || window.webkitAudioContext;
        if (!AudioContextClass) {{
          throw new Error('Web Audio API is unavailable.');
        }}
        detectorContext = new AudioContextClass();
        detectorAnalyser = detectorContext.createAnalyser();
        detectorAnalyser.fftSize = 1024;
        if (useTestTone) {{
          const oscillator = detectorContext.createOscillator();
          const gain = detectorContext.createGain();
          oscillator.type = 'square';
          oscillator.frequency.value = 440;
          gain.gain.value = 0.35;
          oscillator.connect(gain);
          gain.connect(detectorAnalyser);
          oscillator.start();
          detectorSource = oscillator;
          setTimeout(() => stopInterruptionDetector('Detector test complete.'), 900);
        }} else {{
          detectorStream = await navigator.mediaDevices.getUserMedia({{ audio: true, video: false }});
          detectorSource = detectorContext.createMediaStreamSource(detectorStream);
          detectorSource.connect(detectorAnalyser);
        }}
        detectorStatusEl.textContent = 'Listening for interruption.';
        detectorFrame = requestAnimationFrame(sampleInterruptionDetector);
      }} catch (error) {{
        detectorStatusEl.textContent = error.message || String(error);
        stopInterruptionDetector('Detector failed.');
        await recordTimelineEvent({{
          kind: 'livekit_error',
          source: 'browser-interruption-detector',
          command: `detector:${{error.message || error}}`
        }});
      }}
    }}

    async function runDetectorTestBurst() {{
      await startInterruptionDetector(true);
    }}

    async function sampleInterruptionDetector() {{
      if (!detectorRunning || !detectorAnalyser) {{
        return;
      }}
      const samples = new Uint8Array(detectorAnalyser.fftSize);
      detectorAnalyser.getByteTimeDomainData(samples);
      let sum = 0;
      for (const sample of samples) {{
        const normalized = (sample - 128) / 128;
        sum += normalized * normalized;
      }}
      const rms = Math.sqrt(sum / samples.length);
      const percent = Math.min(100, Math.round(rms * 220));
      detectorMeterEl.style.width = `${{percent}}%`;
      if (rms > 0.03 && !detectorSawSpeech) {{
        detectorSawSpeech = true;
        detectorStatusEl.textContent = `Speech activity detected: rms=${{rms.toFixed(3)}}`;
        await recordTimelineEvent({{
          kind: 'speech_started',
          source: 'browser-interruption-detector',
          confidence: Math.min(1, Number((rms * 12).toFixed(2))),
          offset_ms: 0
        }});
      }}
      if (rms > 0.08) {{
        detectorStatusEl.textContent = `Interruption detected: rms=${{rms.toFixed(3)}}`;
        await recordTimelineEvent({{
          kind: 'speech_interrupted',
          source: 'browser-interruption-detector',
          confidence: Math.min(1, Number((rms * 10).toFixed(2))),
          offset_ms: 0
        }});
        stopInterruptionDetector('Interruption recorded.');
        return;
      }}
      detectorFrame = requestAnimationFrame(sampleInterruptionDetector);
    }}

    function stopInterruptionDetector(message) {{
      if (detectorFrame) {{
        cancelAnimationFrame(detectorFrame);
        detectorFrame = null;
      }}
      if (detectorSource && typeof detectorSource.stop === 'function') {{
        detectorSource.stop();
      }}
      if (detectorStream) {{
        detectorStream.getTracks().forEach((track) => track.stop());
      }}
      if (detectorContext && detectorContext.state !== 'closed') {{
        detectorContext.close();
      }}
      detectorRunning = false;
      detectorStream = null;
      detectorSource = null;
      detectorAnalyser = null;
      detectorContext = null;
      detectorButton.textContent = 'Start detector';
      detectorMeterEl.style.width = '0%';
      detectorStatusEl.textContent = message || 'Detector idle.';
    }}

    async function runPresenterCue() {{
      presenterCueButton.disabled = true;
      presenterCueStatusEl.textContent = 'Cue speaking...';
      try {{
        await recordTimelineEvent({{
          kind: 'speech_started',
          source: 'browser-presenter-cue',
          command: 'phase2-local-cue',
          confidence: 1,
          offset_ms: 0
        }});
        await delay(180);
        presenterCueStatusEl.textContent = 'Cue anchor: next';
        await recordTimelineEvent({{
          kind: 'tts_word',
          source: 'browser-presenter-cue',
          token: 'next',
          offset_ms: 180,
          confidence: 1
        }});
        presenterCueStatusEl.textContent = 'Cue complete.';
      }} finally {{
        presenterCueButton.disabled = false;
      }}
    }}

    function resetPresenterCue() {{
      presenterCueStatusEl.textContent = 'Cue idle.';
    }}

    function delay(ms) {{
      return new Promise((resolve) => setTimeout(resolve, ms));
    }}

    async function recordTimelineEvent(payload) {{
      const response = await fetch('/api/timeline-event', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify(payload)
      }});
      const result = await response.json();
      if (result.ok) {{
        renderTimeline(result.timeline);
        if (result.slide_control) {{
          renderSlideControl(result.slide_control);
        }}
      }}
      return result;
    }}

    function connectSlideSocket() {{
      const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
      const socket = new WebSocket(`${{scheme}}://${{window.location.host}}/ws/slides`);
      socket.addEventListener('message', (event) => {{
        applySlideEvent(JSON.parse(event.data));
      }});
    }}

    render(initial);
    connectSlideSocket();
    const startupParams = new URLSearchParams(window.location.search);
    if (startupParams.get('livekit_room')) {{
      livekitRoomEl.value = startupParams.get('livekit_room');
    }}
    if (startupParams.get('livekit_identity')) {{
      livekitIdentityEl.value = startupParams.get('livekit_identity');
    }}
    if (startupParams.get('auto_livekit') === '1') {{
      selectToolTab('audio');
      if (!startupParams.get('livekit_identity')) {{
        livekitIdentityEl.value = `devdefender-browser-smoke-${{Date.now()}}`;
      }}
      setTimeout(() => connectLiveKitRoom(), 250);
    }}
    if (startupParams.get('auto_interruption') === '1') {{
      selectToolTab('audio');
      setTimeout(() => runDetectorTestBurst(), 250);
    }}
    if (startupParams.get('auto_presenter_cue') === '1') {{
      selectToolTab('audio');
      setTimeout(() => runPresenterCue(), 250);
    }}
    if (startupParams.get('auto_meeting') === '1') {{
      setTimeout(() => {{
        window.location.href = `/meeting-test${{window.location.search}}`;
      }}, 150);
    }}
  </script>
</body>
</html>"""


def _meeting_test_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>DevDefender Meeting Test</title>
  <style>
    body { font-family: system-ui, sans-serif; margin: 0; padding: 24px; color: #17202a; background: #f8fafc; }
    main { max-width: 720px; margin: 0 auto; }
    button { border: 0; border-radius: 6px; padding: 10px 14px; background: #0f766e; color: white; font-weight: 700; }
    .status { margin-top: 16px; padding: 12px; border: 1px solid #d7dde6; background: white; border-radius: 6px; }
  </style>
</head>
<body>
  <main>
    <h1>DevDefender Meeting Test</h1>
    <button id="joinButton" type="button">Join and leave</button>
    <div class="status" id="status">Idle.</div>
  </main>
  <script>
    const params = new URLSearchParams(window.location.search);
    const meetingUrl = params.get('meeting_url') || 'local-meeting-test';
    const statusEl = document.getElementById('status');
    document.getElementById('joinButton').addEventListener('click', runMeetingLifecycle);

    async function runMeetingLifecycle() {
      try {
        statusEl.textContent = 'Join started.';
        await recordTimelineEvent('meeting_join_started');
        await delay(160);
        statusEl.textContent = 'Joined.';
        await recordTimelineEvent('meeting_joined');
        await delay(160);
        statusEl.textContent = 'Left.';
        await recordTimelineEvent('meeting_left');
      } catch (error) {
        statusEl.textContent = error.message || String(error);
        await recordTimelineEvent('meeting_error', error.message || String(error));
      }
    }

    async function recordTimelineEvent(kind, fallbackCommand = null) {
      const response = await fetch('/api/timeline-event', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          kind,
          source: 'local-meeting-test',
          command: fallbackCommand || meetingUrl
        })
      });
      const payload = await response.json();
      if (!payload.ok) {
        throw new Error(payload.error || 'Timeline event failed.');
      }
      return payload;
    }

    function delay(ms) {
      return new Promise((resolve) => setTimeout(resolve, ms));
    }

    if (params.get('auto_meeting') === '1') {
      setTimeout(() => runMeetingLifecycle(), 250);
    }
  </script>
</body>
</html>"""


def _webrtc_meeting_test_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>DevDefender WebRTC Meeting Test</title>
  <style>
    body { font-family: system-ui, sans-serif; margin: 0; padding: 24px; color: #17202a; background: #f8fafc; }
    main { max-width: 760px; margin: 0 auto; }
    button { border: 0; border-radius: 6px; padding: 10px 14px; background: #0f766e; color: white; font-weight: 700; }
    .status { margin-top: 16px; padding: 12px; border: 1px solid #d7dde6; background: white; border-radius: 6px; }
    video { width: 320px; max-width: 100%; margin-top: 16px; background: #111827; border-radius: 6px; }
  </style>
</head>
<body>
  <main>
    <h1>DevDefender WebRTC Meeting Test</h1>
    <button id="joinButton" type="button">Join WebRTC test</button>
    <div class="status" id="status">Idle.</div>
    <video id="preview" autoplay muted playsinline></video>
  </main>
  <script>
    const params = new URLSearchParams(window.location.search);
    const meetingUrl = params.get('meeting_url') || 'webrtc-local-test';
    const statusEl = document.getElementById('status');
    const previewEl = document.getElementById('preview');
    let localStream = null;
    let pc1 = null;
    let pc2 = null;
    document.getElementById('joinButton').addEventListener('click', runWebRtcLifecycle);

    async function runWebRtcLifecycle() {
      try {
        statusEl.textContent = 'Join started.';
        await recordTimelineEvent({ kind: 'meeting_join_started', source: 'generic-webrtc-test', command: meetingUrl });
        localStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: true });
        previewEl.srcObject = localStream;
        await recordTimelineEvent({
          kind: 'virtual_audio_ready',
          source: 'generic-webrtc-test',
          command: 'getUserMedia:audio',
          confidence: 1,
          offset_ms: 0
        });
        await recordTimelineEvent({
          kind: 'virtual_video_ready',
          source: 'generic-webrtc-test',
          command: 'getUserMedia:video',
          confidence: 1,
          offset_ms: 0
        });
        await connectLocalPeer(localStream);
        await recordTimelineEvent({
          kind: 'meeting_joined',
          source: 'generic-webrtc-test',
          command: meetingUrl
        });
        await recordTimelineEvent({
          kind: 'media_published',
          source: 'generic-webrtc-test',
          command: 'local-peer-connection',
          confidence: 1,
          offset_ms: 120
        });
        await delay(220);
        await closeMeeting();
        statusEl.textContent = 'Left.';
        await recordTimelineEvent({ kind: 'meeting_left', source: 'generic-webrtc-test', command: meetingUrl });
      } catch (error) {
        statusEl.textContent = error.message || String(error);
        await recordTimelineEvent({
          kind: 'meeting_error',
          source: 'generic-webrtc-test',
          command: error.message || String(error)
        });
      }
    }

    async function connectLocalPeer(stream) {
      pc1 = new RTCPeerConnection();
      pc2 = new RTCPeerConnection();
      pc1.onicecandidate = (event) => event.candidate && pc2.addIceCandidate(event.candidate);
      pc2.onicecandidate = (event) => event.candidate && pc1.addIceCandidate(event.candidate);
      stream.getTracks().forEach((track) => pc1.addTrack(track, stream));
      const offer = await pc1.createOffer();
      await pc1.setLocalDescription(offer);
      await pc2.setRemoteDescription(offer);
      const answer = await pc2.createAnswer();
      await pc2.setLocalDescription(answer);
      await pc1.setRemoteDescription(answer);
      await waitForConnection(pc1);
    }

    function waitForConnection(peer) {
      if (peer.connectionState === 'connected') {
        return Promise.resolve();
      }
      return new Promise((resolve, reject) => {
        const timeout = setTimeout(() => reject(new Error('WebRTC connection timed out.')), 5000);
        peer.addEventListener('connectionstatechange', () => {
          if (peer.connectionState === 'connected') {
            clearTimeout(timeout);
            resolve();
          }
          if (peer.connectionState === 'failed') {
            clearTimeout(timeout);
            reject(new Error('WebRTC connection failed.'));
          }
        });
      });
    }

    async function closeMeeting() {
      if (pc1) {
        pc1.close();
        pc1 = null;
      }
      if (pc2) {
        pc2.close();
        pc2 = null;
      }
      if (localStream) {
        localStream.getTracks().forEach((track) => track.stop());
        localStream = null;
      }
      previewEl.srcObject = null;
    }

    async function recordTimelineEvent(payload) {
      const response = await fetch('/api/timeline-event', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const result = await response.json();
      if (!result.ok) {
        throw new Error(result.error || 'Timeline event failed.');
      }
      return result;
    }

    function delay(ms) {
      return new Promise((resolve) => setTimeout(resolve, ms));
    }

    if (params.get('auto_webrtc_meeting') === '1') {
      setTimeout(() => runWebRtcLifecycle(), 250);
    }
  </script>
</body>
</html>"""


def _zoom_discovery_test_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>DevDefender Zoom Discovery Test</title>
  <style>
    body { font-family: system-ui, sans-serif; margin: 0; padding: 24px; color: #17202a; background: #f8fafc; }
    main { max-width: 760px; margin: 0 auto; }
    label { display: block; margin-bottom: 8px; font-weight: 700; }
    input { box-sizing: border-box; width: 100%; border: 1px solid #cbd5e1; border-radius: 6px; padding: 10px 12px; }
    button { border: 0; border-radius: 6px; padding: 10px 14px; background: #0f766e; color: white; font-weight: 700; }
    .controls { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 16px; }
    .secondary { background: #334155; }
    .status { margin-top: 16px; padding: 12px; border: 1px solid #d7dde6; background: white; border-radius: 6px; }
  </style>
</head>
<body>
  <main>
    <h1>DevDefender Zoom Discovery Test</h1>
    <label for="displayName">Display name</label>
    <input id="displayName" name="displayName" autocomplete="off" value="DevDefender Tester">
    <div class="controls" aria-label="Zoom-like prejoin controls">
      <button id="joinButton" type="button" data-zoom-control="join">Join from browser</button>
      <button id="audioToggle" class="secondary" type="button" data-zoom-control="audio">Mute audio</button>
      <button id="videoToggle" class="secondary" type="button" data-zoom-control="video">Stop video</button>
      <button id="leaveButton" class="secondary" type="button" data-zoom-control="leave">Leave</button>
    </div>
    <div class="status" id="status">Idle.</div>
  </main>
  <script>
    const params = new URLSearchParams(window.location.search);
    const zoomUrl = params.get('zoom_url') || 'https://zoom.us/wc/join/123456789?pwd=local-secret';
    const statusEl = document.getElementById('status');
    const controlIds = ['displayName', 'joinButton', 'audioToggle', 'videoToggle', 'leaveButton'];
    document.getElementById('joinButton').addEventListener('click', runZoomDiscovery);
    document.getElementById('leaveButton').addEventListener('click', () => recordTimelineEvent({
      kind: 'meeting_left',
      source: 'zoom-web-discovery',
      command: 'zoom-discovery-complete'
    }));

    async function runZoomDiscovery() {
      try {
        statusEl.textContent = 'Zoom Web discovery started.';
        await recordTimelineEvent({
          kind: 'meeting_join_started',
          source: 'zoom-web-discovery',
          command: zoomUrl
        });
        await delay(120);
        const missingControls = controlIds.filter((id) => !document.getElementById(id));
        if (missingControls.length) {
          throw new Error('Zoom discovery controls missing.');
        }
        statusEl.textContent = 'Zoom prejoin controls detected.';
        await recordTimelineEvent({
          kind: 'meeting_joined',
          source: 'zoom-web-discovery',
          command: 'zoom-prejoin-detected',
          confidence: 1,
          offset_ms: 0
        });
        await delay(120);
        statusEl.textContent = 'Zoom discovery complete.';
        await recordTimelineEvent({
          kind: 'meeting_left',
          source: 'zoom-web-discovery',
          command: 'zoom-discovery-complete'
        });
      } catch (error) {
        statusEl.textContent = error.message || String(error);
        await recordTimelineEvent({
          kind: 'meeting_error',
          source: 'zoom-web-discovery',
          command: error.message || String(error)
        });
      }
    }

    async function recordTimelineEvent(payload) {
      const response = await fetch('/api/timeline-event', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const result = await response.json();
      if (!result.ok) {
        throw new Error(result.error || 'Timeline event failed.');
      }
      return result;
    }

    function delay(ms) {
      return new Promise((resolve) => setTimeout(resolve, ms));
    }

    if (params.get('auto_zoom_discovery') === '1') {
      setTimeout(() => runZoomDiscovery(), 250);
    }
  </script>
</body>
</html>"""


if __name__ == "__main__":
    try:
        main()
    except OSError as exc:
        print(f"Unable to start Phase 1 room: {exc}", file=sys.stderr)
        raise
