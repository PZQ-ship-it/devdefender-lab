from __future__ import annotations

import json
from pathlib import Path

from devdefender_lab.briefing import contains_forbidden_briefing_artifact_fields
from devdefender_lab.briefing_feedback import BriefingFeedbackPlan, load_feedback_plan


PLAN_UPDATE_START = "<!-- DEVDEFENDER_BRIEFING_FEEDBACK_PLAN:START -->"
PLAN_UPDATE_END = "<!-- DEVDEFENDER_BRIEFING_FEEDBACK_PLAN:END -->"


def apply_feedback_plan_to_markdown(
    *,
    feedback_plan_path: Path,
    plan_path: Path = Path("plan.md"),
    out: Path = Path("artifacts/briefing_plan_update.json"),
    dry_run: bool = False,
) -> dict[str, object]:
    plan = load_feedback_plan(feedback_plan_path)
    if plan is None:
        report = {
            "ok": False,
            "error": f"Invalid or unsafe feedback plan: {feedback_plan_path}",
            "feedback_plan_path": str(feedback_plan_path),
            "plan_path": str(plan_path),
        }
        write_update_report(report, out)
        return report

    existing = _read_text(plan_path)
    section = render_feedback_plan_section(plan, feedback_plan_path=feedback_plan_path)
    updated_text = replace_marked_section(existing, section)
    changed = updated_text != existing
    if not dry_run:
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        plan_path.write_text(updated_text, encoding="utf-8")

    pending_questions = [question for question in plan.clarification_questions if question.status == "pending"]
    answered_questions = [question for question in plan.clarification_questions if question.status == "answered"]
    execution_source_of_truth = not plan.needs_follow_up
    execution_next_steps = list(plan.updated_execution_plan.next_steps) if execution_source_of_truth else []
    blocking_reason = (
        ""
        if execution_source_of_truth
        else f"{len(pending_questions)} clarification question(s) must be answered before execution continues."
    )
    report: dict[str, object] = {
        "ok": True,
        "feedback_plan_path": str(feedback_plan_path),
        "plan_path": str(plan_path),
        "report_path": str(out),
        "dry_run": dry_run,
        "changed": changed,
        "ready_for_execution": not plan.needs_follow_up,
        "execution_source_of_truth": execution_source_of_truth,
        "blocking_reason": blocking_reason,
        "execution_next_steps": execution_next_steps,
        "pending_questions": [question.question for question in pending_questions],
        "needs_follow_up": plan.needs_follow_up,
        "pending_question_count": len(pending_questions),
        "answered_question_count": len(answered_questions),
        "plan_change_count": len(plan.plan_changes),
        "next_step_count": len(plan.updated_execution_plan.next_steps),
        "checks": {
            "feedback_plan_loaded": True,
            "section_markers_present": PLAN_UPDATE_START in updated_text and PLAN_UPDATE_END in updated_text,
            "pending_questions_preserved": bool(pending_questions) == plan.needs_follow_up,
            "plan_written": dry_run or plan_path.exists(),
            "no_forbidden_artifact_fields": not contains_forbidden_briefing_artifact_fields(
                {
                    "report": {
                        "feedback_plan_path": str(feedback_plan_path),
                        "plan_path": str(plan_path),
                        "ready_for_execution": not plan.needs_follow_up,
                        "execution_source_of_truth": execution_source_of_truth,
                        "pending_question_count": len(pending_questions),
                    },
                    "section": section,
                }
            ),
        },
    }
    report["ok"] = all(report["checks"].values())
    write_update_report(report, out)
    return report


def render_feedback_plan_section(plan: BriefingFeedbackPlan, *, feedback_plan_path: Path) -> str:
    status = "ready_for_execution" if not plan.needs_follow_up else "needs_clarification"
    lines = [
        PLAN_UPDATE_START,
        "## Project Briefing Feedback Execution Plan",
        "",
        f"- Source: `{feedback_plan_path.as_posix()}`",
        f"- Project: {plan.project_name}",
        f"- Status: `{status}`",
        f"- Follow-up required: `{str(plan.needs_follow_up).lower()}`",
        f"- Execution source of truth: `{str(not plan.needs_follow_up).lower()}`",
        "",
        "### Stakeholder Signal",
        "",
        f"- {plan.feedback_summary}",
        "",
        "### Decisions",
        "",
    ]
    lines.extend(_bullet_lines(plan.decisions, empty="- No confirmed decisions yet."))
    lines.extend(["", "### Plan Changes", ""])
    if plan.plan_changes:
        for change in plan.plan_changes:
            lines.append(f"- `{change.change_type}` `{change.priority}`: {change.title}")
            lines.append(f"  Rationale: {change.rationale}")
    else:
        lines.append("- No plan changes recorded.")
    lines.extend(["", "### Updated Next Steps", ""])
    lines.extend(_numbered_lines(plan.updated_execution_plan.next_steps))
    lines.extend(["", "### Execution Gate", ""])
    if plan.needs_follow_up:
        lines.append("- Blocked: pending clarification questions must be answered before execution continues.")
    else:
        lines.append("- Ready: use this feedback plan as the source of truth for the next execution step.")
    lines.extend(["", "### Acceptance Criteria", ""])
    lines.extend(_bullet_lines(plan.updated_execution_plan.acceptance_criteria))
    pending_questions = [question for question in plan.clarification_questions if question.status == "pending"]
    answered_questions = [question for question in plan.clarification_questions if question.status == "answered"]
    lines.extend(["", "### Clarifications", ""])
    if answered_questions:
        lines.append("Answered:")
        for question in answered_questions:
            lines.append(f"- {question.question}")
            lines.append(f"  Answer: {question.answer_summary or 'answered'}")
    if pending_questions:
        lines.append("Pending:")
        for question in pending_questions:
            lines.append(f"- {question.question}")
            if question.options:
                lines.append(f"  Options: {', '.join(question.options)}")
    if not answered_questions and not pending_questions:
        lines.append("- No clarification questions recorded.")
    lines.extend(["", "### Evidence Pointers", ""])
    lines.extend(_bullet_lines([f"`{pointer}`" for pointer in plan.evidence_pointers], empty="- No evidence pointers recorded."))
    lines.extend(["", PLAN_UPDATE_END, ""])
    return "\n".join(lines)


def replace_marked_section(text: str, section: str) -> str:
    normalized_section = section.rstrip() + "\n"
    start = text.find(PLAN_UPDATE_START)
    end = text.find(PLAN_UPDATE_END)
    if start >= 0 and end >= start:
        end += len(PLAN_UPDATE_END)
        prefix = text[:start].rstrip()
        suffix = text[end:].lstrip()
        parts = [prefix, normalized_section.rstrip(), suffix.rstrip()]
        return "\n\n".join(part for part in parts if part) + "\n"
    if text.strip():
        return text.rstrip() + "\n\n" + normalized_section
    return normalized_section


def write_update_report(report: dict[str, object], out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _bullet_lines(values: list[str], *, empty: str = "- None.") -> list[str]:
    items = [value.strip() for value in values if isinstance(value, str) and value.strip()]
    return [f"- {value}" for value in items] if items else [empty]


def _numbered_lines(values: list[str]) -> list[str]:
    items = [value.strip() for value in values if isinstance(value, str) and value.strip()]
    return [f"{index}. {value}" for index, value in enumerate(items, start=1)] if items else ["1. No next steps recorded."]
