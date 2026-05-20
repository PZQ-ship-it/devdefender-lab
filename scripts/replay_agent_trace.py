from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from devdefender_lab.agent_gateway import replay_agent_trace


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay DevDefender Agent Gateway validation from agent_trace.json.")
    parser.add_argument("trace_path", type=Path, help="Path to agent_trace.json.")
    args = parser.parse_args()

    report = replay_agent_trace(args.trace_path)
    print(
        json.dumps(
            {
                "status": report.status,
                "backend": report.backend,
                "summary": report.summary,
                "return_code": report.return_code,
                "changed_files": report.changed_files,
                "violations": report.violations,
                "patch_path": str(report.patch_path) if report.patch_path else None,
                "test_report_path": str(report.test_report_path) if report.test_report_path else None,
                "trace_path": str(report.trace_path) if report.trace_path else None,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    raise SystemExit(0 if report.status == "verified" else 1)


if __name__ == "__main__":
    main()
