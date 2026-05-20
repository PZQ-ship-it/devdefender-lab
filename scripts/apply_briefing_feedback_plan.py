from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from devdefender_lab.briefing_plan_update import apply_feedback_plan_to_markdown  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply briefing feedback plan decisions to plan.md.")
    parser.add_argument(
        "--feedback-plan",
        type=Path,
        default=Path("artifacts/briefing_feedback_plan.json"),
        help="BriefingFeedbackPlan JSON path.",
    )
    parser.add_argument("--plan", type=Path, default=Path("plan.md"), help="Markdown plan path to update.")
    parser.add_argument("--out", type=Path, default=Path("artifacts/briefing_plan_update.json"), help="Report path.")
    parser.add_argument("--dry-run", action="store_true", help="Build the section and report without writing plan.md.")
    args = parser.parse_args()

    try:
        report = apply_feedback_plan_to_markdown(
            feedback_plan_path=args.feedback_plan,
            plan_path=args.plan,
            out=args.out,
            dry_run=args.dry_run,
        )
    except Exception as exc:
        report = {"ok": False, "error": _safe_error(exc), "report_path": str(args.out)}
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if not report.get("ok"):
        print(json.dumps(report, indent=2, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


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
