from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_DIR = ROOT / "artifacts"
DEFAULT_OUT = ARTIFACT_DIR / "project_briefing_room_smoke.json"
DEFAULT_TTS_OUT = ARTIFACT_DIR / "project_briefing_room_livekit_tts.json"
DEFAULT_INTERRUPTION_OUT = ARTIFACT_DIR / "project_briefing_room_livekit_interruption.json"
DEFAULT_EVIDENCE_OUT = ARTIFACT_DIR / "evidence_packet_project_briefing_room.json"
DEFAULT_SECRET_OUT = ARTIFACT_DIR / "project_briefing_room_secret_scan.json"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from devdefender_lab.briefing import (  # noqa: E402
    MockBriefingAdapter,
    contains_forbidden_briefing_artifact_fields,
    default_briefing_context,
)
from devdefender_lab.briefing_deck import write_briefing_deck  # noqa: E402
from scripts.room_acceptance_smoke import managed_room_report, start_managed_room, stop_managed_room  # noqa: E402


@dataclass(frozen=True)
class Step:
    name: str
    command: list[str]
    timeout: int
    report_path: Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Phase 4D Project Briefing Room product smoke.")
    parser.add_argument("--room-url", default="http://127.0.0.1:8765", help="Running DevDefender room URL.")
    parser.add_argument("--managed-room", action="store_true", help="Start and stop one local room for LiveKit gates.")
    parser.add_argument("--repo", default="sample_repo", help="Repository path used when --managed-room starts a room.")
    parser.add_argument("--slidev-port", type=int, default=3030, help="Slidev port used by --managed-room.")
    parser.add_argument("--startup-timeout", type=float, default=45.0, help="Seconds to wait for managed room startup.")
    parser.add_argument("--browser", help="Path to Edge/Chrome/Chromium. Defaults to child smoke auto-discovery.")
    parser.add_argument(
        "--agent-backend",
        choices=["mock"],
        default="mock",
        help="Briefing adapter backend. Phase 4D-4 supports only the deterministic mock backend.",
    )
    parser.add_argument(
        "--skip-livekit-gates",
        action="store_true",
        help="Generate briefing artifacts without running LiveKit TTS/interruption child gates.",
    )
    parser.add_argument(
        "--skip-livekit-room-create",
        action="store_true",
        help="Pass through to LiveKit child gates and rely on lazy room creation.",
    )
    parser.add_argument(
        "--skip-closure-gates",
        action="store_true",
        help="Skip replay, evidence packet, and artifact secret scan after LiveKit child gates.",
    )
    parser.add_argument("--timeout", type=float, default=120.0, help="Process timeout for each LiveKit child gate.")
    parser.add_argument("--tts-timeout", type=float, default=75.0, help="Child wait timeout for the LiveKit TTS gate.")
    parser.add_argument(
        "--interruption-timeout",
        type=float,
        default=90.0,
        help="Child wait timeout for the LiveKit interruption gate.",
    )
    parser.add_argument("--artifact-dir", type=Path, default=ARTIFACT_DIR, help="Directory for briefing artifacts.")
    parser.add_argument("--tts-out", type=Path, default=DEFAULT_TTS_OUT, help="Path for the LiveKit TTS child report.")
    parser.add_argument(
        "--interruption-out",
        type=Path,
        default=DEFAULT_INTERRUPTION_OUT,
        help="Path for the LiveKit interruption child report.",
    )
    parser.add_argument("--evidence-packet-out", type=Path, default=DEFAULT_EVIDENCE_OUT)
    parser.add_argument("--secret-scan-out", type=Path, default=DEFAULT_SECRET_OUT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Path for the compact product smoke report.")
    args = parser.parse_args()

    try:
        report = run_smoke(
            room_url=args.room_url.rstrip("/"),
            managed_room=args.managed_room,
            repo=args.repo,
            slidev_port=args.slidev_port,
            startup_timeout=args.startup_timeout,
            browser=args.browser,
            agent_backend=args.agent_backend,
            skip_livekit_gates=args.skip_livekit_gates,
            skip_livekit_room_create=args.skip_livekit_room_create,
            skip_closure_gates=args.skip_closure_gates,
            timeout=args.timeout,
            tts_timeout=args.tts_timeout,
            interruption_timeout=args.interruption_timeout,
            artifact_dir=args.artifact_dir,
            tts_out=args.tts_out,
            interruption_out=args.interruption_out,
            evidence_packet_out=args.evidence_packet_out,
            secret_scan_out=args.secret_scan_out,
            out=args.out,
        )
    except Exception as exc:
        report = {
            "ok": False,
            "error": _safe_error(exc),
            "report_path": str(args.out),
        }
        write_report(report, args.out)

    if not report.get("ok"):
        print(json.dumps(report, indent=2, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


def run_smoke(
    *,
    room_url: str,
    managed_room: bool = False,
    repo: str = "sample_repo",
    slidev_port: int = 3030,
    startup_timeout: float = 45.0,
    browser: str | None = None,
    agent_backend: str = "mock",
    skip_livekit_gates: bool = False,
    skip_livekit_room_create: bool = False,
    skip_closure_gates: bool = False,
    timeout: float = 120.0,
    tts_timeout: float = 75.0,
    interruption_timeout: float = 90.0,
    artifact_dir: Path = ARTIFACT_DIR,
    tts_out: Path = DEFAULT_TTS_OUT,
    interruption_out: Path = DEFAULT_INTERRUPTION_OUT,
    evidence_packet_out: Path = DEFAULT_EVIDENCE_OUT,
    secret_scan_out: Path = DEFAULT_SECRET_OUT,
    out: Path = DEFAULT_OUT,
) -> dict[str, object]:
    results = [build_briefing_artifacts(agent_backend=agent_backend, artifact_dir=artifact_dir)]
    managed_room_payload: dict[str, object] | None = None
    managed_room_state: dict[str, object] | None = None
    shutdown: dict[str, object] | None = None
    try:
        if not skip_livekit_gates:
            if managed_room:
                managed_room_state = start_managed_room(
                    room_url=room_url,
                    repo=repo,
                    slidev_port=slidev_port,
                    startup_timeout=startup_timeout,
                )
            steps = build_livekit_steps(
                room_url=room_url,
                browser=browser,
                timeout=timeout,
                tts_timeout=tts_timeout,
                interruption_timeout=interruption_timeout,
                tts_out=tts_out,
                interruption_out=interruption_out,
                skip_livekit_room_create=skip_livekit_room_create,
            )
            results.extend(run_steps_until_failure(steps))
            livekit_ok = all(_result_ok(results, name) for name in ["livekit_tts", "livekit_interruption"])
            if livekit_ok and not skip_closure_gates:
                closure_steps = build_closure_steps(
                    artifact_dir=artifact_dir,
                    timeout=timeout,
                    evidence_packet_out=evidence_packet_out,
                    secret_scan_out=secret_scan_out,
                )
                results.extend(run_steps_until_failure(closure_steps))
    finally:
        if managed_room_state:
            shutdown = stop_managed_room(managed_room_state)
            managed_room_payload = managed_room_report(managed_room_state, shutdown)

    expected_steps = ["briefing_artifacts"]
    if not skip_livekit_gates:
        expected_steps.extend(["livekit_tts", "livekit_interruption"])
        if not skip_closure_gates:
            expected_steps.extend(["room_replay", "evidence_packet", "artifact_secret"])
    report = build_report(
        results,
        expected_steps,
        managed_room=managed_room_payload,
        skip_livekit_gates=skip_livekit_gates,
        skip_closure_gates=skip_closure_gates,
    )
    report["report_path"] = str(out)
    report["child_report_paths"] = {
        "briefing_deck": display_path(Path(artifact_dir) / "briefing_deck"),
        "livekit_tts": display_path(tts_out),
        "livekit_interruption": display_path(interruption_out),
        "evidence_packet": display_path(evidence_packet_out),
        "artifact_secret": display_path(secret_scan_out),
    }
    write_report(report, out)
    return report


def build_briefing_artifacts(*, agent_backend: str = "mock", artifact_dir: Path = ARTIFACT_DIR) -> dict[str, object]:
    if agent_backend != "mock":
        return {
            "name": "briefing_artifacts",
            "ok": False,
            "payload": {"ok": False, "agent_backend": agent_backend, "error": "unsupported briefing backend"},
            "return_code": None,
        }
    adapter = MockBriefingAdapter()
    report = adapter.build_report(default_briefing_context())
    deck_artifact = write_briefing_deck(report, artifact_dir)
    deck_dir = Path(artifact_dir) / "briefing_deck"
    briefing_report_path = deck_dir / "briefing_report.json"
    briefing_report_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    payload = {
        "ok": True,
        "agent_backend": agent_backend,
        "generated_by": report.generated_by,
        "briefing_report_path": display_path(briefing_report_path),
        "deck_path": display_path(deck_artifact.deck_path),
        "script_path": display_path(deck_artifact.script_path),
        "slide_count": deck_artifact.slide_count,
        "diagram_count": deck_artifact.diagram_count,
        "checks": {
            "briefing_report_written": briefing_report_path.exists(),
            "deck_written": deck_artifact.deck_path is not None and deck_artifact.deck_path.exists(),
            "presenter_script_written": deck_artifact.script_path is not None and deck_artifact.script_path.exists(),
            "mermaid_present": "```mermaid" in deck_artifact.deck_markdown,
            "summary_present": "## Stakeholder Summary" in deck_artifact.deck_markdown,
            "progress_present": "## Progress" in deck_artifact.deck_markdown,
            "requirements_present": "## Requirements Coverage" in deck_artifact.deck_markdown,
            "experiments_present": "## Experiment Results" in deck_artifact.deck_markdown,
            "risks_present": "## Risks and Decisions" in deck_artifact.deck_markdown,
            "questions_present": "## Stakeholder Questions" in deck_artifact.deck_markdown,
            "next_asks_present": "## Next Asks" in deck_artifact.deck_markdown,
            "evidence_pointers_present": "## Evidence Pointers" in deck_artifact.deck_markdown,
            "no_forbidden_artifact_fields": not contains_forbidden_briefing_artifact_fields(
                {
                    "briefing_report": report.model_dump(mode="json"),
                    "deck_artifact": deck_artifact.model_dump(mode="json"),
                }
            ),
        },
    }
    return {
        "name": "briefing_artifacts",
        "ok": all(payload["checks"].values()),
        "payload": payload,
        "return_code": 0,
    }


def build_livekit_steps(
    *,
    room_url: str,
    browser: str | None = None,
    timeout: float = 120.0,
    tts_timeout: float = 75.0,
    interruption_timeout: float = 90.0,
    tts_out: Path = DEFAULT_TTS_OUT,
    interruption_out: Path = DEFAULT_INTERRUPTION_OUT,
    skip_livekit_room_create: bool = False,
) -> list[Step]:
    tts_command = [
        sys.executable,
        str(ROOT / "scripts" / "phase4_livekit_tts_smoke.py"),
        "--room-url",
        room_url,
        "--topic",
        "Project Briefing Room TTS",
        "--timeout",
        str(tts_timeout),
        "--out",
        str(tts_out),
    ]
    interruption_command = [
        sys.executable,
        str(ROOT / "scripts" / "phase4_livekit_interruption_smoke.py"),
        "--room-url",
        room_url,
        "--topic",
        "Project Briefing Room interruption",
        "--timeout",
        str(interruption_timeout),
        "--out",
        str(interruption_out),
    ]
    if browser:
        tts_command.extend(["--browser", browser])
        interruption_command.extend(["--browser", browser])
    if skip_livekit_room_create:
        tts_command.append("--skip-livekit-room-create")
        interruption_command.append("--skip-livekit-room-create")
    step_timeout = max(30, int(timeout))
    return [
        Step("livekit_tts", tts_command, timeout=step_timeout, report_path=tts_out),
        Step("livekit_interruption", interruption_command, timeout=step_timeout, report_path=interruption_out),
    ]


def build_closure_steps(
    *,
    artifact_dir: Path = ARTIFACT_DIR,
    timeout: float = 120.0,
    evidence_packet_out: Path = DEFAULT_EVIDENCE_OUT,
    secret_scan_out: Path = DEFAULT_SECRET_OUT,
) -> list[Step]:
    step_timeout = max(30, int(timeout))
    return [
        Step(
            "room_replay",
            [
                sys.executable,
                str(ROOT / "scripts" / "room_replay_smoke.py"),
                "--artifact-dir",
                str(artifact_dir),
            ],
            timeout=step_timeout,
            report_path=artifact_dir / "project_briefing_room_replay.stdout.json",
        ),
        Step(
            "evidence_packet",
            [
                sys.executable,
                str(ROOT / "scripts" / "evidence_packet_smoke.py"),
                "--artifact-dir",
                str(artifact_dir),
                "--out",
                str(evidence_packet_out),
            ],
            timeout=step_timeout,
            report_path=evidence_packet_out,
        ),
        Step(
            "artifact_secret",
            [
                sys.executable,
                str(ROOT / "scripts" / "artifact_secret_smoke.py"),
                "--artifact-dir",
                str(artifact_dir),
            ],
            timeout=step_timeout,
            report_path=secret_scan_out,
        ),
    ]


def run_steps_until_failure(steps: list[Step]) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for step in steps:
        result = run_step(step)
        results.append(result)
        if not result["ok"]:
            break
    return results


def run_step(step: Step) -> dict[str, object]:
    try:
        process = subprocess.run(
            step.command,
            cwd=ROOT,
            env=os.environ.copy(),
            capture_output=True,
            text=True,
            timeout=step.timeout,
            check=False,
        )
        payload = load_json(step.report_path) if step.report_path.exists() else _parse_json_output(process.stdout)
        if step.name in {"room_replay", "artifact_secret"} and payload:
            write_report(payload, step.report_path)
        return {
            "name": step.name,
            "ok": process.returncode == 0 and isinstance(payload, dict) and payload.get("ok") is True,
            "return_code": process.returncode,
            "report_path": display_path(step.report_path),
            "payload": payload if isinstance(payload, dict) else {},
            "stderr": _safe_stderr(process.stderr),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "name": step.name,
            "ok": False,
            "return_code": None,
            "report_path": display_path(step.report_path),
            "payload": {},
            "stderr": _safe_error(exc),
        }


def build_report(
    results: list[dict[str, object]],
    expected_steps: list[str],
    *,
    managed_room: dict[str, object] | None = None,
    skip_livekit_gates: bool = False,
    skip_closure_gates: bool = False,
) -> dict[str, object]:
    checks = {name: False for name in expected_steps}
    for result in results:
        name = str(result.get("name"))
        if name in checks:
            checks[name] = bool(result.get("ok"))
    summarized_results = summarize_results(results)
    cross_checks = build_cross_checks(
        results,
        summarized_results=summarized_results,
        managed_room=managed_room,
        skip_livekit_gates=skip_livekit_gates,
        skip_closure_gates=skip_closure_gates,
    )
    required_cross_checks = {key: value for key, value in cross_checks.items() if key.endswith("_ok")}
    report: dict[str, object] = {
        "ok": bool(checks) and all(checks.values()) and all(required_cross_checks.values()),
        "checks": checks,
        "cross_checks": cross_checks,
        "results": summarized_results,
        "skip_livekit_gates": skip_livekit_gates,
        "skip_closure_gates": skip_closure_gates,
    }
    if managed_room:
        report["managed_room"] = managed_room
    return report


def build_cross_checks(
    results: list[dict[str, object]],
    *,
    summarized_results: list[dict[str, object]] | None = None,
    managed_room: dict[str, object] | None = None,
    skip_livekit_gates: bool = False,
    skip_closure_gates: bool = False,
) -> dict[str, bool]:
    briefing = _payload_for(results, "briefing_artifacts")
    briefing_checks = briefing.get("checks") if isinstance(briefing.get("checks"), dict) else {}
    summary_payload: dict[str, object] = {
        "results": summarized_results if summarized_results is not None else summarize_results(results),
    }
    if managed_room:
        summary_payload["managed_room"] = managed_room
    replay = _payload_for(results, "room_replay")
    evidence = _payload_for(results, "evidence_packet")
    secret = _payload_for(results, "artifact_secret")
    evidence_kinds = _evidence_kinds(evidence)
    checks = {
        "briefing_report_generated_ok": bool(briefing_checks.get("briefing_report_written")),
        "briefing_deck_written_ok": bool(briefing_checks.get("deck_written")),
        "presenter_script_written_ok": bool(briefing_checks.get("presenter_script_written")),
        "briefing_deck_has_required_sections_ok": all(
            bool(briefing_checks.get(key))
            for key in [
                "mermaid_present",
                "summary_present",
                "progress_present",
                "requirements_present",
                "experiments_present",
                "risks_present",
                "questions_present",
                "next_asks_present",
                "evidence_pointers_present",
            ]
        ),
        "livekit_tts_ok": skip_livekit_gates or _result_ok(results, "livekit_tts"),
        "livekit_interruption_ok": skip_livekit_gates or _result_ok(results, "livekit_interruption"),
        "room_replay_ok": skip_livekit_gates or skip_closure_gates or _result_ok(results, "room_replay"),
        "evidence_packet_ok": skip_livekit_gates or skip_closure_gates or _result_ok(results, "evidence_packet"),
        "artifact_secret_ok": skip_livekit_gates or skip_closure_gates or _result_ok(results, "artifact_secret"),
        "replay_evidence_thread_match_ok": skip_livekit_gates
        or skip_closure_gates
        or bool(replay.get("thread_id") and replay.get("thread_id") == evidence.get("thread_id")),
        "evidence_packet_contains_project_events_ok": skip_livekit_gates
        or skip_closure_gates
        or _has_required_evidence_kinds(evidence_kinds),
        "artifact_secret_findings_clean_ok": skip_livekit_gates
        or skip_closure_gates
        or (
            secret.get("ok") is True
            and isinstance(secret.get("findings"), list)
            and len(secret.get("findings", [])) == 0
        ),
        "managed_room_shutdown_ok": managed_room is None or bool(
            isinstance(managed_room.get("shutdown"), dict) and managed_room["shutdown"].get("ok") is True
        ),
        "no_forbidden_artifact_fields_ok": bool(briefing_checks.get("no_forbidden_artifact_fields"))
        and not contains_forbidden_briefing_artifact_fields(summary_payload),
    }
    checks["livekit_gates_skipped"] = skip_livekit_gates
    checks["closure_gates_skipped"] = skip_livekit_gates or skip_closure_gates
    return checks


def summarize_results(results: list[dict[str, object]]) -> list[dict[str, object]]:
    return [
        {
            "name": result.get("name"),
            "ok": bool(result.get("ok")),
            "return_code": result.get("return_code"),
            "report_path": result.get("report_path"),
            "payload": summarize_payload(result.get("payload")),
        }
        for result in results
    ]


def summarize_payload(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        return {}
    keep_keys = [
        "ok",
        "agent_backend",
        "generated_by",
        "briefing_report_path",
        "deck_path",
        "script_path",
        "slide_count",
        "diagram_count",
        "checks",
        "new_event_count",
        "new_event_kinds",
        "livekit_tts_event_count",
        "mapped_slide_count",
        "baseline_event_count",
        "browser_return_code",
        "thread_id",
        "thread_id_source",
        "slide_event_count",
        "timeline_event_count",
        "evidence_count",
        "kinds",
        "scanned_file_count",
        "loaded_secret_count",
        "findings",
    ]
    return {key: payload[key] for key in keep_keys if key in payload}


def _payload_for(results: list[dict[str, object]], name: str) -> dict[str, object]:
    for result in results:
        if result.get("name") == name and isinstance(result.get("payload"), dict):
            return result["payload"]  # type: ignore[return-value]
    return {}


def _result_ok(results: list[dict[str, object]], name: str) -> bool:
    return any(result.get("name") == name and result.get("ok") is True for result in results)


def _evidence_kinds(evidence_payload: dict[str, object]) -> set[str]:
    kinds = evidence_payload.get("kinds")
    if isinstance(kinds, list):
        return {str(kind) for kind in kinds}
    evidence = evidence_payload.get("evidence")
    if isinstance(evidence, list):
        return {str(item.get("kind")) for item in evidence if isinstance(item, dict)}
    return set()


def _has_required_evidence_kinds(kinds: set[str]) -> bool:
    required = {"meeting_created", "livekit_connected", "tts_audio_track_published", "speech_interrupted"}
    return required.issubset(kinds)


def write_report(report: dict[str, object], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def display_path(path: Path | None) -> str | None:
    if path is None:
        return None
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return str(resolved)


def load_json(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _parse_json_output(output: str) -> dict[str, object]:
    text = output.strip()
    if not text:
        return {}
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end < start:
            return {}
        try:
            payload = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return {}
    return payload if isinstance(payload, dict) else {}


def _safe_stderr(value: str) -> str:
    text = " ".join(str(value).split())
    replacements = {
        "LIVEKIT_API_SECRET": "LIVEKIT_SECRET_ENV",
        "LIVEKIT_API_KEY": "LIVEKIT_KEY_ENV",
        "OPENAI_API_KEY": "OPENAI_KEY_ENV",
    }
    for source, replacement in replacements.items():
        text = text.replace(source, replacement)
    return text[:500]


def _safe_error(exc: BaseException) -> str:
    return _safe_stderr(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
