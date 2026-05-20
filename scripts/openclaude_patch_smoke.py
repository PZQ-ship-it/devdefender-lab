from __future__ import annotations

import argparse
import json
import os
import shutil
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
    parser = argparse.ArgumentParser(description="Run a real OpenClaude CLI patch smoke in an isolated repo copy.")
    parser.add_argument("--source-repo", default="sample_repo", help="Repository template to copy before agent execution.")
    parser.add_argument("--artifact-dir", default="artifacts/openclaude-patch", help="Directory for agent artifacts.")
    parser.add_argument("--timeout", type=float, default=240, help="OpenClaude subprocess timeout in seconds.")
    parser.add_argument(
        "--keep-existing-tests",
        action="store_true",
        help="Do not remove sample payment validation tests from the disposable smoke repo.",
    )
    args = parser.parse_args()

    os.chdir(ROOT)
    artifact_dir = (ROOT / args.artifact_dir).resolve()
    smoke_repo = artifact_dir / "input_repo"
    source_repo = (ROOT / args.source_repo).resolve()
    if smoke_repo.exists():
        shutil.rmtree(smoke_repo)
    shutil.copytree(source_repo, smoke_repo, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))

    if not args.keep_existing_tests:
        existing_test = smoke_repo / "tests" / "test_payment_validation.py"
        if existing_test.exists():
            existing_test.unlink()

    issue = DefenseIssue(
        title="Add evidence tests for payment validation",
        body="Write tests proving invalid payment amounts and missing account IDs cannot be captured. Keep production code changes minimal.",
        labels=["devdefender", "phase-1", "openclaude"],
        evidence=["openclaude cli patch smoke"],
    )
    task = build_agent_task(smoke_repo, issue, artifact_dir)
    task.agent_backend = "openclaude-cli"

    report = AgentGateway(OpenClaudeCliAdapter(timeout_seconds=args.timeout)).run(task, smoke_repo, artifact_dir)
    print(
        json.dumps(
            {
                "status": report.status,
                "backend": report.backend,
                "summary": report.summary,
                "return_code": report.return_code,
                "changed_files": report.changed_files,
                "violations": report.violations,
                "workspace": str(report.workspace) if report.workspace else None,
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
