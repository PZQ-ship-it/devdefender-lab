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
    updated_plan = feedback_plan.get("updated_execution_plan") if isinstance(feedback_plan.get("updated_execution_plan"), dict) else {}
    gate_steps = _string_list(execution_gate.get("next_steps"))
    plan_steps = _string_list(updated_plan.get("next_steps")) if isinstance(updated_plan, dict) else []
    feedback_summary = _fallback_text(feedback_plan.get("feedback_summary"), "No stakeholder feedback was captured.")
    lines = [
        f"# {project_name} Stakeholder Briefing",
        "",
        "## Executive Summary",
        "",
        f"- **Current decision state**: `{status}`.",
        f"- **Project direction**: {_fallback_text(briefing.get('task_goal'), 'Brief the current project status and update the execution plan from stakeholder feedback.')}",
        f"- **Plain-language conclusion**: {_fallback_text(briefing.get('audience_summary'), 'The briefing was generated from repo-visible project facts.')}",
        f"- **Stakeholder signal**: {feedback_summary}",
        f"- **Execution gate**: {_gate_sentence(can_continue, execution_gate)}",
        "",
        "## Project Snapshot",
        "",
        "- **What this product does**: It lets a code agent brief a stakeholder on current project status, listen to feedback, ask clarifying questions, and produce the next execution plan.",
        f"- **What was inspected**: {_source_summary(briefing, smoke_report)}",
        f"- **What happens next**: {_fallback_text((gate_steps or plan_steps or ['No next step recorded.'])[0], 'No next step recorded.')}",
        "",
        "## Architecture In Plain Language",
        "",
    ]
    lines.extend(_diagram_lines(briefing))
    lines.extend(["", "## Progress For Stakeholders", ""])
    lines.extend(_model_list_lines(_public_items(briefing.get("progress_status")), "label", "plain_language_summary", max_items=6))
    lines.extend(["", "## Requirement Fit", ""])
    lines.extend(_model_list_lines(_dedupe_items(briefing.get("requirements_coverage"), "requirement"), "requirement", "explanation", status_key="status", max_items=6))
    lines.extend(["", "## Validation Snapshot", ""])
    lines.extend(_validation_snapshot(smoke_report, briefing, execution_gate))
    lines.extend(["", "## Risks And Decisions Needed", ""])
    lines.extend(_model_list_lines(briefing.get("risks_and_unknowns"), "risk", "mitigation", status_key="severity", max_items=6))
    lines.extend(["", "## Feedback Listening Checkpoint", ""])
    lines.append("Pause for stakeholder confirmation before treating this plan as final.")
    lines.append("")
    lines.append(feedback_summary)
    lines.extend(["", "### Interpreted Stakeholder Concerns", ""])
    lines.extend(_model_list_lines(feedback_plan.get("interpreted_concerns"), "concern", "category", status_key="priority", max_items=5))
    lines.extend(["", "### Clarification Questions", ""])
    questions = _clarification_lines(feedback_plan)
    lines.extend(questions if questions else ["- No clarification questions recorded."])
    lines.extend(["", "## Updated Execution Plan", ""])
    lines.append(_fallback_text(updated_plan.get("summary"), "No updated plan summary was generated."))
    lines.extend(["", "### Next Steps", ""])
    lines.extend(_numbered_lines(gate_steps or plan_steps))
    lines.extend(["", "### Acceptance Criteria", ""])
    lines.extend(_bullet_lines(_string_list(updated_plan.get("acceptance_criteria")) if isinstance(updated_plan, dict) else []))
    lines.extend(["", "## Continue Or Stop", ""])
    if can_continue:
        lines.append("- Ready: continue in the same Codex session from this updated plan.")
    else:
        reason = str(execution_gate.get("blocking_reason") or "Pending clarification is required before execution continues.")
        lines.append(f"- Blocked: {reason}")
    pending_questions = _pending_questions(feedback_plan, execution_gate)
    if pending_questions:
        lines.extend(["", "Pending stakeholder answers:"])
        lines.extend(_numbered_lines(pending_questions))
    lines.extend(["", "## Technical Appendix", ""])
    lines.extend(
        [
            f"- Status: `{status}`",
            f"- Can continue: `{str(can_continue).lower()}`",
            f"- Source of truth: `{str(execution_gate.get('source_of_truth') is True).lower()}`",
            f"- Smoke ok: `{str(smoke_report.get('ok') is True).lower()}`",
        ]
    )
    lines.extend(["", "### Detailed Validation", ""])
    lines.extend(_model_list_lines(briefing.get("experiment_results"), "name", "summary", status_key="status", max_items=8))
    lines.extend(["", "### Artifacts", ""])
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
    max_items: int = 8,
) -> list[str]:
    if not isinstance(value, list) or not value:
        return ["- None recorded."]
    lines: list[str] = []
    for item in value[:max_items]:
        if not isinstance(item, dict):
            continue
        title = _fallback_text(item.get(title_key), "Untitled")
        body = _fallback_text(item.get(body_key), "")
        status = f" `{item.get(status_key)}`" if status_key and item.get(status_key) else ""
        lines.append(f"-{status} **{title}**: {body}" if body else f"-{status} **{title}**")
    return lines or ["- None recorded."]


def _public_items(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    items: list[dict[str, object]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        text = " ".join(str(item.get(key, "")) for key in ("label", "plain_language_summary", "name", "summary"))
        if _is_technical_noise(text):
            continue
        items.append(item)
    return items


def _dedupe_items(value: object, key: str) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    seen: set[str] = set()
    items: list[dict[str, object]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        marker = str(item.get(key, "")).strip().casefold().rstrip(".")
        if not marker or marker in seen:
            continue
        seen.add(marker)
        items.append(item)
    return items


def _validation_snapshot(
    smoke_report: dict[str, object],
    briefing: dict[str, object],
    execution_gate: dict[str, object],
) -> list[str]:
    lines = []
    if smoke_report.get("ok") is True:
        lines.append("- **Local product gate**: passed.")
    else:
        lines.append("- **Local product gate**: not confirmed.")
    if execution_gate.get("source_of_truth") is True:
        lines.append("- **Execution plan state**: accepted as the current source of truth.")
    elif execution_gate.get("can_continue") is True:
        lines.append("- **Execution plan state**: ready to continue, but source-of-truth status is not confirmed.")
    else:
        lines.append("- **Execution plan state**: waiting for stakeholder clarification before continuing.")
    public_results = _public_items(briefing.get("experiment_results"))
    if public_results:
        first = public_results[0]
        lines.append(
            f"- **Most relevant check**: {_fallback_text(first.get('summary'), _fallback_text(first.get('name'), 'No validation detail recorded.'))}"
        )
    return lines


def _source_summary(briefing: dict[str, object], smoke_report: dict[str, object]) -> str:
    generated_by = _fallback_text(briefing.get("generated_by"), "workspace briefing adapter")
    child_paths = smoke_report.get("child_report_paths")
    artifact_count = len(child_paths) if isinstance(child_paths, dict) else 0
    return f"{generated_by}; {artifact_count} generated artifact group(s)."


def _gate_sentence(can_continue: bool, execution_gate: dict[str, object]) -> str:
    if can_continue:
        return "Ready to continue from the updated plan after stakeholder confirmation."
    reason = str(execution_gate.get("blocking_reason") or "Stakeholder clarification is still required.")
    return f"Stop before implementation. {reason}"


def _is_technical_noise(value: str) -> bool:
    lowered = value.casefold()
    return any(
        marker in lowered
        for marker in (
            "artifacts/",
            ".json",
            "pytest",
            "changed file",
            "dirty worktree",
            "workspace has pending edits",
            "smoke",
        )
    )


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
