from __future__ import annotations

import argparse
import json
import os
import shutil
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
from devdefender_lab.workflow import DefenseState, resume_phase1, start_phase1


class Phase1Room:
    def __init__(self, settings: Settings, repo_path: Path) -> None:
        self.settings = settings
        self.repo_path = repo_path
        self.lock = threading.Lock()
        self.session = start_phase1(settings, repo_path)
        self.state: DefenseState | None = None
        self.last_error: str | None = None
        self.slidev_process: subprocess.Popen | None = None

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
        self.slidev_process = subprocess.Popen(
            command,
            cwd=Path.cwd(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )

    def stop_slidev(self) -> None:
        if self.slidev_process and self.slidev_process.poll() is None:
            self.slidev_process.terminate()

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
        if parsed.path == "/api/session":
            self._send_json(self.room.summary())
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/api/feedback":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8")
        feedback = self._feedback_from_body(raw)
        self._send_json(self.room.submit_feedback(feedback))

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
    h1 {{
      margin: 0;
      font-size: 18px;
      font-weight: 720;
      letter-spacing: 0;
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
      display: grid;
      grid-template-rows: auto auto 1fr;
      gap: 14px;
      padding: 16px;
      overflow: auto;
      border-left: 1px solid var(--line);
      background: var(--panel);
    }}
    .metrics {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
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
    .error {{ color: var(--danger); font-weight: 700; }}
    @media (max-width: 860px) {{
      header {{ height: auto; min-height: 56px; align-items: flex-start; flex-direction: column; padding: 12px 14px; }}
      main {{ height: auto; min-height: calc(100vh - 80px); grid-template-columns: 1fr; }}
      iframe {{ height: 56vh; min-height: 360px; }}
      aside {{ border-left: 0; border-top: 1px solid var(--line); }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>DevDefender Phase 1</h1>
    <div class="status" id="status">waiting</div>
  </header>
  <main>
    <iframe id="slides" src="{summary['slidev_url']}" title="Slidev defense deck"></iframe>
    <aside>
      <section class="metrics">
        <div class="metric"><strong id="nodeCount">0</strong><span>nodes</span></div>
        <div class="metric"><strong id="edgeCount">0</strong><span>edges</span></div>
      </section>
      <section class="block">
        <div class="label">thread</div>
        <div class="path" id="threadId"></div>
        <div class="label" style="margin-top:8px">graph</div>
        <div class="path" id="graphPath"></div>
      </section>
      <section class="block">
        <form id="feedbackForm">
          <label class="label" for="feedback">reviewer feedback</label>
          <textarea id="feedback" name="feedback">Payment capture looks risky. Explain why invalid amounts cannot be captured, then create an issue if evidence is weak.</textarea>
          <button id="submitButton" type="submit">Submit Feedback</button>
        </form>
        <div id="result"></div>
      </section>
    </aside>
  </main>
  <script>
    const initial = {initial_json};
    const statusEl = document.getElementById('status');
    const resultEl = document.getElementById('result');
    const submitButton = document.getElementById('submitButton');
    const form = document.getElementById('feedbackForm');

    function render(data) {{
      statusEl.textContent = data.status;
      document.getElementById('nodeCount').textContent = data.node_count;
      document.getElementById('edgeCount').textContent = data.edge_count;
      document.getElementById('threadId').textContent = data.thread_id;
      document.getElementById('graphPath').textContent = data.graph_path;
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

    render(initial);
  </script>
</body>
</html>"""


if __name__ == "__main__":
    try:
        main()
    except OSError as exc:
        print(f"Unable to start Phase 1 room: {exc}", file=sys.stderr)
        raise
