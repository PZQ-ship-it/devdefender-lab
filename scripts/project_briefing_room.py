from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_DIR = ROOT / "artifacts" / "project_briefing_room"
DEFAULT_OUT = ARTIFACT_DIR / "session.json"
DEFAULT_SESSION_MD = ARTIFACT_DIR / "session.md"
DEFAULT_FEEDBACK = (
    "The briefing should listen to my feedback, clarify my intent, and update the execution plan before continuing."
)

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from devdefender_lab.briefing import contains_forbidden_briefing_artifact_fields  # noqa: E402
from scripts.project_briefing_room_smoke import (  # noqa: E402
    DEFAULT_FEEDBACK_CLARIFICATIONS,
    load_json,
    run_smoke,
    write_report,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one Project Briefing Room session.")
    parser.add_argument("--repo", default=".", help="Repository path used by the briefing adapter.")
    parser.add_argument("--agent-backend", choices=["mock", "workspace"], default="workspace")
    parser.add_argument("--agent-input", type=Path, help="Optional provider-neutral agent briefing input JSON.")
    parser.add_argument("--artifact-dir", type=Path, default=ARTIFACT_DIR, help="Directory for session artifacts.")
    parser.add_argument("--feedback", default=DEFAULT_FEEDBACK, help="Stakeholder feedback to interpret.")
    parser.add_argument("--feedback-file", type=Path, help="Path to bounded stakeholder feedback text.")
    parser.add_argument("--stt-text", help="Bounded speech-to-text feedback text.")
    parser.add_argument(
        "--clarification",
        action="append",
        default=[],
        help="Clarification answer. Repeat for multiple answers.",
    )
    parser.add_argument(
        "--use-default-clarifications",
        action="store_true",
        help="Use deterministic sample clarification answers for a fully passing local demo.",
    )
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Machine-readable session JSON path.")
    parser.add_argument("--session-md", type=Path, default=DEFAULT_SESSION_MD, help="Human-readable session summary path.")
    args = parser.parse_args()

    clarifications = DEFAULT_FEEDBACK_CLARIFICATIONS if args.use_default_clarifications else args.clarification
    try:
        report = run_session(
            repo=args.repo,
            agent_backend=args.agent_backend,
            agent_input=args.agent_input,
            artifact_dir=args.artifact_dir,
            feedback=args.feedback,
            feedback_file=args.feedback_file,
            stt_text=args.stt_text,
            clarification_answers=clarifications,
            timeout=args.timeout,
            out=args.out,
            session_md=args.session_md,
        )
    except Exception as exc:
        report = {
            "ok": False,
            "can_continue": False,
            "error": _safe_error(exc),
            "session_path": str(args.session_md),
            "report_path": str(args.out),
        }
        write_report(report, args.out)
    print(json.dumps(report, indent=2, ensure_ascii=False), file=sys.stdout if report.get("ok") else sys.stderr)
    return 0 if report.get("ok") else 1


def run_session(
    *,
    repo: str | Path = ".",
    agent_backend: str = "workspace",
    agent_input: Path | None = None,
    artifact_dir: Path = ARTIFACT_DIR,
    feedback: str | None = DEFAULT_FEEDBACK,
    feedback_file: Path | None = None,
    stt_text: str | None = None,
    clarification_answers: list[str] | None = None,
    timeout: float = 120.0,
    out: Path = DEFAULT_OUT,
    session_md: Path = DEFAULT_SESSION_MD,
) -> dict[str, object]:
    artifact_path = Path(artifact_dir)
    smoke_out = artifact_path / "smoke.json"
    smoke_report = run_smoke(
        repo=repo,
        agent_backend=agent_backend,
        artifact_dir=artifact_path,
        agent_input=agent_input,
        feedback=feedback,
        feedback_file=feedback_file,
        stt_text=stt_text,
        clarification_answers=[] if clarification_answers is None else clarification_answers,
        feedback_plan_out=artifact_path / "briefing_feedback_plan.json",
        feedback_plan_update_out=artifact_path / "briefing_plan_update.json",
        feedback_execution_gate_out=artifact_path / "briefing_execution_gate.json",
        timeout=timeout,
        out=smoke_out,
    )
    paths = _session_paths(artifact_path, session_md, smoke_report)
    payloads = {name: load_json(path) for name, path in paths.items() if path is not None}
    session_markdown = render_session_markdown(
        smoke_report=smoke_report,
        briefing=payloads.get("briefing_report", {}),
        feedback_plan=payloads.get("feedback_plan", {}),
        plan_update=payloads.get("plan_update", {}),
        execution_gate=payloads.get("execution_gate", {}),
        paths=paths,
    )
    if contains_forbidden_briefing_artifact_fields(session_markdown):
        raise ValueError("Session summary contains forbidden artifact fields.")
    session_md.parent.mkdir(parents=True, exist_ok=True)
    session_md.write_text(session_markdown, encoding="utf-8")
    execution_gate = payloads.get("execution_gate", {})
    feedback_plan = payloads.get("feedback_plan", {})
    pending_questions = _pending_questions(feedback_plan, execution_gate)
    report = {
        "schema_version": "1",
        "ok": True,
        "can_continue": bool(execution_gate.get("can_continue") is True),
        "source_of_truth": bool(execution_gate.get("source_of_truth") is True),
        "blocking_reason": str(execution_gate.get("blocking_reason") or ""),
        "pending_questions": pending_questions,
        "next_steps": _string_list(execution_gate.get("next_steps")),
        "session_path": _display_path(session_md),
        "report_path": _display_path(out),
        "smoke_report_path": _display_path(smoke_out),
        "artifact_paths": {name: _display_path(path) for name, path in paths.items() if path is not None},
        "checks": {
            "briefing_generated": bool(payloads.get("briefing_report")),
            "feedback_plan_generated": bool(payloads.get("feedback_plan")),
            "plan_update_generated": bool(payloads.get("plan_update")),
            "execution_gate_generated": bool(payloads.get("execution_gate")),
            "session_markdown_written": session_md.exists(),
            "no_forbidden_artifact_fields": not contains_forbidden_briefing_artifact_fields(
                {
                    "report": {
                        "can_continue": bool(execution_gate.get("can_continue") is True),
                        "pending_question_count": len(pending_questions),
                    },
                    "session_markdown": session_markdown,
                }
            ),
        },
    }
    report["ok"] = all(report["checks"].values())
    write_report(report, out)
    return report


def render_session_markdown(
    *,
    smoke_report: dict[str, object],
    briefing: dict[str, object],
    feedback_plan: dict[str, object],
    plan_update: dict[str, object],
    execution_gate: dict[str, object],
    paths: dict[str, Path | None],
) -> str:
    project_name = str(briefing.get("project_name") or feedback_plan.get("project_name") or "Project Briefing Room")
    can_continue = execution_gate.get("can_continue") is True
    status = "ready_to_continue" if can_continue else "needs_clarification"
    lines = [
        f"# {project_name} Briefing Session",
        "",
        f"- Status: `{status}`",
        f"- Can continue: `{str(can_continue).lower()}`",
        f"- Source of truth: `{str(execution_gate.get('source_of_truth') is True).lower()}`",
        f"- Smoke ok: `{str(smoke_report.get('ok') is True).lower()}`",
        "",
        "## Stakeholder Summary",
        "",
        _fallback_text(briefing.get("audience_summary"), "No briefing summary was generated."),
        "",
        "## Architecture",
        "",
    ]
    lines.extend(_diagram_lines(briefing))
    lines.extend(["", "## Progress", ""])
    lines.extend(_model_list_lines(briefing.get("progress_status"), "label", "plain_language_summary"))
    lines.extend(["", "## Requirements Coverage", ""])
    lines.extend(_model_list_lines(briefing.get("requirements_coverage"), "requirement", "explanation", status_key="status"))
    lines.extend(["", "## Experiment Results", ""])
    lines.extend(_model_list_lines(briefing.get("experiment_results"), "name", "summary", status_key="status"))
    lines.extend(["", "## Risks And Decisions", ""])
    lines.extend(_model_list_lines(briefing.get("risks_and_unknowns"), "risk", "mitigation", status_key="severity"))
    lines.extend(["", "## Stakeholder Feedback", ""])
    lines.append(_fallback_text(feedback_plan.get("feedback_summary"), "No feedback summary was generated."))
    lines.extend(["", "### Interpreted Concerns", ""])
    lines.extend(_model_list_lines(feedback_plan.get("interpreted_concerns"), "concern", "category", status_key="priority"))
    lines.extend(["", "### Clarification Questions", ""])
    questions = _clarification_lines(feedback_plan)
    lines.extend(questions if questions else ["- No clarification questions recorded."])
    lines.extend(["", "## Updated Execution Plan", ""])
    updated_plan = feedback_plan.get("updated_execution_plan") if isinstance(feedback_plan.get("updated_execution_plan"), dict) else {}
    lines.append(_fallback_text(updated_plan.get("summary"), "No updated plan summary was generated."))
    lines.extend(["", "### Next Steps", ""])
    gate_steps = _string_list(execution_gate.get("next_steps"))
    plan_steps = _string_list(updated_plan.get("next_steps")) if isinstance(updated_plan, dict) else []
    lines.extend(_numbered_lines(gate_steps or plan_steps))
    lines.extend(["", "### Acceptance Criteria", ""])
    lines.extend(_bullet_lines(_string_list(updated_plan.get("acceptance_criteria")) if isinstance(updated_plan, dict) else []))
    lines.extend(["", "## Execution Gate", ""])
    if can_continue:
        lines.append("- Ready: continue in the same Codex session from this updated plan.")
    else:
        reason = str(execution_gate.get("blocking_reason") or "Pending clarification is required before execution continues.")
        lines.append(f"- Blocked: {reason}")
    lines.extend(["", "## Artifacts", ""])
    for name, path in paths.items():
        if path is not None:
            lines.append(f"- `{name}`: `{_display_path(path)}`")
    lines.append("")
    return "\n".join(lines)


def _session_paths(
    artifact_dir: Path,
    session_md: Path,
    smoke_report: dict[str, object],
) -> dict[str, Path | None]:
    child_paths = smoke_report.get("child_report_paths") if isinstance(smoke_report.get("child_report_paths"), dict) else {}
    return {
        "session_md": session_md,
        "briefing_report": _path_from_child(child_paths.get("briefing")) or artifact_dir / "briefing_deck" / "briefing_report.json",
        "slides": artifact_dir / "briefing_deck" / "slides.md",
        "presenter_script": artifact_dir / "briefing_deck" / "presenter_script.md",
        "feedback_plan": _path_from_child(child_paths.get("feedback_plan")) or artifact_dir / "briefing_feedback_plan.json",
        "plan_update": _path_from_child(child_paths.get("plan_update")) or artifact_dir / "briefing_plan_update.json",
        "execution_gate": _path_from_child(child_paths.get("execution_gate")) or artifact_dir / "briefing_execution_gate.json",
    }


def _path_from_child(value: object) -> Path | None:
    if not isinstance(value, str) or not value:
        return None
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _diagram_lines(briefing: dict[str, object]) -> list[str]:
    diagrams = briefing.get("architecture_diagrams")
    if not isinstance(diagrams, list) or not diagrams:
        return ["- No architecture diagram was generated."]
    lines: list[str] = []
    for item in diagrams[:4]:
        if not isinstance(item, dict):
            continue
        lines.append(f"### {_fallback_text(item.get('title'), 'Architecture View')}")
        lines.append("")
        lines.append(_fallback_text(item.get("audience_goal"), "No diagram goal was generated."))
        hint = item.get("mermaid_hint")
        if isinstance(hint, str) and hint.strip():
            lines.extend(["", "```mermaid", hint.strip(), "```", ""])
    return lines or ["- No architecture diagram was generated."]


def _model_list_lines(
    value: object,
    title_key: str,
    body_key: str,
    *,
    status_key: str | None = None,
) -> list[str]:
    if not isinstance(value, list) or not value:
        return ["- None recorded."]
    lines: list[str] = []
    for item in value[:8]:
        if not isinstance(item, dict):
            continue
        title = _fallback_text(item.get(title_key), "Untitled")
        body = _fallback_text(item.get(body_key), "")
        status = f" `{item.get(status_key)}`" if status_key and item.get(status_key) else ""
        lines.append(f"-{status} **{title}**: {body}" if body else f"-{status} **{title}**")
    return lines or ["- None recorded."]


def _clarification_lines(feedback_plan: dict[str, object]) -> list[str]:
    questions = feedback_plan.get("clarification_questions")
    if not isinstance(questions, list):
        return []
    lines: list[str] = []
    for index, item in enumerate(questions, start=1):
        if not isinstance(item, dict):
            continue
        status = item.get("status") or "pending"
        question = _fallback_text(item.get("question"), "Clarification question")
        lines.append(f"{index}. `{status}` {question}")
        answer = item.get("answer_summary")
        if answer:
            lines.append(f"   Answer: {_fallback_text(answer, '')}")
    return lines


def _pending_questions(feedback_plan: dict[str, object], execution_gate: dict[str, object]) -> list[str]:
    gate_questions = _string_list(execution_gate.get("pending_questions"))
    if gate_questions:
        return gate_questions
    questions = feedback_plan.get("clarification_questions")
    if not isinstance(questions, list):
        return []
    pending = []
    for item in questions:
        if isinstance(item, dict) and item.get("status") == "pending" and item.get("question"):
            pending.append(str(item["question"]))
    return pending


def _numbered_lines(values: list[str]) -> list[str]:
    return [f"{index}. {value}" for index, value in enumerate(values, start=1)] if values else ["1. No next steps recorded."]


def _bullet_lines(values: list[str]) -> list[str]:
    return [f"- {value}" for value in values] if values else ["- None recorded."]


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _fallback_text(value: object, fallback: str) -> str:
    text = " ".join(str(value).split()) if value is not None else ""
    return text if text else fallback


def _safe_error(exc: BaseException) -> str:
    text = " ".join(str(exc).split())
    replacements = {
        "LIVEKIT_API_SECRET": "LIVEKIT_SECRET_ENV",
        "LIVEKIT_API_KEY": "LIVEKIT_KEY_ENV",
        "OPENAI_API_KEY": "OPENAI_KEY_ENV",
    }
    for source, replacement in replacements.items():
        text = text.replace(source, replacement)
    return text[:500]


if __name__ == "__main__":
    raise SystemExit(main())
