from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from devdefender_lab.briefing_feedback import (  # noqa: E402
    answer_feedback_clarification,
    load_feedback_plan,
    write_feedback_plan,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Answer one pending briefing feedback clarification question.")
    parser.add_argument(
        "--feedback-plan",
        type=Path,
        default=Path("artifacts/briefing_feedback_plan.json"),
        help="BriefingFeedbackPlan JSON path.",
    )
    parser.add_argument("--question", type=int, required=True, help="1-based clarification question index.")
    parser.add_argument("--answer", required=True, help="Clarification answer text.")
    parser.add_argument("--out", type=Path, help="Optional output path. Defaults to overwriting --feedback-plan.")
    args = parser.parse_args()

    try:
        result = answer_clarification(
            feedback_plan_path=args.feedback_plan,
            question_index=args.question,
            answer=args.answer,
            out=args.out,
        )
    except Exception as exc:
        result = {"ok": False, "error": _safe_error(exc)}
        print(json.dumps(result, indent=2, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ok"] else 1


def answer_clarification(
    *,
    feedback_plan_path: Path,
    question_index: int,
    answer: str,
    out: Path | None = None,
) -> dict[str, object]:
    plan = load_feedback_plan(feedback_plan_path)
    if plan is None:
        raise ValueError(f"Invalid or unsafe feedback plan: {feedback_plan_path}")
    updated = answer_feedback_clarification(plan, question_index=question_index, answer=answer)
    output_path = write_feedback_plan(updated, out or feedback_plan_path)
    pending = [question for question in updated.clarification_questions if question.status == "pending"]
    answered = [question for question in updated.clarification_questions if question.status == "answered"]
    return {
        "ok": True,
        "out": _display_path(output_path),
        "question_index": question_index,
        "needs_follow_up": updated.needs_follow_up,
        "pending_question_count": len(pending),
        "answered_question_count": len(answered),
        "ready_for_execution": not updated.needs_follow_up,
        "checks": {
            "feedback_plan_written": output_path.exists(),
            "question_answered": updated.clarification_questions[question_index - 1].status == "answered",
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
