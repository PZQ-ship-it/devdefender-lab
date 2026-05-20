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

from devdefender_lab.meeting import MEETING_SOURCE, redact_meeting_url  # noqa: E402
from devdefender_lab.meeting_provisioner import (  # noqa: E402
    contains_forbidden_provisioning_artifact_fields,
    create_provisioner,
    meeting_created_event_payload,
    meeting_provision_failed_event_payload,
    provisioner_source,
    safe_provisioned_meeting,
)
from scripts.meeting_automation_smoke import find_browser  # noqa: E402
from scripts.room_acceptance_smoke import managed_room_report, start_managed_room, stop_managed_room  # noqa: E402


DEFAULT_ROOM_URL = "http://127.0.0.1:8765"
DEFAULT_REPORT_PATH = ROOT / "artifacts" / "meeting_provisioner_smoke.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Phase 3 AI-initiated meeting provisioning.")
    parser.add_argument("--room-url", default=DEFAULT_ROOM_URL, help="Running DevDefender room URL.")
    parser.add_argument("--managed-room", action="store_true", help="Start and stop a local mock room for this run.")
    parser.add_argument("--repo", default="sample_repo", help="Repository path used when --managed-room starts a room.")
    parser.add_argument("--slidev-port", type=int, default=3030, help="Slidev port used by --managed-room.")
    parser.add_argument("--startup-timeout", type=float, default=45.0, help="Seconds to wait for a managed room.")
    parser.add_argument("--browser", help="Path to Edge/Chrome/Chromium. Defaults to auto-discovery.")
    parser.add_argument("--provider", default="mock", choices=["mock", "livekit"], help="Meeting provisioner backend.")
    parser.add_argument(
        "--skip-livekit-room-create",
        action="store_true",
        help="For --provider livekit, rely on LiveKit lazy room creation when the browser joins.",
    )
    parser.add_argument("--topic", default="DevDefender AI-created meeting", help="Provisioned meeting topic.")
    parser.add_argument("--duration-minutes", type=int, default=30, help="Provisioned meeting duration.")
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
        report = run_smoke(
            room_url=args.room_url.rstrip("/"),
            out=args.out,
            provider=args.provider,
            topic=args.topic,
            duration_minutes=args.duration_minutes,
            browser=args.browser,
            timeout=args.timeout,
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
    provider: str = "mock",
    topic: str = "DevDefender AI-created meeting",
    duration_minutes: int = 30,
    browser: str | None = None,
    timeout: float = 20.0,
    create_livekit_room: bool = True,
) -> dict[str, object]:
    browser_path = find_browser(browser)
    _post_json(
        f"{room_url}/api/timeline-event",
        {
            "kind": "manual_voice_command",
            "command": "goto",
            "slide_index": 1,
            "source": "meeting-provisioner-smoke",
        },
    )
    before = _get_json(f"{room_url}/api/timeline-events")
    before_events = _events(before)
    thread_id = str(before.get("thread_id") or "local-thread")
    provisioner = create_provisioner(provider, create_livekit_room=create_livekit_room)
    teardown: dict[str, object] | None = None

    try:
        meeting = provisioner.create_meeting(
            topic=topic,
            duration_minutes=duration_minutes,
            room_thread_id=thread_id,
        )
    except Exception as exc:
        _post_json(f"{room_url}/api/timeline-event", meeting_provision_failed_event_payload(provider, str(exc)))
        timeline = _get_json(f"{room_url}/api/timeline-events")
        report = build_report(
            browser_path=browser_path,
            room_url=room_url,
            target_url=None,
            before_events=before_events,
            timeline=timeline,
            provisioned_meeting=None,
            teardown_result=None,
            browser_return_code=None,
            used_terminate=False,
            used_kill=False,
            profile_dir=None,
        )
        report["report_path"] = str(out)
        write_report(report, out)
        return report

    _post_json(f"{room_url}/api/timeline-event", meeting_created_event_payload(meeting))
    if meeting.provider == "livekit":
        target = local_provisioned_meeting_test_url(
            room_url,
            meeting.join_url,
            livekit_room=meeting.meeting_id,
            livekit_identity=f"{thread_id}-livekit-provisioner",
        )
    else:
        target = local_provisioned_meeting_test_url(room_url, meeting.join_url)
    profile_dir_obj = tempfile.TemporaryDirectory(prefix="devdefender-provisioner-profile-", ignore_cleanup_errors=True)
    profile_dir = Path(profile_dir_obj.name)
    process = subprocess.Popen(
        [
            browser_path,
            "--headless=new",
            "--disable-gpu",
            "--use-fake-ui-for-media-stream",
            "--use-fake-device-for-media-stream",
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
        timeline = wait_for_provisioned_meeting_events(room_url, len(before_events), timeout)
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
        before_events=before_events,
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
    target_url: str | None,
    before_events: list[dict[str, object]],
    timeline: dict[str, object],
    provisioned_meeting: dict[str, object] | None,
    teardown_result: dict[str, object] | None,
    browser_return_code: int | None = None,
    used_terminate: bool = False,
    used_kill: bool = False,
    profile_dir: Path | None = None,
) -> dict[str, object]:
    new_events = _events(timeline)[len(before_events) :]
    kinds = [str(event.get("kind")) for event in new_events]
    created = _last_event(new_events, "meeting_created")
    provision_failed = _last_event(new_events, "meeting_provision_failed")
    join_started = _last_event(new_events, "meeting_join_started")
    joined = _last_event(new_events, "meeting_joined")
    left = _last_event(new_events, "meeting_left")
    meeting_error = _last_event(new_events, "meeting_error")
    livekit_connected = _last_event(new_events, "livekit_connected")
    audio_published = _last_event(new_events, "audio_track_published")
    livekit_error = _last_event(new_events, "livekit_error")
    provider_name = str(provisioned_meeting.get("provider")) if isinstance(provisioned_meeting, dict) else ""
    expected_provisioner_source = provisioner_source(provider_name)
    is_livekit = provider_name == "livekit"
    profile_removed = True if profile_dir is None else not profile_dir.exists()
    target_url_redacted = redact_meeting_url(target_url) if target_url else None
    checks = {
        "timeline_reachable": bool(timeline),
        "meeting_created_recorded": created is not None,
        "no_meeting_provision_failed": provision_failed is None,
        "meeting_join_started_recorded_or_livekit_direct": is_livekit or join_started is not None,
        "meeting_joined_recorded_or_livekit_direct": is_livekit or joined is not None,
        "meeting_left_recorded_or_livekit_direct": is_livekit or left is not None,
        "no_meeting_error": meeting_error is None,
        "provisioner_source_used": created is not None and _event_source(created) == expected_provisioner_source,
        "meeting_source_used": all(
            _event_source(event) == MEETING_SOURCE
            for event in new_events
            if str(event.get("kind")) in {"meeting_join_started", "meeting_joined", "meeting_left", "meeting_error"}
        ),
        "livekit_connected_recorded": not is_livekit or livekit_connected is not None,
        "audio_track_published_recorded": not is_livekit or audio_published is not None,
        "no_livekit_error": livekit_error is None,
        "target_url_redacted": target_url_redacted is not None and _has_no_raw_mock_secret(target_url_redacted),
        "provisioned_meeting_redacted": provisioned_meeting is not None
        and _has_no_raw_mock_secret(json.dumps(provisioned_meeting, ensure_ascii=False)),
        "teardown_ok": bool(teardown_result and teardown_result.get("ok") is True),
        "no_forbidden_artifact_fields": not contains_forbidden_provisioning_artifact_fields(new_events)
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
        "new_event_count": len(new_events),
        "new_event_kinds": kinds,
        "provisioned_meeting": provisioned_meeting,
        "teardown": teardown_result,
        "created_event": created,
        "join_started_event": join_started,
        "joined_event": joined,
        "left_event": left,
        "livekit_connected_event": livekit_connected,
        "audio_track_published_event": audio_published,
        "last_meeting_provision_failed": provision_failed,
        "last_meeting_error": meeting_error,
        "last_livekit_error": livekit_error,
    }


def wait_for_provisioned_meeting_events(room_url: str, baseline_count: int, timeout: float) -> dict[str, object]:
    deadline = time.monotonic() + timeout
    last_timeline: dict[str, object] = {}
    while time.monotonic() < deadline:
        last_timeline = _get_json(f"{room_url}/api/timeline-events")
        new_events = _events(last_timeline)[baseline_count:]
        if (
            _last_event(new_events, "meeting_created")
            and (
                (_last_event(new_events, "meeting_joined") and _last_event(new_events, "meeting_left"))
                or (_last_event(new_events, "livekit_connected") and _last_event(new_events, "audio_track_published"))
            )
        ):
            return last_timeline
        time.sleep(0.4)
    return last_timeline


def local_provisioned_meeting_test_url(
    room_url: str,
    join_url: str,
    *,
    livekit_room: str | None = None,
    livekit_identity: str | None = None,
) -> str:
    parsed = urllib.parse.urlparse(room_url)
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    query.append(("auto_livekit" if livekit_room else "auto_meeting", "1"))
    query.append(("meeting_url", join_url))
    if livekit_room:
        query.append(("livekit_room", livekit_room))
    if livekit_identity:
        query.append(("livekit_identity", livekit_identity))
    return urllib.parse.urlunparse(
        parsed._replace(path="/" if livekit_room else "/meeting-test", query=urllib.parse.urlencode(query))
    )


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


def _has_no_raw_mock_secret(value: str) -> bool:
    lowered = value.lower()
    forbidden_fragments = {
        "mock-host-token",
        "mock-join-token",
        "mock-password",
        "start_token=",
        "password=",
        "token=mock",
    }
    return not any(fragment in lowered for fragment in forbidden_fragments)


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
