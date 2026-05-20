from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOM_URL = "http://127.0.0.1:8765"
DEFAULT_REPORT_PATH = ROOT / "artifacts" / "room_acceptance_smoke.json"
ROOM_SHUTDOWN_TOKEN_ENV = "DEVDEFENDER_ROOM_SHUTDOWN_TOKEN"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run serial Phase 2 room acceptance smokes.")
    parser.add_argument("--room-url", default=DEFAULT_ROOM_URL, help="Running DevDefender room URL.")
    parser.add_argument("--managed-room", action="store_true", help="Start and stop a local mock room for this run.")
    parser.add_argument("--repo", default="sample_repo", help="Repository path used when --managed-room starts a room.")
    parser.add_argument("--slidev-port", type=int, default=3030, help="Slidev port used by --managed-room.")
    parser.add_argument("--startup-timeout", type=float, default=45.0, help="Seconds to wait for a managed room.")
    parser.add_argument("--skip-visual", action="store_true", help="Skip browser screenshot visual smoke.")
    parser.add_argument(
        "--include-livekit-token",
        action="store_true",
        help="Also request and validate a browser LiveKit token from the room API.",
    )
    parser.add_argument(
        "--include-livekit-browser",
        action="store_true",
        help="Also open a headless browser, connect to LiveKit, and verify timeline events.",
    )
    parser.add_argument(
        "--include-evidence-chain",
        action="store_true",
        help="Also verify evidence packet pointers propagated into Issue/refinement artifacts.",
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_REPORT_PATH, help="Path for the JSON acceptance report.")
    args = parser.parse_args()

    managed_room: dict[str, object] | None = None
    report: dict[str, object]
    results: list[dict[str, object]] = []
    try:
        if args.managed_room:
            managed_room = start_managed_room(
                room_url=args.room_url,
                repo=args.repo,
                slidev_port=args.slidev_port,
                startup_timeout=args.startup_timeout,
            )

        sequence = build_sequence(
            room_url=args.room_url,
            skip_visual=args.skip_visual,
            include_livekit_token=args.include_livekit_token,
            include_livekit_browser=args.include_livekit_browser,
            include_evidence_chain=args.include_evidence_chain,
        )
        results = [run_step(name, command) for name, command in sequence]
        report = build_report(results)
    except Exception as exc:
        report = {"ok": False, "checks": {}, "results": results, "error": str(exc)}
    finally:
        if managed_room:
            shutdown = stop_managed_room(managed_room)
            report["managed_room"] = managed_room_report(managed_room, shutdown)
            report["ok"] = bool(report.get("ok")) and bool(shutdown.get("ok"))

    report["report_path"] = str(args.out)
    write_report(report, args.out)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if not report["ok"]:
        raise SystemExit(1)


def run_step(name: str, command: list[str]) -> dict[str, object]:
    script = ROOT / "scripts" / command[0]
    process = subprocess.run(
        [sys.executable, str(script), *command[1:]],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=180,
    )
    payload = _parse_json_output(process.stdout)
    return {
        "name": name,
        "ok": process.returncode == 0 and bool(payload.get("ok")),
        "return_code": process.returncode,
        "payload": payload,
        "stderr": process.stderr.strip(),
    }


def start_managed_room(
    *, room_url: str, repo: str, slidev_port: int, startup_timeout: float
) -> dict[str, object]:
    host, port = _parse_room_url(room_url)
    token = secrets.token_urlsafe(24)
    stdout_path = ROOT / "artifacts" / "room_acceptance_managed_room_stdout.log"
    stderr_path = ROOT / "artifacts" / "room_acceptance_managed_room_stderr.log"
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    command = _managed_room_command(repo=repo, host=host, port=port, slidev_port=slidev_port)
    env = os.environ.copy()
    env["DEVDEFENDER_LLM_MODE"] = "mock"
    env["DEVDEFENDER_AGENT_BACKEND"] = "mock"
    env[ROOM_SHUTDOWN_TOKEN_ENV] = token

    with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open("w", encoding="utf-8") as stderr:
        process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=stdout, stderr=stderr, text=True)

    managed_room: dict[str, object] = {
        "process": process,
        "pid": process.pid,
        "room_url": room_url,
        "repo": repo,
        "room_port": port,
        "slidev_port": slidev_port,
        "stdout": str(stdout_path),
        "stderr": str(stderr_path),
        "shutdown_token": token,
        "command": command,
    }
    try:
        wait_for_room(room_url, process, startup_timeout)
    except Exception:
        stop_managed_room(managed_room)
        raise
    return managed_room


def stop_managed_room(managed_room: dict[str, object], timeout: float = 20.0) -> dict[str, object]:
    process = managed_room["process"]
    assert isinstance(process, subprocess.Popen)
    already_exited = process.poll() is not None
    shutdown_request_ok = False
    shutdown_payload: dict[str, object] = {}
    used_terminate = False
    used_kill = False

    if not already_exited:
        try:
            payload = _post_json(
                f"{str(managed_room['room_url']).rstrip('/')}/api/shutdown",
                {"token": str(managed_room["shutdown_token"])},
            )
            shutdown_payload = payload
            shutdown_request_ok = bool(payload.get("ok"))
        except Exception as exc:
            shutdown_payload = {"ok": False, "error": str(exc)}

    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        used_terminate = True
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            used_kill = True
            process.kill()
            process.wait(timeout=5)
    lingering_ports = _listening_ports([int(managed_room["room_port"]), int(managed_room["slidev_port"])])

    return {
        "ok": process.returncode is not None
        and (already_exited or shutdown_request_ok)
        and not used_kill
        and not lingering_ports,
        "already_exited": already_exited,
        "shutdown_request_ok": shutdown_request_ok,
        "shutdown_payload_ok": shutdown_payload.get("ok"),
        "used_terminate": used_terminate,
        "used_kill": used_kill,
        "return_code": process.returncode,
        "lingering_ports": lingering_ports,
    }


def managed_room_report(managed_room: dict[str, object], shutdown: dict[str, object]) -> dict[str, object]:
    return {
        "pid": managed_room["pid"],
        "room_url": managed_room["room_url"],
        "repo": managed_room["repo"],
        "room_port": managed_room["room_port"],
        "slidev_port": managed_room["slidev_port"],
        "stdout": managed_room["stdout"],
        "stderr": managed_room["stderr"],
        "command": managed_room["command"],
        "shutdown": shutdown,
    }


def wait_for_room(room_url: str, process: subprocess.Popen, timeout: float) -> dict[str, object]:
    deadline = time.monotonic() + timeout
    last_error = ""
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Managed room exited before startup completed: {process.returncode}")
        try:
            payload = _get_json(f"{room_url.rstrip('/')}/api/session")
            if payload.get("thread_id"):
                return payload
        except Exception as exc:
            last_error = str(exc)
        time.sleep(0.5)
    raise TimeoutError(f"Timed out waiting for managed room at {room_url}: {last_error}")


def build_sequence(
    *,
    room_url: str,
    skip_visual: bool = False,
    include_livekit_token: bool = False,
    include_livekit_browser: bool = False,
    include_evidence_chain: bool = False,
) -> list[tuple[str, list[str]]]:
    sequence = [
        ("slide_sync", ["slide_sync_smoke.py", "--room-url", room_url]),
        ("tts_anchor", ["tts_anchor_smoke.py", "--room-url", room_url]),
        ("presenter_cue", ["presenter_cue_smoke.py", "--room-url", room_url]),
        ("interruption", ["interruption_smoke.py", "--room-url", room_url]),
        ("browser_interruption", ["browser_interruption_smoke.py", "--room-url", room_url]),
        ("audio_provider", ["audio_provider_smoke.py", "--room-url", room_url]),
    ]
    if not skip_visual:
        sequence.append(("visual", ["room_visual_smoke.py", "--room-url", room_url]))
    if include_livekit_token:
        sequence.append(("livekit_token", ["livekit_token_smoke.py", "--room-url", room_url]))
    if include_livekit_browser:
        sequence.append(("livekit_browser", ["livekit_browser_smoke.py", "--room-url", room_url]))
    sequence.append(("room_replay", ["room_replay_smoke.py"]))
    sequence.append(("evidence_packet", ["evidence_packet_smoke.py"]))
    if include_evidence_chain:
        sequence.append(("evidence_chain", ["evidence_chain_smoke.py"]))
    sequence.append(("artifact_secret", ["artifact_secret_smoke.py"]))
    return sequence


def build_report(results: list[dict[str, object]]) -> dict[str, object]:
    checks = {str(result["name"]): bool(result.get("ok")) for result in results}
    return {
        "ok": all(checks.values()),
        "checks": checks,
        "results": results,
    }


def write_report(report: dict[str, object], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _parse_json_output(stdout: str) -> dict[str, object]:
    text = stdout.strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise


def _managed_room_command(*, repo: str, host: str, port: int, slidev_port: int) -> list[str]:
    return [
        sys.executable,
        "-m",
        "devdefender_lab.room",
        "--repo",
        repo,
        "--mock",
        "--host",
        host,
        "--port",
        str(port),
        "--slidev-port",
        str(slidev_port),
    ]


def _parse_room_url(room_url: str) -> tuple[str, int]:
    parsed = urllib.parse.urlparse(room_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.port is None:
        raise ValueError("--managed-room requires --room-url with http(s), host, and explicit port.")
    return parsed.hostname, parsed.port


def _get_json(url: str) -> dict[str, object]:
    with urllib.request.urlopen(url, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def _post_json(url: str, payload: dict[str, object]) -> dict[str, object]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def _listening_ports(ports: list[int]) -> list[int]:
    if os.name != "nt":
        return []
    joined_ports = ",".join(str(port) for port in ports)
    command = [
        "powershell",
        "-NoProfile",
        "-Command",
        "$ports = @(" + joined_ports + "); "
        "Get-NetTCPConnection -ErrorAction SilentlyContinue | "
        "Where-Object { $_.State -eq 'Listen' -and $ports -contains $_.LocalPort } | "
        "Select-Object -ExpandProperty LocalPort -Unique",
    ]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=10, check=False)
    if completed.returncode != 0:
        return []
    found: list[int] = []
    for line in completed.stdout.splitlines():
        line = line.strip()
        if line.isdigit():
            found.append(int(line))
    return sorted(found)


if __name__ == "__main__":
    main()
