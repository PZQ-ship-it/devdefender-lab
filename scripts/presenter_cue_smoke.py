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
DEFAULT_REPORT_PATH = ROOT / "artifacts" / "presenter_cue_smoke.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify browser presenter cue anchors drive slide replay.")
    parser.add_argument("--room-url", default=DEFAULT_ROOM_URL, help="Running DevDefender room URL.")
    parser.add_argument("--browser", help="Path to Edge/Chrome/Chromium. Defaults to auto-discovery.")
    parser.add_argument("--timeout", type=float, default=20.0, help="Seconds to wait for cue timeline events.")
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
    baseline_timeline = _get_json(f"{room_url}/api/timeline-events")
    baseline_slides = _get_json(f"{room_url}/api/slide-events")
    target = browser_auto_presenter_cue_url(room_url)

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
        timeline, slides = wait_for_presenter_cue(room_url, len(_events(baseline_timeline)), timeout)
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()

    report = build_report(browser_path, room_url, target, baseline_timeline, baseline_slides, timeline, slides)
    report["report_path"] = str(out)
    write_report(report, out)
    return report


def build_report(
    browser_path: str,
    room_url: str,
    target_url: str,
    baseline_timeline: dict[str, object],
    baseline_slides: dict[str, object],
    timeline: dict[str, object],
    slides: dict[str, object],
) -> dict[str, object]:
    baseline_events = _events(baseline_timeline)
    new_events = _events(timeline)[len(baseline_events) :]
    kinds = [str(event.get("kind")) for event in new_events]
    speech_started = _last_event(new_events, "speech_started")
    tts_word = _last_event(new_events, "tts_word")
    mapped_slide = _last_source_event(_events(slides), "timeline:browser-presenter-cue")
    baseline_slide = baseline_slides.get("current_slide_index")
    expected_slide = baseline_slide + 1 if isinstance(baseline_slide, int) else None
    current_slide = slides.get("current_slide_index")
    checks = {
        "timeline_reachable": bool(timeline),
        "speech_started_recorded": _event_source(speech_started) == "browser-presenter-cue",
        "tts_anchor_recorded": _event_source(tts_word) == "browser-presenter-cue" and tts_word.get("token") == "next"
        if isinstance(tts_word, dict)
        else False,
        "mapped_slide_recorded": isinstance(mapped_slide, dict) and mapped_slide.get("action") == "next",
        "slide_advanced": current_slide == expected_slide,
        "no_audio_or_transcript_fields": _no_audio_or_transcript_fields(new_events),
    }
    return {
        "ok": all(checks.values()),
        "checks": checks,
        "room_url": room_url,
        "target_url": target_url,
        "browser": browser_path,
        "baseline_slide_index": baseline_slide,
        "expected_slide_index": expected_slide,
        "current_slide_index": current_slide,
        "new_event_count": len(new_events),
        "new_event_kinds": kinds,
        "speech_started_event": speech_started,
        "tts_word_event": tts_word,
        "mapped_slide_event": mapped_slide,
    }


def wait_for_presenter_cue(
    room_url: str,
    baseline_timeline_count: int,
    timeout: float,
) -> tuple[dict[str, object], dict[str, object]]:
    deadline = time.monotonic() + timeout
    last_timeline: dict[str, object] = {}
    last_slides: dict[str, object] = {}
    while time.monotonic() < deadline:
        last_timeline = _get_json(f"{room_url}/api/timeline-events")
        last_slides = _get_json(f"{room_url}/api/slide-events")
        new_events = _events(last_timeline)[baseline_timeline_count:]
        mapped_slide = _last_source_event(_events(last_slides), "timeline:browser-presenter-cue")
        if _last_event(new_events, "speech_started") and _last_event(new_events, "tts_word") and mapped_slide:
            return last_timeline, last_slides
        time.sleep(0.4)
    return last_timeline, last_slides


def browser_auto_presenter_cue_url(room_url: str) -> str:
    parsed = urllib.parse.urlparse(room_url)
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    query.append(("auto_presenter_cue", "1"))
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


def _last_source_event(events: list[dict[str, object]], source: str) -> dict[str, object] | None:
    for event in reversed(events):
        if event.get("source") == source:
            return event
    return None


def _event_source(event: dict[str, object] | None) -> object:
    return event.get("source") if isinstance(event, dict) else None


def _no_audio_or_transcript_fields(events: list[dict[str, object]]) -> bool:
    forbidden_keys = {"audio", "audio_path", "audio_url", "transcript", "raw_audio"}
    for event in events:
        if forbidden_keys & set(event):
            return False
        for value in event.values():
            if isinstance(value, str) and ("data:audio" in value or ".wav" in value or ".mp3" in value):
                return False
    return True


def _events(payload: dict[str, object]) -> list[dict[str, object]]:
    events = payload.get("events")
    return events if isinstance(events, list) else []


def _get_json(url: str) -> dict[str, object]:
    with urllib.request.urlopen(url, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())
