from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_DIR = ROOT / "artifacts"
DEFAULT_OUT = ARTIFACT_DIR / "phase3_meeting_closure_smoke.json"
DEFAULT_FULL_OUT = ARTIFACT_DIR / "phase3_meeting_closure_smoke.full.json"
DEFAULT_ROOM_ACCEPTANCE_OUT = ARTIFACT_DIR / "phase3d_room_acceptance.json"
DEFAULT_MEETING_OUT = ARTIFACT_DIR / "phase3d_meeting_automation_smoke.json"
DEFAULT_MEDIA_OUT = ARTIFACT_DIR / "phase3d_media_route_smoke.json"
DEFAULT_WEBRTC_OUT = ARTIFACT_DIR / "phase3d_webrtc_meeting_smoke.json"
DEFAULT_ZOOM_OUT = ARTIFACT_DIR / "phase3d_zoom_web_discovery_smoke.json"
DEFAULT_EVIDENCE_PACKET_OUT = ARTIFACT_DIR / "evidence_packet.json"
DEFAULT_PHASE3D_EVIDENCE_OUT = ARTIFACT_DIR / "evidence_packet_phase3d.json"
DEFAULT_EVIDENCE_CHAIN_OUT = ARTIFACT_DIR / "evidence_chain_phase3d.json"


if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.room_acceptance_smoke import managed_room_report, start_managed_room, stop_managed_room  # noqa: E402


@dataclass(frozen=True)
class Step:
    name: str
    command: list[str]
    timeout: int
    env: dict[str, str] | None = None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run Phase 3 meeting automation closure: room baseline, 3A/3B/3C gates, evidence chain, secrets, and tests."
    )
    parser.add_argument("--room-url", default="http://127.0.0.1:8765", help="Managed room URL with explicit port.")
    parser.add_argument("--repo", default="sample_repo", help="Repository path used by managed room and Phase 1 e2e.")
    parser.add_argument("--slidev-port", type=int, default=3030, help="Slidev port used by managed room.")
    parser.add_argument("--startup-timeout", type=float, default=45.0, help="Seconds to wait for managed room startup.")
    parser.add_argument("--skip-visual", action="store_true", help="Skip room visual smoke in the baseline room acceptance step.")
    parser.add_argument("--include-livekit-token", action="store_true", help="Include LiveKit token smoke in room acceptance.")
    parser.add_argument("--include-livekit-browser", action="store_true", help="Include LiveKit browser smoke in room acceptance.")
    parser.add_argument(
        "--agent-backend",
        choices=["mock", "openclaude-cli"],
        default="mock",
        help="Agent backend for the Phase 1 e2e/refinement step.",
    )
    parser.add_argument("--agent-timeout", type=int, default=180, help="Timeout in seconds for the Phase 1 e2e step.")
    parser.add_argument("--skip-pytest", action="store_true", help="Skip the final pytest regression step.")
    parser.add_argument(
        "--include-full-results",
        action="store_true",
        help="Embed full child-step payloads in the main report instead of writing a compact summary.",
    )
    parser.add_argument("--full-out", type=Path, default=DEFAULT_FULL_OUT, help="Path for the full child-step report.")
    parser.add_argument("--room-acceptance-out", type=Path, default=DEFAULT_ROOM_ACCEPTANCE_OUT)
    parser.add_argument("--meeting-out", type=Path, default=DEFAULT_MEETING_OUT)
    parser.add_argument("--media-out", type=Path, default=DEFAULT_MEDIA_OUT)
    parser.add_argument("--webrtc-out", type=Path, default=DEFAULT_WEBRTC_OUT)
    parser.add_argument("--zoom-out", type=Path, default=DEFAULT_ZOOM_OUT)
    parser.add_argument("--evidence-packet-out", type=Path, default=DEFAULT_EVIDENCE_PACKET_OUT)
    parser.add_argument("--phase3d-evidence-out", type=Path, default=DEFAULT_PHASE3D_EVIDENCE_OUT)
    parser.add_argument("--evidence-chain-out", type=Path, default=DEFAULT_EVIDENCE_CHAIN_OUT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Path for the compact Phase 3 closure report.")
    args = parser.parse_args()

    room_steps = build_room_steps(
        room_url=args.room_url,
        room_acceptance_out=args.room_acceptance_out,
        meeting_out=args.meeting_out,
        media_out=args.media_out,
        webrtc_out=args.webrtc_out,
        zoom_out=args.zoom_out,
        evidence_packet_out=args.evidence_packet_out,
        skip_visual=args.skip_visual,
        include_livekit_token=args.include_livekit_token,
        include_livekit_browser=args.include_livekit_browser,
    )
    post_steps = build_post_room_steps(
        repo=args.repo,
        agent_backend=args.agent_backend,
        agent_timeout=args.agent_timeout,
        evidence_chain_out=args.evidence_chain_out,
        skip_pytest=args.skip_pytest,
    )
    expected_steps = [step.name for step in [*room_steps, *post_steps]]

    results: list[dict[str, object]] = []
    managed_room: dict[str, object] | None = None
    shutdown: dict[str, object] | None = None
    try:
        managed_room = start_managed_room(
            room_url=args.room_url,
            repo=args.repo,
            slidev_port=args.slidev_port,
            startup_timeout=args.startup_timeout,
        )
        results.extend(run_steps_until_failure(room_steps))
    finally:
        if managed_room:
            shutdown = stop_managed_room(managed_room)

    room_ok = len(results) == len(room_steps) and all(result.get("ok") for result in results)
    if room_ok and shutdown and shutdown.get("ok"):
        duplicate_result = duplicate_evidence_packet(args.evidence_packet_out, args.phase3d_evidence_out)
        results.append(duplicate_result)
        if duplicate_result["ok"]:
            results.extend(run_steps_until_failure(post_steps))

    all_expected_steps = [*expected_steps]
    if "phase3d_evidence_copy" not in all_expected_steps:
        all_expected_steps.insert(len(room_steps), "phase3d_evidence_copy")

    evidence_packet = load_json(args.evidence_packet_out)
    managed_report = managed_room_report(managed_room, shutdown or {}) if managed_room else None
    full_report = build_report(
        results,
        all_expected_steps,
        managed_room=managed_report,
        evidence_packet=evidence_packet,
        compact=False,
    )
    report = (
        full_report
        if args.include_full_results
        else build_report(results, all_expected_steps, managed_room=managed_report, evidence_packet=evidence_packet)
    )
    report["report_path"] = str(args.out)
    report["child_report_paths"] = child_report_paths(args)
    if not args.include_full_results:
        full_report["report_path"] = str(args.full_out)
        full_report["compact_report_path"] = str(args.out)
        write_report(full_report, args.full_out)
        report["full_report_path"] = str(args.full_out)
    write_report(report, args.out)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if not report["ok"]:
        raise SystemExit(1)


def build_room_steps(
    *,
    room_url: str,
    room_acceptance_out: Path = DEFAULT_ROOM_ACCEPTANCE_OUT,
    meeting_out: Path = DEFAULT_MEETING_OUT,
    media_out: Path = DEFAULT_MEDIA_OUT,
    webrtc_out: Path = DEFAULT_WEBRTC_OUT,
    zoom_out: Path = DEFAULT_ZOOM_OUT,
    evidence_packet_out: Path = DEFAULT_EVIDENCE_PACKET_OUT,
    skip_visual: bool = False,
    include_livekit_token: bool = False,
    include_livekit_browser: bool = False,
) -> list[Step]:
    room_acceptance = [
        sys.executable,
        str(ROOT / "scripts" / "room_acceptance_smoke.py"),
        "--room-url",
        room_url,
        "--out",
        str(room_acceptance_out),
    ]
    if skip_visual:
        room_acceptance.append("--skip-visual")
    if include_livekit_token:
        room_acceptance.append("--include-livekit-token")
    if include_livekit_browser:
        room_acceptance.append("--include-livekit-browser")

    return [
        Step("room_acceptance", room_acceptance, timeout=360),
        Step(
            "meeting_automation",
            [
                sys.executable,
                str(ROOT / "scripts" / "meeting_automation_smoke.py"),
                "--room-url",
                room_url,
                "--out",
                str(meeting_out),
            ],
            timeout=120,
        ),
        Step(
            "media_route",
            [
                sys.executable,
                str(ROOT / "scripts" / "media_route_smoke.py"),
                "--room-url",
                room_url,
                "--out",
                str(media_out),
            ],
            timeout=120,
        ),
        Step(
            "webrtc_meeting",
            [
                sys.executable,
                str(ROOT / "scripts" / "webrtc_meeting_smoke.py"),
                "--room-url",
                room_url,
                "--out",
                str(webrtc_out),
            ],
            timeout=160,
        ),
        Step(
            "zoom_web_discovery",
            [
                sys.executable,
                str(ROOT / "scripts" / "zoom_web_discovery_smoke.py"),
                "--room-url",
                room_url,
                "--out",
                str(zoom_out),
            ],
            timeout=120,
        ),
        Step("room_replay", [sys.executable, str(ROOT / "scripts" / "room_replay_smoke.py")], timeout=120),
        Step(
            "evidence_packet",
            [
                sys.executable,
                str(ROOT / "scripts" / "evidence_packet_smoke.py"),
                "--out",
                str(evidence_packet_out),
            ],
            timeout=120,
        ),
    ]


def build_post_room_steps(
    *,
    repo: str = "sample_repo",
    agent_backend: str = "mock",
    agent_timeout: int = 180,
    evidence_chain_out: Path = DEFAULT_EVIDENCE_CHAIN_OUT,
    skip_pytest: bool = False,
) -> list[Step]:
    steps = [
        Step(
            "phase1_e2e",
            [sys.executable, "-m", "devdefender_lab.smoke", "--mode", "e2e", "--repo", repo],
            timeout=agent_timeout + 60,
            env={
                "DEVDEFENDER_LLM_MODE": "mock",
                "DEVDEFENDER_AGENT_BACKEND": agent_backend,
                "DEVDEFENDER_AGENT_TIMEOUT_SECONDS": str(agent_timeout),
            },
        ),
        Step(
            "evidence_chain",
            [sys.executable, str(ROOT / "scripts" / "evidence_chain_smoke.py"), "--out", str(evidence_chain_out)],
            timeout=120,
        ),
        Step("artifact_secret", [sys.executable, str(ROOT / "scripts" / "artifact_secret_smoke.py")], timeout=120),
    ]
    if not skip_pytest:
        steps.append(Step("pytest", [sys.executable, "-m", "pytest", "tests", "-q"], timeout=240))
    return steps


def run_steps_until_failure(steps: list[Step]) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for step in steps:
        result = run_step(step)
        results.append(result)
        if not result["ok"]:
            break
    return results


def run_step(step: Step) -> dict[str, object]:
    env = os.environ.copy()
    if step.env:
        env.update(step.env)
    try:
        process = subprocess.run(
            step.command,
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=step.timeout,
            check=False,
        )
        payload = _parse_json_output(process.stdout)
        ok = _step_ok(step.name, process.returncode, payload)
        return {
            "name": step.name,
            "ok": ok,
            "return_code": process.returncode,
            "payload": payload,
            "stderr": process.stderr.strip(),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "name": step.name,
            "ok": False,
            "return_code": None,
            "payload": {},
            "stderr": f"Timed out after {step.timeout}s: {exc}",
        }


def duplicate_evidence_packet(source: Path, destination: Path) -> dict[str, object]:
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        payload = load_json(destination)
        return {
            "name": "phase3d_evidence_copy",
            "ok": isinstance(payload, dict) and payload.get("ok") is True,
            "return_code": 0,
            "payload": {
                "ok": isinstance(payload, dict) and payload.get("ok") is True,
                "source": str(source),
                "destination": str(destination),
                "evidence_count": len(payload.get("evidence", [])) if isinstance(payload, dict) and isinstance(payload.get("evidence"), list) else 0,
            },
            "stderr": "",
        }
    except OSError as exc:
        return {
            "name": "phase3d_evidence_copy",
            "ok": False,
            "return_code": None,
            "payload": {"ok": False, "source": str(source), "destination": str(destination)},
            "stderr": str(exc),
        }


def build_report(
    results: list[dict[str, object]],
    expected_steps: list[str],
    *,
    managed_room: dict[str, object] | None = None,
    evidence_packet: dict[str, object] | None = None,
    compact: bool = True,
) -> dict[str, object]:
    checks = {name: False for name in expected_steps}
    for result in results:
        checks[str(result["name"])] = bool(result["ok"])
    cross_checks = build_cross_checks(results, managed_room=managed_room, evidence_packet=evidence_packet)
    required_cross_checks = {key: value for key, value in cross_checks.items() if key.endswith("_ok")}
    report: dict[str, object] = {
        "ok": bool(checks) and all(checks.values()) and all(required_cross_checks.values()),
        "checks": checks,
        "cross_checks": cross_checks,
        "results": summarize_results(results) if compact else results,
    }
    if managed_room:
        report["managed_room"] = managed_room
    if evidence_packet:
        evidence = evidence_packet.get("evidence") if isinstance(evidence_packet.get("evidence"), list) else []
        report["evidence_packet"] = {
            "ok": evidence_packet.get("ok"),
            "thread_id": evidence_packet.get("thread_id"),
            "evidence_count": len(evidence),
            "kinds": sorted({str(item.get("kind")) for item in evidence if isinstance(item, dict)}),
        }
    evidence_chain = _payload_for(results, "evidence_chain")
    if evidence_chain:
        report["evidence_chain"] = {
            "expected_pointers": evidence_chain.get("counts", {}).get("expected_pointers"),
            "selected_pointer_count": evidence_chain.get("selection", {}).get("selected_pointer_count"),
            "omitted_pointer_count": evidence_chain.get("selection", {}).get("omitted_pointer_count"),
        }
    return report


def build_cross_checks(
    results: list[dict[str, object]],
    *,
    managed_room: dict[str, object] | None = None,
    evidence_packet: dict[str, object] | None = None,
) -> dict[str, bool]:
    replay = _payload_for(results, "room_replay")
    evidence_packet_step = _payload_for(results, "evidence_packet")
    phase1_e2e = _payload_for(results, "phase1_e2e")
    evidence_chain = _payload_for(results, "evidence_chain")
    artifact_secret = _payload_for(results, "artifact_secret")
    pytest_payload = _payload_for(results, "pytest")

    shutdown = managed_room.get("shutdown", {}) if isinstance(managed_room, dict) else {}
    packet = evidence_packet if isinstance(evidence_packet, dict) else {}
    packet_evidence = packet.get("evidence") if isinstance(packet.get("evidence"), list) else []
    packet_thread_id = str(packet.get("thread_id") or evidence_packet_step.get("thread_id") or "")
    replay_thread_id = str(replay.get("thread_id") or "")
    evidence_chain_pointers = evidence_chain.get("expected_pointers", []) if evidence_chain else []
    issue = phase1_e2e.get("issue", {}) if phase1_e2e else {}
    issue_evidence = issue.get("evidence", []) if isinstance(issue, dict) else []
    findings = artifact_secret.get("findings", []) if artifact_secret else []

    return {
        "managed_room_clean_shutdown_ok": bool(
            isinstance(shutdown, dict)
            and shutdown.get("ok") is True
            and shutdown.get("used_terminate") is False
            and shutdown.get("used_kill") is False
            and shutdown.get("lingering_ports") == []
        ),
        "room_replay_and_packet_thread_match_ok": bool(replay_thread_id and packet_thread_id and replay_thread_id == packet_thread_id),
        "local_meeting_lifecycle_in_packet_ok": _packet_has_source_kinds(
            packet_evidence, "local-meeting-test", {"meeting_join_started", "meeting_joined", "meeting_left"}
        ),
        "media_route_events_in_packet_ok": _packet_has_source_kinds(
            packet_evidence, "mock-media-router", {"virtual_audio_ready", "virtual_video_ready", "media_published"}
        ),
        "webrtc_events_in_packet_ok": _packet_has_source_kinds(
            packet_evidence,
            "generic-webrtc-test",
            {
                "meeting_join_started",
                "virtual_audio_ready",
                "virtual_video_ready",
                "meeting_joined",
                "media_published",
                "meeting_left",
            },
        ),
        "zoom_discovery_events_in_packet_ok": _packet_has_source_kinds(
            packet_evidence, "zoom-web-discovery", {"meeting_join_started", "meeting_joined", "meeting_left"}
        ),
        "evidence_chain_thread_matches_packet_ok": not evidence_chain
        or bool(packet_thread_id and _thread_ids_from_pointers(evidence_chain_pointers) == {packet_thread_id}),
        "issue_evidence_thread_matches_packet_ok": not phase1_e2e
        or bool(packet_thread_id and _thread_ids_from_pointers(issue_evidence) == {packet_thread_id}),
        "meeting_media_pointers_in_evidence_chain_ok": not evidence_chain
        or (
            _contains_kind(evidence_chain_pointers, "meeting_joined")
            and _contains_kind(evidence_chain_pointers, "media_published")
        ),
        "artifact_secret_clean_ok": not artifact_secret or (isinstance(findings, list) and not findings),
        "pytest_reported_ok": not pytest_payload or pytest_payload.get("ok") is True,
    }


def summarize_results(results: list[dict[str, object]]) -> list[dict[str, object]]:
    summaries: list[dict[str, object]] = []
    for result in results:
        name = str(result.get("name", ""))
        payload = result.get("payload")
        summary: dict[str, object] = {
            "name": name,
            "ok": bool(result.get("ok")),
            "return_code": result.get("return_code"),
        }
        if isinstance(payload, dict):
            summary["summary"] = _payload_summary(name, payload)
        stderr = str(result.get("stderr") or "").strip()
        if stderr:
            summary["stderr_tail"] = stderr[-500:]
        summaries.append(summary)
    return summaries


def write_report(report: dict[str, object], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def child_report_paths(args: argparse.Namespace) -> dict[str, str]:
    return {
        "room_acceptance": str(args.room_acceptance_out),
        "meeting_automation": str(args.meeting_out),
        "media_route": str(args.media_out),
        "webrtc_meeting": str(args.webrtc_out),
        "zoom_web_discovery": str(args.zoom_out),
        "evidence_packet": str(args.evidence_packet_out),
        "phase3d_evidence_packet": str(args.phase3d_evidence_out),
        "evidence_chain": str(args.evidence_chain_out),
    }


def load_json(path: Path) -> dict[str, object] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _step_ok(name: str, return_code: int, payload: dict[str, object]) -> bool:
    if return_code != 0:
        return False
    if name == "phase1_e2e":
        refinement = payload.get("refinement")
        return isinstance(refinement, dict) and refinement.get("status") == "verified"
    if name == "pytest":
        return "failed" not in str(payload.get("summary", "")).lower()
    return bool(payload.get("ok"))


def _payload_for(results: list[dict[str, object]], name: str) -> dict[str, object]:
    for result in results:
        if result.get("name") == name and isinstance(result.get("payload"), dict):
            return result["payload"]  # type: ignore[return-value]
    return {}


def _payload_summary(name: str, payload: dict[str, object]) -> dict[str, object]:
    if name in {
        "room_acceptance",
        "meeting_automation",
        "media_route",
        "webrtc_meeting",
        "zoom_web_discovery",
    }:
        return {
            "ok": payload.get("ok"),
            "checks": payload.get("checks"),
            "new_event_count": payload.get("new_event_count"),
            "new_event_kinds": payload.get("new_event_kinds"),
        }
    if name == "room_replay":
        return {
            "ok": payload.get("ok"),
            "thread_id": payload.get("thread_id"),
            "timeline_event_count": payload.get("timeline_event_count"),
            "slide_event_count": payload.get("slide_event_count"),
        }
    if name == "evidence_packet":
        return {
            "ok": payload.get("ok"),
            "thread_id": payload.get("thread_id"),
            "evidence_count": payload.get("evidence_count"),
        }
    if name == "phase3d_evidence_copy":
        return {
            "ok": payload.get("ok"),
            "evidence_count": payload.get("evidence_count"),
            "destination": payload.get("destination"),
        }
    if name == "phase1_e2e":
        issue = payload.get("issue") if isinstance(payload.get("issue"), dict) else {}
        refinement = payload.get("refinement") if isinstance(payload.get("refinement"), dict) else {}
        return {
            "issue_title": issue.get("title"),
            "issue_evidence_count": len(issue.get("evidence", [])) if isinstance(issue.get("evidence"), list) else None,
            "refinement_status": refinement.get("status"),
            "agent_backend": refinement.get("agent_backend"),
            "violations": refinement.get("violations"),
        }
    if name == "evidence_chain":
        return {
            "ok": payload.get("ok"),
            "checks": payload.get("checks"),
            "counts": payload.get("counts"),
            "selection": payload.get("selection"),
        }
    if name == "artifact_secret":
        return {
            "ok": payload.get("ok"),
            "loaded_secret_count": payload.get("loaded_secret_count"),
            "scanned_file_count": payload.get("scanned_file_count"),
            "finding_count": len(payload.get("findings", [])) if isinstance(payload.get("findings"), list) else None,
        }
    if name == "pytest":
        return {"ok": payload.get("ok"), "summary": payload.get("summary")}
    return {"ok": payload.get("ok")}


def _packet_has_source_kinds(evidence: object, source: str, required_kinds: set[str]) -> bool:
    if not isinstance(evidence, list):
        return False
    found = {
        str(item.get("kind"))
        for item in evidence
        if isinstance(item, dict) and item.get("source") == source and isinstance(item.get("kind"), str)
    }
    return required_kinds <= found


def _contains_kind(values: object, kind: str) -> bool:
    if not isinstance(values, list):
        return False
    suffix = f"&kind={kind}"
    return any(isinstance(value, str) and value.endswith(suffix) for value in values)


def _thread_ids_from_pointers(values: object) -> set[str]:
    if not isinstance(values, list):
        return set()
    thread_ids: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            continue
        if value.startswith("timeline://") and "#event=" in value:
            thread_ids.add(value.removeprefix("timeline://").split("#", 1)[0])
        elif value.startswith("slide://") and "#page=" in value:
            thread_ids.add(value.removeprefix("slide://").split("#", 1)[0])
    return thread_ids


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
        if " passed" in text and " failed" not in text:
            return {"ok": True, "summary": text.splitlines()[-1]}
        raise


if __name__ == "__main__":
    main()
