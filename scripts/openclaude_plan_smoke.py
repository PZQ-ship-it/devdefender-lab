from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from devdefender_lab.agent_gateway import AgentGateway, OpenClaudeCliAdapter
from devdefender_lab.models import DefenseIssue
from devdefender_lab.refiner import build_agent_task


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a plan-only OpenClaude CLI adapter smoke.")
    parser.add_argument("--repo", default="sample_repo", help="Repository path to describe to OpenClaude.")
    parser.add_argument("--artifact-dir", default="artifacts/openclaude", help="Directory for plan artifacts.")
    parser.add_argument("--timeout", type=float, default=120, help="OpenClaude subprocess timeout in seconds.")
    args = parser.parse_args()

    os.chdir(ROOT)
    repo = (ROOT / args.repo).resolve()
    artifact_dir = (ROOT / args.artifact_dir).resolve()
    issue = DefenseIssue(
        title="Plan evidence tests for payment validation",
        body="Produce a plan-only response for tests proving invalid payments cannot be captured.",
        labels=["devdefender", "phase-1", "openclaude"],
        evidence=["openclaude cli plan smoke"],
    )
    task = build_agent_task(repo, issue, artifact_dir)
    task.agent_backend = "openclaude-cli"

    report = AgentGateway(OpenClaudeCliAdapter(timeout_seconds=args.timeout)).plan(task, repo, artifact_dir)
    print(
        json.dumps(
            {
                "status": report.status,
                "backend": report.backend,
                "summary": report.summary,
                "return_code": report.return_code,
                "plan_path": str(report.plan_path) if report.plan_path else None,
                "trace_path": str(report.trace_path) if report.trace_path else None,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    raise SystemExit(0 if report.status == "planned" else 1)


if __name__ == "__main__":
    main()
