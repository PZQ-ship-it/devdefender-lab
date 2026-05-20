from __future__ import annotations

import subprocess
from pathlib import Path

from devdefender_lab.agent_gateway import AgentAdapter, AgentGateway, MockAgentAdapter, OpenClaudeCliAdapter
from devdefender_lab.config import Settings
from devdefender_lab.evidence import build_evidence_selection, dedupe_strings, write_evidence_selection
from devdefender_lab.models import AgentTaskEnvelope, DefenseIssue, RefinementReport


def run_tdad_refinement(
    repo_path: Path,
    issue: DefenseIssue,
    artifact_dir: Path,
    adapter: AgentAdapter | None = None,
    settings: Settings | None = None,
) -> RefinementReport:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    task = build_agent_task(repo_path, issue, artifact_dir)
    adapter = adapter or _adapter_from_settings(settings)
    task.agent_backend = adapter.backend
    task_path = artifact_dir / "agent_task.json"
    task_path.write_text(task.model_dump_json(indent=2), encoding="utf-8")

    gateway = AgentGateway(adapter)
    agent_report = gateway.run(task, repo_path, artifact_dir)

    summary = _refinement_summary(agent_report.status)
    report = RefinementReport(
        status=agent_report.status,
        summary=summary,
        issue_title=issue.title,
        test_path=repo_path / "tests" / "test_payment_validation.py",
        command=agent_report.command,
        return_code=agent_report.return_code,
        output=agent_report.output,
        changed_files=agent_report.changed_files,
        evidence=[*issue.evidence, *task.evidence_pointers, agent_report.output[-800:]],
        agent_backend=agent_report.backend,
        agent_task_path=task_path,
        agent_patch_path=agent_report.patch_path,
        agent_test_report_path=agent_report.test_report_path,
        agent_trace_path=agent_report.trace_path,
        violations=agent_report.violations,
    )
    (artifact_dir / "refinement.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return report


def build_agent_task(repo_path: Path, issue: DefenseIssue, artifact_dir: Path) -> AgentTaskEnvelope:
    evidence_selection = build_evidence_selection(artifact_dir)
    write_evidence_selection(artifact_dir, evidence_selection)
    evidence_pointers = dedupe_strings([f"repo://{repo_path.as_posix()}", *evidence_selection["selected_pointers"]])
    return AgentTaskEnvelope(
        issue=issue,
        repo_commit_hash=_repo_commit_hash(),
        graph_path=artifact_dir / "graph.json",
        allowed_paths=["payment_api.py", "tests/**"],
        required_tests=["python -m pytest tests/test_payment_validation.py"],
        evidence_pointers=evidence_pointers,
        agent_backend="mock",
    )


def _repo_commit_hash() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=Path.cwd(),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if completed.returncode == 0:
        return completed.stdout.strip()
    return "unknown"


def _refinement_summary(status: str) -> str:
    if status == "verified":
        return "Agent Gateway accepted the patch and required tests passed."
    if status == "rejected":
        return "Agent Gateway rejected the patch before merge."
    if status == "needs_fix":
        return "Agent patch ran but required tests failed."
    return "Agent Gateway produced an unknown status."


def _adapter_from_settings(settings: Settings | None) -> AgentAdapter:
    backend = settings.agent_backend if settings else "mock"
    if backend == "openclaude-cli":
        timeout_seconds = settings.agent_timeout_seconds if settings else 120
        return OpenClaudeCliAdapter(settings=settings, timeout_seconds=timeout_seconds)
    return MockAgentAdapter()
