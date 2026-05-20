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
DEFAULT_REPORT_PATH = ROOT / "artifacts" / "phase4_voice_defense_smoke.json"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.room_acceptance_smoke import managed_room_report, start_managed_room, stop_managed_room  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Phase 4 browser TTS/interruption/resume defense flow.")
    parser.add_argument("--room-url", default=DEFAULT_ROOM_URL, help="Running DevDefender room URL.")
    parser.add_argument("--managed-room", action="store_true", help="Start and stop a local mock room for this run.")
    parser.add_argument("--repo", default="sample_repo", help="Repository path used when --managed-room starts a room.")
    parser.add_argument("--slidev-port", type=int, default=3030, help="Slidev port used by --managed-room.")
    parser.add_argument("--startup-timeout", type=float, default=45.0, help="Seconds to wait for a managed room.")
    parser.add_argument("--browser", help="Path to Edge/Chrome/Chromium. Defaults to auto-discovery.")
    parser.add_argument("--timeout", type=float, default=30.0, help="Seconds to wait for voice defense events.")
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
    return 0


def run_smoke(room_url: str, out: Path, browser: str | None = None, timeout: float = 30.0) -> dict[str, object]:
    browser_path = find_browser(browser)
    baseline_timeline = _get_json(f"{room_url}/api/timeline-events")
    baseline_slides = _get_json(f"{room_url}/api/slide-events")
    target = browser_auto_voice_defense_url(room_url)
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
        timeline, slides = wait_for_voice_defense(room_url, len(_events(baseline_timeline)), timeout)
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
    voice_events = [event for event in new_events if event.get("source") == "browser-voice-defense"]
    interruption_events = [event for event in new_events if event.get("source") == "browser-voice-interruption"]
    anchors = [event for event in voice_events if event.get("kind") == "tts_word" and event.get("token") == "next"]
    mapped_slides = [
        event for event in _events(slides) if event.get("source") == "timeline:browser-voice-defense"
    ]
    baseline_slide = baseline_slides.get("current_slide_index")
    expected_slide = baseline_slide + 2 if isinstance(baseline_slide, int) else None
    current_slide = slides.get("current_slide_index")
    interruption = timeline.get("interruption") if isinstance(timeline.get("interruption"), dict) else {}
    checks = {
        "timeline_reachable": bool(timeline),
        "opening_speech_started": _has_event(voice_events, "speech_started", command="opening"),
        "answer_speech_started": _has_event(voice_events, "speech_started", command="answer"),
        "resume_speech_started": _has_event(voice_events, "speech_started", command="resume"),
        "two_tts_anchors_recorded": len(anchors) >= 2,
        "interruption_speech_started": _has_event(interruption_events, "speech_started", command="reviewer-question"),
        "speech_interrupted_recorded": _has_event(interruption_events, "speech_interrupted"),
        "interruption_handled_after_answer": interruption.get("active") is False
        and interruption.get("source") == "browser-voice-interruption",
        "two_mapped_slides_recorded": len(mapped_slides) >= 2,
        "slide_advanced_twice": current_slide == expected_slide,
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
        "new_event_kinds": [str(event.get("kind")) for event in new_events],
        "voice_event_count": len(voice_events),
        "interruption_event_count": len(interruption_events),
        "mapped_slide_count": len(mapped_slides),
        "interruption": interruption,
    }


def wait_for_voice_defense(
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
        voice_events = [event for event in new_events if event.get("source") == "browser-voice-defense"]
        interruption_events = [event for event in new_events if event.get("source") == "browser-voice-interruption"]
        anchors = [event for event in voice_events if event.get("kind") == "tts_word" and event.get("token") == "next"]
        if (
            len(anchors) >= 2
            and _has_event(voice_events, "speech_started", command="answer")
            and _has_event(voice_events, "speech_started", command="resume")
            and _has_event(interruption_events, "speech_interrupted")
        ):
            return last_timeline, last_slides
        time.sleep(0.4)
    return last_timeline, last_slides


def browser_auto_voice_defense_url(room_url: str) -> str:
    parsed = urllib.parse.urlparse(room_url)
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    query.append(("auto_voice_defense", "1"))
    return urllib.parse.urlunparse(parsed._replace(path="/voice-defense-test", query=urllib.parse.urlencode(query)))


def write_report(report: dict[str, object], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def find_browser(explicit_browser: str | None = None) -> str:
    candidates: list[str] = []
    if explicit_browser:
        candidates.append(explicit_browser)
    if os.getenv("DEVDEFENDER_BROWSER"):
        candidates.append(os.environ["DEVDEFENDER_BROWSER"])
    candidates.extend(["msedge", "microsoft-edge", "google-chrome", "chrome", "chromium", "chromium-browser"])
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


def _has_event(events: list[dict[str, object]], kind: str, *, command: str | None = None) -> bool:
    for event in events:
        if event.get("kind") != kind:
            continue
        if command is not None and event.get("command") != command:
            continue
        return True
    return False


def _no_audio_or_transcript_fields(events: list[dict[str, object]]) -> bool:
    forbidden_keys = {"audio", "audio_path", "audio_url", "transcript", "raw_audio", "text"}
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
