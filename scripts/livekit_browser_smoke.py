from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOM_URL = "http://127.0.0.1:8765"
DEFAULT_REPORT_PATH = ROOT / "artifacts" / "livekit_browser_smoke.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify browser LiveKit connect/publish events reach the room timeline.")
    parser.add_argument("--room-url", default=DEFAULT_ROOM_URL, help="Running DevDefender room URL.")
    parser.add_argument("--browser", help="Path to Edge/Chrome/Chromium. Defaults to auto-discovery.")
    parser.add_argument("--timeout", type=float, default=35.0, help="Seconds to wait for browser timeline events.")
    parser.add_argument("--out", type=Path, default=DEFAULT_REPORT_PATH, help="Path for the JSON smoke report.")
    args = parser.parse_args()

    try:
        report = run_smoke(args.room_url.rstrip("/"), args.out, args.browser, args.timeout)
    except Exception as exc:
        report = {"ok": False, "error": str(exc)}
        write_report(report, args.out)
        print(json.dumps(report, indent=2, ensure_ascii=False), file=sys.stderr)
        return 1

    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["ok"] else 1


def run_smoke(room_url: str, out: Path, browser: str | None = None, timeout: float = 35.0) -> dict[str, object]:
    browser_path = find_browser(browser)
    before = _get_json(f"{room_url}/api/timeline-events")
    before_events = _events(before)
    target = browser_auto_livekit_url(room_url)

    process = subprocess.Popen(
        [
            browser_path,
            "--headless=new",
            "--disable-gpu",
            "--use-fake-ui-for-media-stream",
            "--use-fake-device-for-media-stream",
            "--autoplay-policy=no-user-gesture-required",
            "--window-size=1280,900",
            target,
        ],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        timeline = wait_for_livekit_events(room_url, len(before_events), timeout)
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()

    report = build_report(browser_path, room_url, target, before_events, timeline)
    report["report_path"] = str(out)
    write_report(report, out)
    return report


def build_report(
    browser_path: str,
    room_url: str,
    target_url: str,
    before_events: list[dict[str, object]],
    timeline: dict[str, object],
) -> dict[str, object]:
    new_events = _events(timeline)[len(before_events) :]
    kinds = [str(event.get("kind")) for event in new_events]
    connected = _last_event(new_events, "livekit_connected")
    published = _last_event(new_events, "audio_track_published")
    error = _last_event(new_events, "livekit_error")
    connected_index = _last_index(kinds, "livekit_connected")
    last_error_index = _last_index(kinds, "livekit_error")
    checks = {
        "timeline_reachable": bool(timeline),
        "livekit_connected_recorded": connected is not None,
        "audio_track_published_recorded": published is not None,
        "no_livekit_error_after_connect": connected_index is not None
        and (last_error_index is None or last_error_index < connected_index),
    }
    return {
        "ok": all(checks.values()),
        "checks": checks,
        "room_url": room_url,
        "target_url": target_url,
        "browser": browser_path,
        "new_event_count": len(new_events),
        "new_event_kinds": kinds,
        "connected_event": connected,
        "published_event": published,
        "last_livekit_error": error,
    }


def wait_for_livekit_events(room_url: str, baseline_count: int, timeout: float) -> dict[str, object]:
    deadline = time.monotonic() + timeout
    last_timeline: dict[str, object] = {}
    while time.monotonic() < deadline:
        last_timeline = _get_json(f"{room_url}/api/timeline-events")
        new_events = _events(last_timeline)[baseline_count:]
        if _last_event(new_events, "livekit_connected") and _last_event(new_events, "audio_track_published"):
            return last_timeline
        time.sleep(0.5)
    return last_timeline


def browser_auto_livekit_url(room_url: str) -> str:
    parsed = urllib.parse.urlparse(room_url)
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    query.append(("auto_livekit", "1"))
    return urllib.parse.urlunparse(parsed._replace(query=urllib.parse.urlencode(query)))


def write_report(report: dict[str, object], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


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


def _last_index(values: list[str], target: str) -> int | None:
    for index in range(len(values) - 1, -1, -1):
        if values[index] == target:
            return index
    return None


def _events(timeline: dict[str, object]) -> list[dict[str, object]]:
    events = timeline.get("events")
    return events if isinstance(events, list) else []


def _get_json(url: str) -> dict[str, object]:
    with urllib.request.urlopen(url, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())
