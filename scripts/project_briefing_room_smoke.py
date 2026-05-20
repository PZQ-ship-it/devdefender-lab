from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_DIR = ROOT / "artifacts"
DEFAULT_OUT = ARTIFACT_DIR / "project_briefing_room_smoke.json"
DEFAULT_FEEDBACK_PLAN_OUT = ARTIFACT_DIR / "briefing_feedback_plan.json"
DEFAULT_FEEDBACK_PLAN_UPDATE_OUT = ARTIFACT_DIR / "briefing_plan_update.json"
DEFAULT_FEEDBACK_EXECUTION_GATE_OUT = ARTIFACT_DIR / "briefing_execution_gate.json"
DEFAULT_STAKEHOLDER_FEEDBACK = (
    "The current briefing loop is too one-way. The AI should listen to stakeholder feedback, "
    "ask clarifying questions, and update the execution plan before continuing."
)
DEFAULT_FEEDBACK_CLARIFICATIONS = [
    "Pause after the direction, risk, and requirements coverage summary, then pause again before the final execution plan.",
    (
        "Block execution on direction or priority changes, requirement-satisfaction objections, safety or privacy concerns, "
        "and evidence or test result disputes. Treat wording preferences, UI polish, and future integration ideas as "
        "non-blocking suggestions unless the stakeholder explicitly marks them as blocking."
    ),
    (
        "Write the interpreted execution plan back to the controlled Project Briefing Feedback Execution Plan block in "
        "plan.md, and keep machine-readable state in artifacts/briefing_plan_update.json plus the source feedback plan "
        "in artifacts/briefing_feedback_plan.json."
    ),
]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from devdefender_lab.briefing import (  # noqa: E402
    MockBriefingAdapter,
    contains_forbidden_briefing_artifact_fields,
    default_briefing_context,
)
from devdefender_lab.briefing_deck import write_briefing_deck  # noqa: E402
from devdefender_lab.briefing_workspace import WorkspaceBriefingAdapter  # noqa: E402


@dataclass(frozen=True)
class Step:
    name: str
    command: list[str]
    timeout: int
    report_path: Path
    retries: int = 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Project Briefing Room product smoke.")
    parser.add_argument("--repo", default=".", help="Repository path used by the briefing adapter.")
    parser.add_argument(
        "--agent-backend",
        choices=["mock", "workspace"],
        default="workspace",
        help="Briefing adapter backend.",
    )
    parser.add_argument("--artifact-dir", type=Path, default=ARTIFACT_DIR, help="Directory for briefing artifacts.")
    parser.add_argument(
        "--agent-input",
        type=Path,
        help="Optional provider-neutral agent briefing input JSON.",
    )
    parser.add_argument(
        "--feedback",
        default=DEFAULT_STAKEHOLDER_FEEDBACK,
        help="Stakeholder feedback used to verify the feedback-to-plan loop.",
    )
    parser.add_argument("--feedback-file", type=Path, help="Path to stakeholder feedback text.")
    parser.add_argument("--stt-text", help="Stakeholder feedback text produced by a speech-to-text step.")
    parser.add_argument(
        "--clarification",
        action="append",
        help="Clarification answer passed to the feedback plan generator. Repeat for multiple answers.",
    )
    parser.add_argument("--feedback-plan-out", type=Path, default=DEFAULT_FEEDBACK_PLAN_OUT)
    parser.add_argument("--feedback-plan-update-out", type=Path)
    parser.add_argument("--feedback-execution-gate-out", type=Path)
    parser.add_argument("--skip-feedback-plan", action="store_true", help="Skip the feedback-to-plan gate.")
    parser.add_argument("--timeout", type=float, default=120.0, help="Process timeout for each child step.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Path for the compact product smoke report.")
    parser.add_argument(
        "--skip-room-gates",
        action="store_true",
        help="Compatibility no-op. External room gates are no longer part of the default product smoke.",
    )
    args = parser.parse_args()

    try:
        report = run_smoke(
            repo=args.repo,
            agent_backend=args.agent_backend,
            artifact_dir=args.artifact_dir,
            agent_input=args.agent_input,
            feedback=args.feedback,
            feedback_file=args.feedback_file,
            stt_text=args.stt_text,
            clarification_answers=args.clarification,
            feedback_plan_out=args.feedback_plan_out,
            feedback_plan_update_out=args.feedback_plan_update_out,
            feedback_execution_gate_out=args.feedback_execution_gate_out,
            skip_feedback_plan=args.skip_feedback_plan,
            timeout=args.timeout,
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
    repo: str | Path = ".",
    agent_backend: str = "workspace",
    artifact_dir: Path = ARTIFACT_DIR,
    agent_input: Path | None = None,
    feedback: str | None = DEFAULT_STAKEHOLDER_FEEDBACK,
    feedback_file: Path | None = None,
    stt_text: str | None = None,
    clarification_answers: list[str] | None = None,
    feedback_plan_out: Path | None = None,
    feedback_plan_update_out: Path | None = None,
    feedback_execution_gate_out: Path | None = None,
    skip_feedback_plan: bool = False,
    timeout: float = 120.0,
    out: Path = DEFAULT_OUT,
) -> dict[str, object]:
    feedback_plan_output = feedback_plan_out or Path(artifact_dir) / "briefing_feedback_plan.json"
    feedback_plan_update_output = feedback_plan_update_out or Path(artifact_dir) / "briefing_plan_update.json"
    feedback_execution_gate_output = feedback_execution_gate_out or Path(artifact_dir) / "briefing_execution_gate.json"

    results = [
        build_briefing_artifacts(
            agent_backend=agent_backend,
            artifact_dir=artifact_dir,
            repo=repo,
            agent_input=agent_input,
        )
    ]
    if not skip_feedback_plan:
        answers = DEFAULT_FEEDBACK_CLARIFICATIONS if clarification_answers is None else clarification_answers
        results.extend(
            run_steps_until_failure(
                build_feedback_plan_steps(
                    artifact_dir=artifact_dir,
                    timeout=timeout,
                    feedback=feedback,
                    feedback_file=feedback_file,
                    stt_text=stt_text,
                    clarification_answers=answers,
                    feedback_plan_out=feedback_plan_output,
                )
            )
        )
        if _result_ok(results, "briefing_feedback_plan"):
            results.extend(
                run_steps_until_failure(
                    build_feedback_execution_steps(
                        timeout=timeout,
                        feedback_plan_out=feedback_plan_output,
                        feedback_plan_update_out=feedback_plan_update_output,
                        feedback_execution_gate_out=feedback_execution_gate_output,
                        plan_path=Path(repo) / "plan.md",
                    )
                )
            )

    expected_steps = ["briefing_artifacts"]
    if not skip_feedback_plan:
        expected_steps.extend(
            [
                "briefing_feedback_plan",
                "briefing_plan_update",
                "briefing_execution_gate",
            ]
        )
    report = build_report(
        results,
        expected_steps,
        feedback_plan_path=feedback_plan_output,
        skip_feedback_plan=skip_feedback_plan,
    )
    report["report_path"] = str(out)
    report["child_report_paths"] = {
        "briefing": display_path(Path(artifact_dir) / "briefing_deck" / "briefing_report.json"),
        "feedback_plan": None if skip_feedback_plan else display_path(feedback_plan_output),
        "plan_update": None if skip_feedback_plan else display_path(feedback_plan_update_output),
        "execution_gate": None if skip_feedback_plan else display_path(feedback_execution_gate_output),
    }
    write_report(report, out)
    return report


def build_briefing_artifacts(
    *,
    agent_backend: str = "workspace",
    artifact_dir: Path,
    repo: str | Path = ".",
    agent_input: Path | None = None,
) -> dict[str, object]:
    artifact_path = Path(artifact_dir)
    adapter = (
        WorkspaceBriefingAdapter(repo_path=repo, agent_input_path=agent_input)
        if agent_backend == "workspace"
        else MockBriefingAdapter()
    )
    context = default_briefing_context() if agent_backend == "mock" else None
    report = adapter.build_report(context) if context is not None else adapter.build_report()
    deck = write_briefing_deck(report, artifact_path)
    report_path = artifact_path / "briefing_deck" / "briefing_report.json"
    report_path.write_text(json.dumps(report.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    payload = {
        "ok": True,
        "agent_backend": agent_backend,
        "generated_by": report.generated_by,
        "briefing_report_path": display_path(report_path),
        "deck_path": display_path(deck.deck_path),
        "script_path": display_path(deck.script_path),
        "slide_count": deck.slide_count,
        "diagram_count": deck.diagram_count,
        "checks": {
            "briefing_report_written": report_path.exists(),
            "deck_written": bool(deck.deck_path and deck.deck_path.exists()),
            "presenter_script_written": bool(deck.script_path and deck.script_path.exists()),
            "mermaid_present": "```mermaid" in deck.deck_markdown,
            "summary_present": bool(report.audience_summary),
            "progress_present": bool(report.progress_status),
            "requirements_present": bool(report.requirements_coverage),
            "experiments_present": bool(report.experiment_results),
            "risks_present": bool(report.risks_and_unknowns),
            "questions_present": bool(report.stakeholder_questions),
            "next_asks_present": bool(report.follow_up_tasks),
            "evidence_pointers_present": bool(report.evidence_pointers),
            "no_forbidden_artifact_fields": not contains_forbidden_briefing_artifact_fields(report),
        },
    }
    return {
        "name": "briefing_artifacts",
        "ok": all(payload["checks"].values()),
        "return_code": 0,
        "report_path": display_path(report_path),
        "payload": payload,
    }


def build_feedback_plan_steps(
    *,
    artifact_dir: Path,
    timeout: float,
    feedback: str | None,
    feedback_file: Path | None,
    stt_text: str | None,
    clarification_answers: list[str],
    feedback_plan_out: Path,
) -> list[Step]:
    command = [
        sys.executable,
        str(ROOT / "scripts" / "briefing_feedback_plan.py"),
        "--briefing-report",
        str(Path(artifact_dir) / "briefing_deck" / "briefing_report.json"),
        "--out",
        str(feedback_plan_out),
    ]
    if feedback:
        command.extend(["--feedback", feedback])
    if feedback_file:
        command.extend(["--feedback-file", str(feedback_file)])
    if stt_text:
        command.extend(["--stt-text", stt_text])
    if not feedback and not feedback_file and not stt_text:
        command.append("--use-default-feedback")
    for answer in clarification_answers:
        command.extend(["--clarification", answer])
    return [
        Step(
            name="briefing_feedback_plan",
            command=command,
            timeout=int(timeout),
            report_path=_feedback_plan_step_report_path(feedback_plan_out),
        )
    ]


def build_feedback_execution_steps(
    *,
    timeout: float,
    feedback_plan_out: Path,
    feedback_plan_update_out: Path,
    feedback_execution_gate_out: Path,
    plan_path: Path = Path("plan.md"),
) -> list[Step]:
    return [
        Step(
            name="briefing_plan_update",
            command=[
                sys.executable,
                str(ROOT / "scripts" / "apply_briefing_feedback_plan.py"),
                "--feedback-plan",
                str(feedback_plan_out),
                "--plan",
                str(plan_path),
                "--out",
                str(feedback_plan_update_out),
            ],
            timeout=int(timeout),
            report_path=feedback_plan_update_out,
        ),
        Step(
            name="briefing_execution_gate",
            command=[
                sys.executable,
                str(ROOT / "scripts" / "briefing_execution_gate.py"),
                "--plan-update",
                str(feedback_plan_update_out),
                "--out",
                str(feedback_execution_gate_out),
            ],
            timeout=int(timeout),
            report_path=feedback_execution_gate_out,
        ),
    ]


def run_steps_until_failure(steps: list[Step]) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for step in steps:
        result = run_step_with_retries(step)
        results.append(result)
        if not result.get("ok"):
            break
    return results


def run_step_with_retries(step: Step) -> dict[str, object]:
    attempts = max(1, step.retries + 1)
    failures: list[dict[str, object]] = []
    for attempt in range(1, attempts + 1):
        result = run_step(step)
        if result.get("ok"):
            if attempt > 1:
                result["attempt_count"] = attempt
                result["previous_failures"] = summarize_retry_failures(failures)
            return result
        failures.append(result)
    final = failures[-1] if failures else run_step(step)
    final["attempt_count"] = attempts
    if len(failures) > 1:
        final["previous_failures"] = summarize_retry_failures(failures[:-1])
    return final


def run_step(step: Step) -> dict[str, object]:
    before = _file_stat(step.report_path)
    try:
        process = subprocess.run(
            step.command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=step.timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "name": step.name,
            "ok": False,
            "return_code": None,
            "report_path": display_path(step.report_path),
            "error": f"timeout after {step.timeout}s: {_safe_stderr(str(exc))}",
            "payload": {},
        }

    stdout_payload = _parse_json_output(process.stdout)
    after = _file_stat(step.report_path)
    file_payload = load_json(step.report_path) if step.report_path.exists() else {}
    payload = stdout_payload if stdout_payload else file_payload
    if stdout_payload and after == before:
        step.report_path.parent.mkdir(parents=True, exist_ok=True)
        step.report_path.write_text(json.dumps(stdout_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {
        "name": step.name,
        "ok": process.returncode == 0 and bool(payload.get("ok", process.returncode == 0)),
        "return_code": process.returncode,
        "report_path": display_path(step.report_path),
        "stderr": _safe_stderr(process.stderr),
        "payload": payload,
    }


def build_report(
    results: list[dict[str, object]],
    expected_steps: list[str],
    *,
    feedback_plan_path: Path | None = None,
    skip_feedback_plan: bool = False,
) -> dict[str, object]:
    checks = {step: _result_ok(results, step) for step in expected_steps}
    cross_checks = build_cross_checks(
        results,
        feedback_plan_path=feedback_plan_path,
        skip_feedback_plan=skip_feedback_plan,
    )
    return {
        "ok": all(checks.values()) and _cross_checks_pass(cross_checks),
        "schema_version": "1",
        "mode": "codex_native",
        "external_room_gates": "skipped",
        "skip_feedback_plan": skip_feedback_plan,
        "checks": checks,
        "cross_checks": cross_checks,
        "results": summarize_results(results),
    }


def build_cross_checks(
    results: list[dict[str, object]],
    *,
    feedback_plan_path: Path | None = None,
    skip_feedback_plan: bool = False,
) -> dict[str, bool]:
    briefing = _payload_for(results, "briefing_artifacts")
    briefing_checks = _dict(briefing.get("checks"))
    feedback = _payload_for(results, "briefing_feedback_plan")
    feedback_checks = _dict(feedback.get("checks"))
    plan_update = _payload_for(results, "briefing_plan_update")
    execution_gate = _payload_for(results, "briefing_execution_gate")
    feedback_artifact = summarize_feedback_plan_artifact(feedback_plan_path)
    checks = {
        "briefing_deck_has_required_sections_ok": bool(
            briefing_checks.get("summary_present")
            and briefing_checks.get("progress_present")
            and briefing_checks.get("requirements_present")
            and briefing_checks.get("experiments_present")
            and briefing_checks.get("risks_present")
            and briefing_checks.get("questions_present")
            and briefing_checks.get("next_asks_present")
        ),
        "briefing_deck_has_diagram_ok": bool(briefing_checks.get("mermaid_present")),
        "briefing_artifacts_no_forbidden_fields_ok": bool(briefing_checks.get("no_forbidden_artifact_fields")),
        "briefing_feedback_plan_ok": skip_feedback_plan or _result_ok(results, "briefing_feedback_plan"),
        "briefing_plan_update_ok": skip_feedback_plan or _result_ok(results, "briefing_plan_update"),
        "briefing_execution_gate_ok": skip_feedback_plan or _result_ok(results, "briefing_execution_gate"),
        "briefing_execution_gate_can_continue_ok": skip_feedback_plan
        or bool(execution_gate.get("can_continue") is True and execution_gate.get("source_of_truth") is True),
        "feedback_plan_has_clarification_questions_ok": skip_feedback_plan
        or bool(feedback_checks.get("has_clarification_questions")),
        "feedback_plan_has_updated_execution_plan_ok": skip_feedback_plan
        or bool(feedback_checks.get("has_updated_execution_plan")),
        "feedback_plan_has_plan_changes_ok": skip_feedback_plan or bool(feedback_checks.get("has_plan_changes")),
        "feedback_plan_artifact_present_ok": skip_feedback_plan or bool(feedback_artifact.get("present")),
        "feedback_plan_artifact_has_concerns_ok": skip_feedback_plan
        or bool(feedback_artifact.get("has_interpreted_concerns")),
        "feedback_plan_artifact_has_clarification_questions_ok": skip_feedback_plan
        or bool(feedback_artifact.get("has_clarification_questions")),
        "feedback_plan_artifact_has_plan_changes_ok": skip_feedback_plan
        or bool(feedback_artifact.get("has_plan_changes")),
        "feedback_plan_artifact_has_actionable_next_steps_ok": skip_feedback_plan
        or bool(feedback_artifact.get("has_actionable_next_steps")),
        "feedback_plan_artifact_no_forbidden_fields_ok": skip_feedback_plan
        or bool(feedback_artifact.get("no_forbidden_artifact_fields")),
        "no_forbidden_artifact_fields_ok": bool(briefing_checks.get("no_forbidden_artifact_fields"))
        and (skip_feedback_plan or not contains_forbidden_briefing_artifact_fields(feedback))
        and (skip_feedback_plan or not contains_forbidden_briefing_artifact_fields(plan_update))
        and (skip_feedback_plan or not contains_forbidden_briefing_artifact_fields(execution_gate))
        and (skip_feedback_plan or bool(feedback_artifact.get("no_forbidden_artifact_fields"))),
        "external_room_gates_skipped": True,
        "advanced_audit_included": False,
    }
    return checks


def _cross_checks_pass(checks: dict[str, bool]) -> bool:
    return all(value for key, value in checks.items() if key.endswith("_ok") or key.endswith("_skipped"))


def summarize_results(results: list[dict[str, object]]) -> list[dict[str, object]]:
    summarized: list[dict[str, object]] = []
    for result in results:
        item = {
            "name": result.get("name"),
            "ok": bool(result.get("ok")),
            "return_code": result.get("return_code"),
            "report_path": result.get("report_path"),
            "payload": summarize_payload(result.get("payload")),
        }
        if result.get("attempt_count") is not None:
            item["attempt_count"] = result.get("attempt_count")
        if result.get("previous_failures") is not None:
            item["previous_failures"] = result.get("previous_failures")
        summarized.append(item)
    return summarized


def summarize_feedback_plan_artifact(path: Path | None) -> dict[str, object]:
    if path is None:
        return {
            "present": False,
            "has_interpreted_concerns": False,
            "has_clarification_questions": False,
            "has_plan_changes": False,
            "has_actionable_next_steps": False,
            "no_forbidden_artifact_fields": False,
        }
    payload = load_json(Path(path))
    updated_plan = payload.get("updated_execution_plan") if isinstance(payload.get("updated_execution_plan"), dict) else {}
    next_steps = updated_plan.get("next_steps") if isinstance(updated_plan, dict) else []
    summary = {
        "present": Path(path).exists() and bool(payload),
        "has_interpreted_concerns": bool(payload.get("interpreted_concerns")),
        "has_clarification_questions": bool(payload.get("clarification_questions")),
        "has_plan_changes": bool(payload.get("plan_changes")),
        "has_actionable_next_steps": isinstance(next_steps, list) and any(str(step).strip() for step in next_steps),
        "no_forbidden_artifact_fields": bool(payload) and not contains_forbidden_briefing_artifact_fields(payload),
    }
    if payload.get("needs_follow_up") is not None:
        summary["needs_follow_up"] = bool(payload.get("needs_follow_up"))
    return summary


def summarize_retry_failures(results: list[dict[str, object]]) -> list[dict[str, object]]:
    failures: list[dict[str, object]] = []
    for result in results:
        failures.append(
            {
                "return_code": result.get("return_code"),
                "report_path": result.get("report_path"),
            }
        )
    return failures


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
        "feedback_summary",
        "needs_follow_up",
        "concern_count",
        "clarification_question_count",
        "plan_change_count",
        "updated_next_step_count",
        "evidence_pointer_count",
        "ready_for_execution",
        "execution_source_of_truth",
        "pending_question_count",
        "answered_question_count",
        "can_continue",
        "source_of_truth",
        "blocking_reason",
        "next_steps",
        "pending_questions",
        "checks",
    ]
    return {key: payload[key] for key in keep_keys if key in payload}


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


def _feedback_plan_step_report_path(feedback_plan_out: Path) -> Path:
    return Path(feedback_plan_out).with_name(f"{Path(feedback_plan_out).stem}.smoke.json")


def _file_stat(path: Path) -> tuple[int, int] | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return (stat.st_mtime_ns, stat.st_size)


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


def _payload_for(results: list[dict[str, object]], name: str) -> dict[str, object]:
    for result in results:
        if result.get("name") == name and isinstance(result.get("payload"), dict):
            return result["payload"]  # type: ignore[return-value]
    return {}


def _result_ok(results: list[dict[str, object]], name: str) -> bool:
    return any(result.get("name") == name and result.get("ok") is True for result in results)


def _dict(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


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
