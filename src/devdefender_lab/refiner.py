from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from devdefender_lab.models import DefenseIssue, RefinementReport


def run_tdad_refinement(repo_path: Path, issue: DefenseIssue, artifact_dir: Path) -> RefinementReport:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    test_path = _write_payment_validation_test(repo_path)
    command = [sys.executable, "-m", "pytest", str(test_path.relative_to(repo_path))]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_path.resolve()) + os.pathsep + env.get("PYTHONPATH", "")
    completed = subprocess.run(
        command,
        cwd=repo_path,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    output = completed.stdout.strip()
    status = "verified" if completed.returncode == 0 else "needs_fix"
    summary = (
        "TDAD evidence test passed; no production code change was needed."
        if completed.returncode == 0
        else "TDAD evidence test failed; keep the issue open for a guarded code change."
    )
    report = RefinementReport(
        status=status,
        summary=summary,
        issue_title=issue.title,
        test_path=test_path,
        command=command,
        return_code=completed.returncode,
        output=output,
        changed_files=[test_path.as_posix()],
        evidence=[*issue.evidence, output[-800:]],
    )
    (artifact_dir / "refinement.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return report


def _write_payment_validation_test(repo_path: Path) -> Path:
    test_dir = repo_path / "tests"
    test_dir.mkdir(parents=True, exist_ok=True)
    test_path = test_dir / "test_payment_validation.py"
    test_path.write_text(
        """import pytest

from payment_api import Payment, capture_payment


def test_capture_rejects_non_positive_amounts_before_capturing() -> None:
    with pytest.raises(ValueError, match="amount must be positive"):
        capture_payment(Payment(account_id="acct_123", amount_cents=0))


def test_capture_rejects_missing_account_before_capturing() -> None:
    with pytest.raises(ValueError, match="account_id is required"):
        capture_payment(Payment(account_id="", amount_cents=100))


def test_capture_keeps_valid_amount_in_success_response() -> None:
    response = capture_payment(Payment(account_id="acct_123", amount_cents=100))

    assert response["status"] == "captured"
    assert response["amount_cents"] == 100
    assert response["authorization"]
""",
        encoding="utf-8",
    )
    return test_path
