from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "artifacts" / "phase1_room_closure_smoke.json"
DEFAULT_FULL_OUT = ROOT / "artifacts" / "phase1_room_closure_smoke.full.json"
DEFAULT_ROOM_ACCEPTANCE_OUT = ROOT / "artifacts" / "room_acceptance_livekit_browser_gate.json"


@dataclass(frozen=True)
class Step:
    name: str
    command: list[str]
    timeout: int
    env: dict[str, str] | None = None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run managed room acceptance, Phase 1 e2e, evidence chain, and secret scan."
    )
    parser.add_argument("--room-url", default="http://127.0.0.1:8765", help="Managed room URL with explicit port.")
    parser.add_argument("--repo", default="sample_repo", help="Repository path used by managed room and Phase 1 e2e.")
    parser.add_argument("--slidev-port", type=int, default=3030, help="Slidev port used by managed room.")
    parser.add_argument("--skip-visual", action="store_true", help="Skip browser screenshot visual smoke.")
    parser.add_argument("--include-livekit-token", action="store_true", help="Include LiveKit browser token smoke.")
    parser.add_argument("--include-livekit-browser", action="store_true", help="Include headless browser LiveKit smoke.")
    parser.add_argument(
        "--agent-backend",
        choices=["mock", "openclaude-cli"],
        default="mock",
        help="Agent backend for the Phase 1 e2e/refinement step.",
    )
    parser.add_argument(
        "--agent-timeout",
        type=int,
        default=180,
        help="Timeout in seconds for the Phase 1 e2e/refinement step.",
    )
    parser.add_argument(
        "--include-full-results",
        action="store_true",
        help="Embed full child-step payloads in the main report instead of writing a compact summary.",
    )
    parser.add_argument(
        "--full-out",
        type=Path,
        default=DEFAULT_FULL_OUT,
        help="Path for full child-step details when the main report is compact.",
    )
    parser.add_argument(
        "--room-acceptance-out",
        type=Path,
        default=DEFAULT_ROOM_ACCEPTANCE_OUT,
        help="Path for the nested room acceptance report.",
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Path for the closure report.")
    args = parser.parse_args()

    steps = build_sequence(
        room_url=args.room_url,
        repo=args.repo,
        slidev_port=args.slidev_port,
        skip_visual=args.skip_visual,
        include_livekit_token=args.include_livekit_token,
        include_livekit_browser=args.include_livekit_browser,
        agent_backend=args.agent_backend,
        agent_timeout=args.agent_timeout,
        room_acceptance_out=args.room_acceptance_out,
    )
    results: list[dict[str, object]] = []
    for step in steps:
        result = run_step(step)
        results.append(result)
        if not result["ok"]:
            break

    full_report = build_report(results, [step.name for step in steps], compact=False)
    report = full_report if args.include_full_results else build_report(results, [step.name for step in steps])
    report["report_path"] = str(args.out)
    report["room_acceptance_report_path"] = str(args.room_acceptance_out)
    if not args.include_full_results:
        full_report["report_path"] = str(args.full_out)
        full_report["compact_report_path"] = str(args.out)
        write_report(full_report, args.full_out)
        report["full_report_path"] = str(args.full_out)
    write_report(report, args.out)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if not report["ok"]:
        raise SystemExit(1)


def build_sequence(
    *,
    room_url: str,
    repo: str,
    slidev_port: int,
    skip_visual: bool = False,
    include_livekit_token: bool = False,
    include_livekit_browser: bool = False,
    agent_backend: str = "mock",
    agent_timeout: int = 180,
    room_acceptance_out: Path = DEFAULT_ROOM_ACCEPTANCE_OUT,
) -> list[Step]:
    room_acceptance = [
        sys.executable,
        str(ROOT / "scripts" / "room_acceptance_smoke.py"),
        "--managed-room",
        "--room-url",
        room_url,
        "--repo",
        repo,
        "--slidev-port",
        str(slidev_port),
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
            "phase1_e2e",
            [sys.executable, "-m", "devdefender_lab.smoke", "--mode", "e2e"],
            timeout=agent_timeout + 60,
            env={
                "DEVDEFENDER_LLM_MODE": "mock",
                "DEVDEFENDER_AGENT_BACKEND": agent_backend,
                "DEVDEFENDER_AGENT_TIMEOUT_SECONDS": str(agent_timeout),
            },
        ),
        Step("evidence_chain", [sys.executable, str(ROOT / "scripts" / "evidence_chain_smoke.py")], timeout=120),
        Step("artifact_secret", [sys.executable, str(ROOT / "scripts" / "artifact_secret_smoke.py")], timeout=120),
    ]


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


def build_report(results: list[dict[str, object]], expected_steps: list[str], compact: bool = True) -> dict[str, object]:
    checks = {name: False for name in expected_steps}
    for result in results:
        checks[str(result["name"])] = bool(result["ok"])
    cross_checks = build_cross_checks(results)
    cross_check_passed = {key: value for key, value in cross_checks.items() if key.endswith("_ok")}
    report: dict[str, object] = {
        "ok": bool(checks) and all(checks.values()) and all(cross_check_passed.values()),
        "checks": checks,
        "cross_checks": cross_checks,
        "results": summarize_results(results) if compact else results,
    }
    evidence_chain = _payload_for(results, "evidence_chain")
    if evidence_chain:
        report["evidence_chain"] = {
            "expected_pointers": evidence_chain.get("counts", {}).get("expected_pointers"),
            "selected_pointer_count": evidence_chain.get("selection", {}).get("selected_pointer_count"),
            "omitted_pointer_count": evidence_chain.get("selection", {}).get("omitted_pointer_count"),
        }
    room_acceptance = _payload_for(results, "room_acceptance")
    if room_acceptance:
        report["managed_room_shutdown"] = room_acceptance.get("managed_room", {}).get("shutdown")
    return report


def build_cross_checks(results: list[dict[str, object]]) -> dict[str, bool]:
    room_acceptance = _payload_for(results, "room_acceptance")
    evidence_chain = _payload_for(results, "evidence_chain")
    artifact_secret = _payload_for(results, "artifact_secret")
    phase1_e2e = _payload_for(results, "phase1_e2e")

    shutdown = room_acceptance.get("managed_room", {}).get("shutdown", {}) if room_acceptance else {}
    room_checks = room_acceptance.get("checks", {}) if room_acceptance else {}
    room_replay = _nested_room_acceptance_payload(room_acceptance, "room_replay")
    evidence_packet = _nested_room_acceptance_payload(room_acceptance, "evidence_packet")
    room_replay_thread_id = room_replay.get("thread_id") if isinstance(room_replay, dict) else None
    evidence_packet_thread_id = evidence_packet.get("thread_id") if isinstance(evidence_packet, dict) else None
    expected_pointers = evidence_chain.get("expected_pointers", []) if evidence_chain else []
    issue = phase1_e2e.get("issue", {}) if phase1_e2e else {}
    issue_evidence = issue.get("evidence", []) if isinstance(issue, dict) else []
    findings = artifact_secret.get("findings", []) if artifact_secret else []
    livekit_browser_ran = bool(isinstance(room_checks, dict) and room_checks.get("livekit_browser"))
    evidence_chain_thread_ids = _thread_ids_from_pointers(expected_pointers)
    issue_thread_ids = _thread_ids_from_pointers(issue_evidence)

    livekit_pointer_checks = True
    if livekit_browser_ran:
        livekit_pointer_checks = _contains_kind(expected_pointers, "livekit_connected") and _contains_kind(
            expected_pointers, "audio_track_published"
        )

    livekit_issue_checks = True
    if livekit_browser_ran:
        livekit_issue_checks = _contains_kind(issue_evidence, "livekit_connected") and _contains_kind(
            issue_evidence, "audio_track_published"
        )

    return {
        "managed_room_clean_shutdown_ok": not room_acceptance
        or bool(
            isinstance(shutdown, dict)
            and shutdown.get("ok") is True
            and shutdown.get("used_terminate") is False
            and shutdown.get("used_kill") is False
            and shutdown.get("lingering_ports") == []
        ),
        "livekit_browser_ran": livekit_browser_ran,
        "livekit_pointers_in_evidence_chain_ok": livekit_pointer_checks,
        "livekit_pointers_in_issue_ok": livekit_issue_checks,
        "room_replay_and_packet_thread_match_ok": not room_acceptance
        or bool(room_replay_thread_id and evidence_packet_thread_id and room_replay_thread_id == evidence_packet_thread_id),
        "evidence_chain_thread_matches_packet_ok": not evidence_chain
        or not evidence_packet_thread_id
        or evidence_chain_thread_ids == {str(evidence_packet_thread_id)},
        "issue_evidence_thread_matches_packet_ok": not phase1_e2e
        or not evidence_packet_thread_id
        or issue_thread_ids == {str(evidence_packet_thread_id)},
        "artifact_secret_clean_ok": not artifact_secret or (isinstance(findings, list) and not findings),
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


def _payload_summary(name: str, payload: dict[str, object]) -> dict[str, object]:
    if name == "room_acceptance":
        checks = payload.get("checks") if isinstance(payload.get("checks"), dict) else {}
        managed_room = payload.get("managed_room") if isinstance(payload.get("managed_room"), dict) else {}
        shutdown = managed_room.get("shutdown") if isinstance(managed_room.get("shutdown"), dict) else {}
        return {
            "ok": payload.get("ok"),
            "checks": checks,
            "managed_shutdown": shutdown,
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
    return {"ok": payload.get("ok")}


def write_report(report: dict[str, object], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _step_ok(name: str, return_code: int, payload: dict[str, object]) -> bool:
    if return_code != 0:
        return False
    if name == "phase1_e2e":
        refinement = payload.get("refinement")
        return isinstance(refinement, dict) and refinement.get("status") == "verified"
    return bool(payload.get("ok"))


def _payload_for(results: list[dict[str, object]], name: str) -> dict[str, object]:
    for result in results:
        if result.get("name") == name and isinstance(result.get("payload"), dict):
            return result["payload"]  # type: ignore[return-value]
    return {}


def _nested_room_acceptance_payload(room_acceptance: dict[str, object], name: str) -> dict[str, object]:
    nested_results = room_acceptance.get("results", [])
    if not isinstance(nested_results, list):
        return {}
    for result in nested_results:
        if isinstance(result, dict) and result.get("name") == name and isinstance(result.get("payload"), dict):
            return result["payload"]  # type: ignore[return-value]
    return {}


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
        raise


if __name__ == "__main__":
    main()
