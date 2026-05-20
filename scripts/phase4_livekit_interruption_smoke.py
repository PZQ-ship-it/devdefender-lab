from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOM_URL = "http://127.0.0.1:8765"
DEFAULT_REPORT_PATH = ROOT / "artifacts" / "phase4_livekit_interruption_smoke.json"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from devdefender_lab.meeting import redact_meeting_url  # noqa: E402
from devdefender_lab.meeting_provisioner import (  # noqa: E402
    contains_forbidden_provisioning_artifact_fields,
    create_provisioner,
    meeting_created_event_payload,
    provisioner_source,
    safe_provisioned_meeting,
)
from scripts.meeting_provisioner_smoke import cleanup_browser_profile  # noqa: E402
from scripts.phase4_voice_defense_smoke import find_browser  # noqa: E402
from scripts.room_acceptance_smoke import managed_room_report, start_managed_room, stop_managed_room  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Phase 4C LiveKit remote audio interruption detection.")
    parser.add_argument("--room-url", default=DEFAULT_ROOM_URL, help="Running DevDefender room URL.")
    parser.add_argument("--managed-room", action="store_true", help="Start and stop a local mock room for this run.")
    parser.add_argument("--repo", default="sample_repo", help="Repository path used when --managed-room starts a room.")
    parser.add_argument("--slidev-port", type=int, default=3030, help="Slidev port used by --managed-room.")
    parser.add_argument("--startup-timeout", type=float, default=45.0, help="Seconds to wait for a managed room.")
    parser.add_argument("--browser", help="Path to Edge/Chrome/Chromium. Defaults to auto-discovery.")
    parser.add_argument("--timeout", type=float, default=55.0, help="Seconds to wait for interruption events.")
    parser.add_argument("--topic", default="DevDefender LiveKit interruption defense", help="Provisioned LiveKit room topic.")
    parser.add_argument("--duration-minutes", type=int, default=30, help="Provisioned room duration.")
    parser.add_argument(
        "--skip-livekit-room-create",
        action="store_true",
        help="Rely on LiveKit lazy room creation when the browser joins.",
    )
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
        report = run_smoke(
            room_url=args.room_url.rstrip("/"),
            out=args.out,
            browser=args.browser,
            timeout=args.timeout,
            topic=args.topic,
            duration_minutes=args.duration_minutes,
            create_livekit_room=not args.skip_livekit_room_create,
        )
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


def run_smoke(
    *,
    room_url: str,
    out: Path,
    browser: str | None = None,
    timeout: float = 55.0,
    topic: str = "DevDefender LiveKit interruption defense",
    duration_minutes: int = 30,
    create_livekit_room: bool = True,
) -> dict[str, object]:
    browser_path = find_browser(browser)
    baseline_timeline = _get_json(f"{room_url}/api/timeline-events")
    baseline_events = _events(baseline_timeline)
    thread_id = str(baseline_timeline.get("thread_id") or "local-thread")
    provisioner = create_provisioner("livekit", create_livekit_room=create_livekit_room)
    meeting = provisioner.create_meeting(topic=topic, duration_minutes=duration_minutes, room_thread_id=thread_id)
    teardown: dict[str, object] | None = None
    _post_json(f"{room_url}/api/timeline-event", meeting_created_event_payload(meeting))
    target = browser_auto_livekit_interruption_url(
        room_url,
        livekit_room=meeting.meeting_id,
        detector_identity=f"{thread_id}-livekit-detector",
        reviewer_identity=f"{thread_id}-livekit-reviewer",
    )
    profile_dir_obj = tempfile.TemporaryDirectory(
        prefix="devdefender-livekit-interruption-profile-",
        ignore_cleanup_errors=True,
    )
    profile_dir = Path(profile_dir_obj.name)
    process = subprocess.Popen(
        [
            browser_path,
            "--headless=new",
            "--disable-gpu",
            "--autoplay-policy=no-user-gesture-required",
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
        timeline = wait_for_livekit_interruption(room_url, len(baseline_events), timeout)
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
        teardown = provisioner.teardown_meeting(meeting).model_dump(exclude_none=True)

    report = build_report(
        browser_path=browser_path,
        room_url=room_url,
        target_url=target,
        baseline_timeline=baseline_timeline,
        timeline=timeline,
        provisioned_meeting=safe_provisioned_meeting(meeting),
        teardown_result=teardown,
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
    baseline_timeline: dict[str, object],
    timeline: dict[str, object],
    provisioned_meeting: dict[str, object] | None,
    teardown_result: dict[str, object] | None,
    browser_return_code: int | None = None,
    used_terminate: bool = False,
    used_kill: bool = False,
    profile_dir: Path | None = None,
) -> dict[str, object]:
    new_events = _events(timeline)[len(_events(baseline_timeline)) :]
    detection_events = [
        event
        for event in new_events
        if not (
            event.get("kind") == "manual_voice_command"
            and event.get("source") == "browser-livekit-remote-interruption"
            and event.get("command") == "goto"
        )
    ]
    created = _last_event(detection_events, "meeting_created")
    detector_connected = _last_source_event(detection_events, "livekit_connected", "browser-livekit-interruption-detector")
    reviewer_connected = _last_source_event(detection_events, "livekit_connected", "browser-livekit-reviewer")
    reviewer_published = _last_source_event(detection_events, "audio_track_published", "browser-livekit-reviewer")
    remote_started = _last_source_event(detection_events, "speech_started", "browser-livekit-remote-interruption")
    remote_interrupted = _last_source_event(detection_events, "speech_interrupted", "browser-livekit-remote-interruption")
    livekit_error = _last_source_event(detection_events, "livekit_error", "browser-livekit-interruption-detector")
    interruption = timeline.get("interruption") if isinstance(timeline.get("interruption"), dict) else {}
    target_url_redacted = redact_meeting_url(target_url)
    profile_removed = True if profile_dir is None else not profile_dir.exists()
    expected_provisioner_source = provisioner_source("livekit")
    checks = {
        "timeline_reachable": bool(timeline),
        "meeting_created_recorded": created is not None,
        "livekit_provisioner_source_used": created is not None and created.get("source") == expected_provisioner_source,
        "detector_connected_recorded": detector_connected is not None,
        "reviewer_connected_recorded": reviewer_connected is not None,
        "reviewer_audio_track_published": reviewer_published is not None,
        "remote_speech_started_recorded": remote_started is not None,
        "remote_speech_interrupted_recorded": remote_interrupted is not None,
        "interruption_state_active": interruption.get("active") is True
        and interruption.get("source") == "browser-livekit-remote-interruption",
        "no_livekit_error": livekit_error is None,
        "target_url_redacted": "token=" not in target_url_redacted.lower(),
        "provisioned_meeting_redacted": provisioned_meeting is not None
        and not contains_forbidden_provisioning_artifact_fields(provisioned_meeting),
        "teardown_ok": bool(teardown_result and teardown_result.get("ok") is True),
        "no_forbidden_artifact_fields": _no_audio_or_transcript_fields(detection_events)
        and not contains_forbidden_provisioning_artifact_fields(provisioned_meeting)
        and not contains_forbidden_provisioning_artifact_fields(teardown_result),
        "browser_process_exited": browser_return_code is not None,
        "browser_profile_removed": profile_removed,
        "browser_not_killed": used_kill is False,
    }
    return {
        "ok": all(checks.values()),
        "checks": checks,
        "room_url": room_url,
        "target_url": target_url_redacted,
        "browser": browser_path,
        "browser_return_code": browser_return_code,
        "used_terminate": used_terminate,
        "used_kill": used_kill,
        "new_event_count": len(detection_events),
        "new_event_kinds": [str(event.get("kind")) for event in detection_events],
        "baseline_event_count": len(new_events) - len(detection_events),
        "provisioned_meeting": provisioned_meeting,
        "teardown": teardown_result,
        "created_event": created,
        "detector_connected_event": detector_connected,
        "reviewer_connected_event": reviewer_connected,
        "reviewer_published_event": reviewer_published,
        "remote_speech_started_event": remote_started,
        "remote_speech_interrupted_event": remote_interrupted,
        "interruption": interruption,
        "last_livekit_error": livekit_error,
    }


def wait_for_livekit_interruption(room_url: str, baseline_timeline_count: int, timeout: float) -> dict[str, object]:
    deadline = time.monotonic() + timeout
    last_timeline: dict[str, object] = {}
    while time.monotonic() < deadline:
        last_timeline = _get_json(f"{room_url}/api/timeline-events")
        new_events = _events(last_timeline)[baseline_timeline_count:]
        if (
            _last_source_event(new_events, "livekit_connected", "browser-livekit-interruption-detector")
            and _last_source_event(new_events, "livekit_connected", "browser-livekit-reviewer")
            and _last_source_event(new_events, "audio_track_published", "browser-livekit-reviewer")
            and _last_source_event(new_events, "speech_interrupted", "browser-livekit-remote-interruption")
        ):
            return last_timeline
        time.sleep(0.4)
    return last_timeline


def browser_auto_livekit_interruption_url(
    room_url: str,
    *,
    livekit_room: str | None = None,
    detector_identity: str | None = None,
    reviewer_identity: str | None = None,
) -> str:
    parsed = urllib.parse.urlparse(room_url)
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    query.append(("auto_livekit_interruption", "1"))
    if livekit_room:
        query.append(("livekit_room", livekit_room))
    if detector_identity:
        query.append(("detector_identity", detector_identity))
    if reviewer_identity:
        query.append(("reviewer_identity", reviewer_identity))
    return urllib.parse.urlunparse(
        parsed._replace(path="/livekit-interruption-test", query=urllib.parse.urlencode(query))
    )


def write_report(report: dict[str, object], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _last_event(events: list[dict[str, object]], kind: str) -> dict[str, object] | None:
    for event in reversed(events):
        if event.get("kind") == kind:
            return event
    return None


def _last_source_event(events: list[dict[str, object]], kind: str, source: str) -> dict[str, object] | None:
    for event in reversed(events):
        if event.get("kind") == kind and event.get("source") == source:
            return event
    return None


def _no_audio_or_transcript_fields(events: list[dict[str, object]]) -> bool:
    forbidden_keys = {"audio", "audio_path", "audio_url", "transcript", "raw_audio", "text"}
    forbidden_fragments = ("data:audio", ".wav", ".mp3")
    for event in events:
        if forbidden_keys & set(event):
            return False
        for value in event.values():
            if isinstance(value, str) and any(fragment in value.lower() for fragment in forbidden_fragments):
                return False
    return True


def _events(payload: dict[str, object]) -> list[dict[str, object]]:
    events = payload.get("events")
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
