from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from devdefender_lab.briefing_feedback import (  # noqa: E402
    DEFAULT_FEEDBACK_PLAN_OUT,
    build_feedback_plan_from_input,
    load_briefing_report,
    select_feedback_input,
    write_feedback_plan,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Turn stakeholder briefing feedback into an updated execution plan.")
    parser.add_argument(
        "--feedback",
        help="Stakeholder feedback text. Defaults to a product smoke feedback sample when --use-default-feedback is set.",
    )
    parser.add_argument("--feedback-file", type=Path, help="Path to a bounded stakeholder feedback text file.")
    parser.add_argument("--stt-text", help="Stakeholder feedback text produced by a speech-to-text step.")
    parser.add_argument(
        "--clarification",
        action="append",
        default=[],
        help="Clarification answer. Repeat to answer multiple generated questions.",
    )
    parser.add_argument(
        "--briefing-report",
        type=Path,
        default=Path("artifacts/briefing_deck/briefing_report.json"),
        help="Optional ProjectBriefingReport JSON used for project name and evidence pointers.",
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_FEEDBACK_PLAN_OUT, help="Output feedback plan JSON path.")
    parser.add_argument(
        "--use-default-feedback",
        action="store_true",
        help="Use the deterministic product smoke feedback sample when no feedback is supplied.",
    )
    args = parser.parse_args()

    try:
        result = generate_feedback_plan(
            feedback=args.feedback,
            feedback_file=args.feedback_file,
            stt_text=args.stt_text,
            clarification_answers=args.clarification,
            briefing_report=args.briefing_report,
            out=args.out,
            use_default_feedback=args.use_default_feedback,
        )
    except Exception as exc:
        result = {"ok": False, "error": _safe_error(exc)}
        print(json.dumps(result, indent=2, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ok"] else 1


def generate_feedback_plan(
    *,
    feedback: str | None = None,
    feedback_file: Path | None = None,
    stt_text: str | None = None,
    clarification_answers: list[str] | None = None,
    briefing_report: Path | None = None,
    out: Path = DEFAULT_FEEDBACK_PLAN_OUT,
    use_default_feedback: bool = False,
) -> dict[str, object]:
    feedback_input = select_feedback_input(
        feedback=feedback,
        feedback_file=feedback_file,
        stt_text=stt_text,
        use_default_feedback=use_default_feedback,
    )
    report = load_briefing_report(briefing_report)
    plan = build_feedback_plan_from_input(
        feedback_input,
        clarification_answers=clarification_answers or [],
        briefing_report=report,
    )
    output_path = write_feedback_plan(plan, out)
    return {
        "ok": True,
        "out": _display_path(output_path),
        "feedback_source": feedback_input.source,
        "project_name": plan.project_name,
        "feedback_summary": plan.feedback_summary,
        "needs_follow_up": plan.needs_follow_up,
        "concern_count": len(plan.interpreted_concerns),
        "clarification_question_count": len(plan.clarification_questions),
        "plan_change_count": len(plan.plan_changes),
        "updated_next_step_count": len(plan.updated_execution_plan.next_steps),
        "evidence_pointer_count": len(plan.evidence_pointers),
        "checks": {
            "feedback_plan_written": output_path.exists(),
            "has_interpreted_concerns": bool(plan.interpreted_concerns),
            "has_clarification_questions": bool(plan.clarification_questions),
            "has_updated_execution_plan": bool(plan.updated_execution_plan.next_steps),
            "has_plan_changes": bool(plan.plan_changes),
        },
    }


def _display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


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
