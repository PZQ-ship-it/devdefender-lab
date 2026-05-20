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
DEFAULT_REPORT_PATH = ROOT / "artifacts" / "browser_interruption_smoke.json"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify the browser interruption detector records timeline events without saving audio."
    )
    parser.add_argument("--room-url", default=DEFAULT_ROOM_URL, help="Running DevDefender room URL.")
    parser.add_argument("--browser", help="Path to Edge/Chrome/Chromium. Defaults to auto-discovery.")
    parser.add_argument("--timeout", type=float, default=20.0, help="Seconds to wait for detector timeline events.")
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


def run_smoke(room_url: str, out: Path, browser: str | None = None, timeout: float = 20.0) -> dict[str, object]:
    browser_path = find_browser(browser)
    before = _get_json(f"{room_url}/api/timeline-events")
    before_events = _events(before)
    target = browser_auto_interruption_url(room_url)

    process = subprocess.Popen(
        [
            browser_path,
            "--headless=new",
            "--disable-gpu",
            "--autoplay-policy=no-user-gesture-required",
            "--window-size=1280,900",
            target,
        ],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        timeline = wait_for_interruption_events(room_url, len(before_events), timeout)
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
    speech_started = _last_event(new_events, "speech_started")
    speech_interrupted = _last_event(new_events, "speech_interrupted")
    interruption = timeline.get("interruption") if isinstance(timeline.get("interruption"), dict) else {}
    checks = {
        "timeline_reachable": bool(timeline),
        "speech_started_recorded": speech_started is not None,
        "speech_interrupted_recorded": speech_interrupted is not None,
        "detector_source_used": _event_source(speech_interrupted) == "browser-interruption-detector",
        "interruption_active": interruption.get("active") is True,
        "no_audio_artifact_fields": _no_audio_artifact_fields(new_events),
    }
    return {
        "ok": all(checks.values()),
        "checks": checks,
        "room_url": room_url,
        "target_url": target_url,
        "browser": browser_path,
        "new_event_count": len(new_events),
        "new_event_kinds": kinds,
        "speech_started_event": speech_started,
        "speech_interrupted_event": speech_interrupted,
        "interruption": interruption,
    }


def wait_for_interruption_events(room_url: str, baseline_count: int, timeout: float) -> dict[str, object]:
    deadline = time.monotonic() + timeout
    last_timeline: dict[str, object] = {}
    while time.monotonic() < deadline:
        last_timeline = _get_json(f"{room_url}/api/timeline-events")
        new_events = _events(last_timeline)[baseline_count:]
        if _last_event(new_events, "speech_started") and _last_event(new_events, "speech_interrupted"):
            return last_timeline
        time.sleep(0.4)
    return last_timeline


def browser_auto_interruption_url(room_url: str) -> str:
    parsed = urllib.parse.urlparse(room_url)
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    query.append(("auto_interruption", "1"))
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


def _event_source(event: dict[str, object] | None) -> object:
    return event.get("source") if isinstance(event, dict) else None


def _no_audio_artifact_fields(events: list[dict[str, object]]) -> bool:
    forbidden_keys = {"audio", "audio_path", "audio_url", "transcript", "raw_audio"}
    for event in events:
        if forbidden_keys & set(event):
            return False
        for value in event.values():
            if isinstance(value, str) and ("data:audio" in value or ".wav" in value or ".mp3" in value):
                return False
    return True


def _events(timeline: dict[str, object]) -> list[dict[str, object]]:
    events = timeline.get("events")
    return events if isinstance(events, list) else []


def _get_json(url: str) -> dict[str, object]:
    with urllib.request.urlopen(url, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())
