from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from devdefender_lab.meeting import (
    MEETING_SOURCE,
    contains_forbidden_meeting_artifact_fields,
    redact_meeting_url,
)
from scripts.room_acceptance_smoke import managed_room_report, start_managed_room, stop_managed_room


DEFAULT_ROOM_URL = "http://127.0.0.1:8765"
DEFAULT_REPORT_PATH = ROOT / "artifacts" / "meeting_automation_smoke.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Phase 3A local meeting automation shell.")
    parser.add_argument("--room-url", default=DEFAULT_ROOM_URL, help="Running DevDefender room URL.")
    parser.add_argument("--managed-room", action="store_true", help="Start and stop a local mock room for this run.")
    parser.add_argument("--repo", default="sample_repo", help="Repository path used when --managed-room starts a room.")
    parser.add_argument("--slidev-port", type=int, default=3030, help="Slidev port used by --managed-room.")
    parser.add_argument("--startup-timeout", type=float, default=45.0, help="Seconds to wait for a managed room.")
    parser.add_argument("--browser", help="Path to Edge/Chrome/Chromium. Defaults to auto-discovery.")
    parser.add_argument("--timeout", type=float, default=20.0, help="Seconds to wait for meeting timeline events.")
    parser.add_argument("--out", type=Path, default=DEFAULT_REPORT_PATH, help="Path for the JSON smoke report.")
    args = parser.parse_args()

    managed_room: dict[str, object] | None = None
    try:
        if args.managed_room:
            managed_room = start_managed_room(
                room_url=args.room_url,
                repo=args.repo,
                slidev_port=args.slidev_port,
                startup_timeout=args.startup_timeout,
            )
        report = run_smoke(args.room_url.rstrip("/"), args.out, args.browser, args.timeout)
    except Exception as exc:
        report = {"ok": False, "error": str(exc)}
    finally:
        if managed_room:
            shutdown = stop_managed_room(managed_room)
            report["managed_room"] = managed_room_report(managed_room, shutdown)
            report["ok"] = bool(report.get("ok")) and bool(shutdown.get("ok"))

    write_report(report, args.out)
    if not report.get("ok"):
        print(json.dumps(report, indent=2, ensure_ascii=False), file=sys.stderr)
        return 1

    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["ok"] else 1


def run_smoke(room_url: str, out: Path, browser: str | None = None, timeout: float = 20.0) -> dict[str, object]:
    browser_path = find_browser(browser)
    _post_json(
        f"{room_url}/api/timeline-event",
        {
            "kind": "manual_voice_command",
            "command": "goto",
            "slide_index": 1,
            "source": "meeting-automation-smoke",
        },
    )
    before = _get_json(f"{room_url}/api/timeline-events")
    before_events = _events(before)
    target = local_meeting_test_url(room_url)

    profile_dir_obj = tempfile.TemporaryDirectory(prefix="devdefender-meeting-profile-", ignore_cleanup_errors=True)
    profile_dir = Path(profile_dir_obj.name)
    process = subprocess.Popen(
        [
            browser_path,
            "--headless=new",
            "--disable-gpu",
            "--disable-background-mode",
            "--disable-background-networking",
            "--no-first-run",
            "--disable-default-apps",
            f"--user-data-dir={profile_dir}",
            "--window-size=1280,900",
            target,
        ],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    used_terminate = False
    used_kill = False
    try:
        timeline = wait_for_meeting_events(room_url, len(before_events), timeout)
    finally:
        if process.poll() is None:
            used_terminate = True
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                used_kill = True
                process.kill()
                process.wait(timeout=5)
        cleanup_browser_profile(profile_dir_obj, profile_dir)

    report = build_report(
        browser_path=browser_path,
        room_url=room_url,
        target_url=target,
        before_events=before_events,
        timeline=timeline,
        browser_return_code=process.returncode,
        used_terminate=used_terminate,
        used_kill=used_kill,
        profile_dir=profile_dir,
    )
    report["report_path"] = str(out)
    write_report(report, out)
    return report


def build_report(
    *,
    browser_path: str,
    room_url: str,
    target_url: str,
    before_events: list[dict[str, object]],
    timeline: dict[str, object],
    browser_return_code: int | None = None,
    used_terminate: bool = False,
    used_kill: bool = False,
    profile_dir: Path | None = None,
) -> dict[str, object]:
    new_events = _events(timeline)[len(before_events) :]
    kinds = [str(event.get("kind")) for event in new_events]
    joined = _last_event(new_events, "meeting_joined")
    left = _last_event(new_events, "meeting_left")
    join_started = _last_event(new_events, "meeting_join_started")
    error = _last_event(new_events, "meeting_error")
    source_ok = all(_event_source(event) == MEETING_SOURCE for event in new_events if str(event.get("kind")).startswith("meeting_"))
    profile_removed = True if profile_dir is None else not profile_dir.exists()
    checks = {
        "timeline_reachable": bool(timeline),
        "meeting_join_started_recorded": join_started is not None,
        "meeting_joined_recorded": joined is not None,
        "meeting_left_recorded": left is not None,
        "no_meeting_error": error is None,
        "meeting_source_used": source_ok,
        "target_url_redacted": "token=" not in redact_meeting_url(target_url).lower(),
        "no_forbidden_artifact_fields": not contains_forbidden_meeting_artifact_fields(new_events),
        "browser_process_exited": browser_return_code is not None,
        "browser_profile_removed": profile_removed,
        "browser_not_killed": used_kill is False,
    }
    return {
        "ok": all(checks.values()),
        "checks": checks,
        "room_url": room_url,
        "target_url": redact_meeting_url(target_url),
        "browser": browser_path,
        "browser_return_code": browser_return_code,
        "used_terminate": used_terminate,
        "used_kill": used_kill,
        "new_event_count": len(new_events),
        "new_event_kinds": kinds,
        "join_started_event": join_started,
        "joined_event": joined,
        "left_event": left,
        "last_meeting_error": error,
    }


def wait_for_meeting_events(room_url: str, baseline_count: int, timeout: float) -> dict[str, object]:
    deadline = time.monotonic() + timeout
    last_timeline: dict[str, object] = {}
    while time.monotonic() < deadline:
        last_timeline = _get_json(f"{room_url}/api/timeline-events")
        new_events = _events(last_timeline)[baseline_count:]
        if _last_event(new_events, "meeting_joined") and _last_event(new_events, "meeting_left"):
            return last_timeline
        time.sleep(0.4)
    return last_timeline


def local_meeting_test_url(room_url: str) -> str:
    parsed = urllib.parse.urlparse(room_url)
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    query.append(("auto_meeting", "1"))
    query.append(("meeting_url", "https://meeting.local/devdefender?token=redacted-test-token"))
    return urllib.parse.urlunparse(parsed._replace(query=urllib.parse.urlencode(query)))


def write_report(report: dict[str, object], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def cleanup_browser_profile(profile_dir_obj: tempfile.TemporaryDirectory, profile_dir: Path) -> None:
    for _ in range(10):
        profile_dir_obj.cleanup()
        if not profile_dir.exists():
            return
        time.sleep(0.5)
    shutil.rmtree(profile_dir, ignore_errors=True)


def find_browser(explicit_browser: str | None = None) -> str:
    candidates: list[str] = []
    if explicit_browser:
        candidates.append(explicit_browser)
    if os.getenv("DEVDEFENDER_BROWSER"):
        candidates.append(os.environ["DEVDEFENDER_BROWSER"])

    candidates.extend(
        [
            "msedge",
            "microsoft-edge",
            "google-chrome",
            "chrome",
            "chromium",
            "chromium-browser",
        ]
    )

    program_files = [os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles")]
    for base in program_files:
        if not base:
            continue
        candidates.extend(
            [
                str(Path(base) / "Microsoft" / "Edge" / "Application" / "msedge.exe"),
                str(Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe"),
            ]
        )

    for candidate in candidates:
        resolved = shutil.which(candidate) or candidate
        if Path(resolved).exists():
            return resolved

    raise RuntimeError("No Edge/Chrome/Chromium browser found. Pass --browser or set DEVDEFENDER_BROWSER.")


def _last_event(events: list[dict[str, object]], kind: str) -> dict[str, object] | None:
    for event in reversed(events):
        if event.get("kind") == kind:
            return event
    return None


def _event_source(event: dict[str, object] | None) -> object:
    return event.get("source") if isinstance(event, dict) else None


def _events(timeline: dict[str, object]) -> list[dict[str, object]]:
    events = timeline.get("events")
    return events if isinstance(events, list) else []


def _get_json(url: str) -> dict[str, object]:
    with urllib.request.urlopen(url, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


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


if __name__ == "__main__":
    raise SystemExit(main())
