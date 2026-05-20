from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from devdefender_lab.briefing_execution_gate import (  # noqa: E402
    DEFAULT_PLAN_UPDATE_REPORT,
    evaluate_briefing_execution_gate,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate whether a briefing feedback plan can drive execution.")
    parser.add_argument(
        "--plan-update",
        type=Path,
        default=DEFAULT_PLAN_UPDATE_REPORT,
        help="briefing_plan_update.json report path.",
    )
    parser.add_argument("--out", type=Path, help="Optional path to write the gate report.")
    args = parser.parse_args()

    report = evaluate_briefing_execution_gate(args.plan_update)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    stream = sys.stdout if report.get("ok") else sys.stderr
    print(json.dumps(report, indent=2, ensure_ascii=False), file=stream)
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
