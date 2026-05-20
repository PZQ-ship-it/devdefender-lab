from __future__ import annotations

import difflib
import fnmatch
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Protocol

from devdefender_lab.config import Settings, load_settings
from devdefender_lab.evidence import is_safe_evidence_pointer
from devdefender_lab.models import AgentRunReport, AgentTaskEnvelope


PAYMENT_VALIDATION_TEST = """import pytest

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
"""


FAILING_PAYMENT_TEST = """from payment_api import Payment, capture_payment


def test_mock_agent_failure_is_reported() -> None:
    response = capture_payment(Payment(account_id="acct_123", amount_cents=100))

    assert response["status"] == "not-captured"
"""


FORBIDDEN_PATTERNS = [
    ".env",
    ".env.*",
    "**/.env",
    "**/.env.*",
    "package-lock.json",
    "scripts/publish_github.ps1",
    ".github/**",
]


FORBIDDEN_INTENT_TERMS = [
    ".env",
    "api key",
    "apikey",
    "secret",
    "token",
    "git reset",
    "delete the repo",
    "delete repository",
    "remove the repo",
    "rm -rf",
    "ignore tests",
    "skip tests",
    "bypass tests",
    "publish",
]


SECRET_MARKERS = [
    "OPENAI_API_KEY=",
    "ANTHROPIC_API_KEY=",
    "GH_TOKEN=",
    "github_pat_",
    "sk-",
]


OPENCLAUDE_PLAN_KEYS = (
    "risk_summary",
    "proposed_tests",
    "proposed_patch",
    "verification_commands",
    "gateway_notes",
)


OPENCLAUDE_PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "risk_summary": {"type": "string"},
        "proposed_tests": {"type": "array", "items": {"type": "string"}},
        "proposed_patch": {"type": "array", "items": {"type": "string"}},
        "verification_commands": {"type": "array", "items": {"type": "string"}},
        "gateway_notes": {"type": "array", "items": {"type": "string"}},
    },
    "required": list(OPENCLAUDE_PLAN_KEYS),
    "additionalProperties": False,
}


OPENCLAUDE_PATCH_KEYS = (
    "summary",
    "changed_files",
    "tests_written",
    "verification_commands",
    "risk_notes",
)


OPENCLAUDE_PATCH_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "changed_files": {"type": "array", "items": {"type": "string"}},
        "tests_written": {"type": "array", "items": {"type": "string"}},
        "verification_commands": {"type": "array", "items": {"type": "string"}},
        "risk_notes": {"type": "array", "items": {"type": "string"}},
    },
    "required": list(OPENCLAUDE_PATCH_KEYS),
    "additionalProperties": False,
}


class AgentAdapter(Protocol):
    backend: str

    def run(self, task: AgentTaskEnvelope, repo_path: Path, artifact_dir: Path) -> AgentRunReport:
        ...


class AgentGateway:
    def __init__(self, adapter: AgentAdapter) -> None:
        self.adapter = adapter

    def plan(self, task: AgentTaskEnvelope, repo_path: Path, artifact_dir: Path) -> AgentRunReport:
        planner = getattr(self.adapter, "plan", None)
        if planner is None:
            raise TypeError(f"{self.adapter.backend} adapter does not support plan-only execution.")
        artifact_dir.mkdir(parents=True, exist_ok=True)
        report = planner(task, repo_path, artifact_dir)
        _write_trace(report, task, artifact_dir)
        return report

    def run(self, task: AgentTaskEnvelope, repo_path: Path, artifact_dir: Path) -> AgentRunReport:
        artifact_dir.mkdir(parents=True, exist_ok=True)
        preflight_violations = validate_agent_task(task)
        if preflight_violations:
            report = AgentRunReport(
                backend=self.adapter.backend,
                status="rejected",
                summary="Agent task rejected before execution.",
                violations=preflight_violations,
                trace_path=artifact_dir / "agent_trace.json",
                workspace=repo_path,
            )
            _write_trace(report, task, artifact_dir)
            return report
        report = self.adapter.run(task, repo_path, artifact_dir)
        violations = [*report.violations, *validate_agent_report(task, report)]
        if violations:
            report.status = "rejected"
            report.summary = "Agent output rejected by gateway policy."
            report.violations = sorted(set(violations))
        elif report.return_code == 0:
            report.status = "verified"
            if _has_verified_no_op_evidence(report):
                report.summary = "Agent produced verified no-op evidence; required tests already pass."
            else:
                report.summary = "Agent patch passed required tests."
        else:
            report.status = "needs_fix"
            report.summary = "Agent patch did not pass required tests."
        _write_trace(report, task, artifact_dir)
        artifact_violations = _scan_report_artifacts(report)
        if artifact_violations:
            report.status = "rejected"
            report.summary = "Agent output rejected by gateway policy."
            report.violations = sorted(set([*report.violations, *artifact_violations]))
            _write_trace(report, task, artifact_dir)
        return report


def replay_agent_trace(trace_path: Path) -> AgentRunReport:
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    task = AgentTaskEnvelope.model_validate(trace["task"])
    report = AgentRunReport(
        backend=trace["backend"],
        status=trace["status"],
        summary=trace["summary"],
        changed_files=trace.get("changed_files", []),
        command=trace.get("command", []),
        return_code=trace.get("return_code"),
        violations=trace.get("violations", []),
        plan_path=Path(trace["plan_path"]) if trace.get("plan_path") else None,
        patch_path=Path(trace["patch_path"]) if trace.get("patch_path") else None,
        test_report_path=Path(trace["test_report_path"]) if trace.get("test_report_path") else None,
        trace_path=trace_path,
        workspace=Path(trace["workspace"]) if trace.get("workspace") else None,
        metadata=trace.get("metadata", {}),
    )
    violations = [*validate_agent_task(task), *report.violations, *validate_agent_report(task, report)]
    if violations:
        report.status = "rejected"
        report.summary = "Agent output rejected by gateway policy."
        report.violations = sorted(set(violations))
    elif report.return_code == 0:
        report.status = "verified"
        report.summary = "Agent patch passed required tests."
    else:
        report.status = "needs_fix"
        report.summary = "Agent patch did not pass required tests."
    return report


def validate_agent_task(task: AgentTaskEnvelope) -> list[str]:
    violations: list[str] = []
    text = " ".join(
        [
            task.issue.title,
            task.issue.body,
            " ".join(task.issue.labels),
            " ".join(_non_pointer_evidence(task.issue.evidence)),
            " ".join(task.allowed_paths),
            " ".join(task.required_tests),
        ]
    ).lower()
    for term in FORBIDDEN_INTENT_TERMS:
        if term in text:
            violations.append(f"Task contains forbidden intent: {term}")
    for allowed_path in task.allowed_paths:
        normalized = _normalize_changed_path(allowed_path.rstrip("*"))
        if normalized is None and ".." in allowed_path.replace("\\", "/"):
            violations.append(f"Allowed path is invalid: {allowed_path}")
        if ".env" in allowed_path.replace("\\", "/").lower():
            violations.append(f"Allowed path is forbidden: {allowed_path}")
    for pointer in task.evidence_pointers:
        if not is_safe_evidence_pointer(pointer) and not pointer.startswith("repo://"):
            violations.append(f"Evidence pointer is invalid: {pointer}")
    return sorted(set(violations))


def _non_pointer_evidence(evidence: list[str]) -> list[str]:
    return [item for item in evidence if not is_safe_evidence_pointer(item)]


OpenClaudeRunner = Callable[
    [list[str], Path, dict[str, str], float],
    subprocess.CompletedProcess[str],
]


class OpenClaudeCliAdapter:
    backend = "openclaude-cli"

    def __init__(
        self,
        command: list[str] | None = None,
        timeout_seconds: float = 120,
        runner: OpenClaudeRunner | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.command = command or _default_openclaude_command()
        self.timeout_seconds = timeout_seconds
        self.runner = runner or _run_openclaude_command
        self.settings = settings

    def plan(self, task: AgentTaskEnvelope, repo_path: Path, artifact_dir: Path) -> AgentRunReport:
        settings = self.settings or load_settings()
        plan_path = artifact_dir / "agent_plan.json"
        trace_path = artifact_dir / "agent_trace.json"

        if not settings.openai_api_key:
            report = AgentRunReport(
                backend=self.backend,
                status="failed",
                summary="OPENAI_API_KEY is required for OpenClaude CLI plan mode.",
                plan_path=plan_path,
                trace_path=trace_path,
                workspace=repo_path,
            )
            _write_openclaude_plan(plan_path, task, report, "")
            return report

        env = _openclaude_env(settings)
        prompt = _openclaude_plan_prompt(task)
        command = self._build_command(settings, prompt, repo_path)
        report_command = _command_for_report(command)
        output = ""
        return_code: int | None = None

        try:
            completed = self.runner(command, repo_path, env, self.timeout_seconds)
            return_code = completed.returncode
            output = _redact_text((completed.stdout or "").strip(), settings)
            parsed_output = _try_parse_json(output)
            plan_payload = _extract_plan_payload(parsed_output)
            if completed.returncode == 0 and plan_payload is not None:
                status = "planned"
                summary = "OpenClaude produced a structured plan-only response."
            elif completed.returncode == 0:
                status = "failed"
                summary = "OpenClaude returned output but not the required plan JSON."
            else:
                status = "failed"
                summary = "OpenClaude plan command failed."
        except FileNotFoundError as exc:
            status = "failed"
            summary = "OpenClaude CLI command was not found."
            output = _redact_text(str(exc), settings)
        except subprocess.TimeoutExpired as exc:
            status = "failed"
            summary = "OpenClaude plan command timed out."
            timeout_output = exc.stdout or exc.stderr or str(exc)
            output = _redact_text(str(timeout_output), settings)

        report = AgentRunReport(
            backend=self.backend,
            status=status,
            summary=summary,
            command=report_command,
            return_code=return_code,
            output=output,
            plan_path=plan_path,
            trace_path=trace_path,
            workspace=repo_path,
        )
        _write_openclaude_plan(plan_path, task, report, output)
        return report

    def run(self, task: AgentTaskEnvelope, repo_path: Path, artifact_dir: Path) -> AgentRunReport:
        settings = self.settings or load_settings()
        patch_path = artifact_dir / "patch.diff"
        test_report_path = artifact_dir / "test_report.json"
        trace_path = artifact_dir / "agent_trace.json"

        if not settings.openai_api_key:
            report = AgentRunReport(
                backend=self.backend,
                status="pending",
                summary="OPENAI_API_KEY is required for OpenClaude CLI patch mode.",
                patch_path=patch_path,
                test_report_path=test_report_path,
                trace_path=trace_path,
                workspace=repo_path,
                violations=["OPENAI_API_KEY is required for OpenClaude CLI patch mode."],
            )
            _write_test_report(test_report_path, [], None, "")
            patch_path.write_text("", encoding="utf-8")
            return report

        preexisting_required_tests = _existing_required_test_paths(task.required_tests, repo_path)
        workspace = _prepare_agent_workspace(repo_path, artifact_dir, self.backend)
        env = _openclaude_env(settings)
        prompt = _openclaude_patch_prompt(task)
        command = self._build_patch_command(settings, prompt, workspace)
        report_command = _command_for_report(command)
        output = ""
        return_code: int | None = None
        changed_files: list[str] = []
        violations: list[str] = []
        timed_out = False

        try:
            completed = self.runner(command, workspace, env, self.timeout_seconds)
            return_code = completed.returncode
            output = _redact_text((completed.stdout or "").strip(), settings)
        except FileNotFoundError as exc:
            output = _redact_text(str(exc), settings)
            violations.append("OpenClaude CLI command was not found.")
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            timeout_output = exc.stdout or exc.stderr or str(exc)
            output = _redact_text(str(timeout_output), settings)

        patch_text = _diff_directories(repo_path, workspace)
        patch_path.write_text(patch_text, encoding="utf-8")
        changed_files = _changed_files(repo_path, workspace)

        test_command: list[str] = []
        test_return_code: int | None = None
        test_output = ""
        if task.required_tests:
            test_command = _test_command(task.required_tests[0])
            completed = _run_test(test_command, workspace)
            test_return_code = completed.returncode
            test_output = completed.stdout.strip()
        else:
            violations.append("Agent task did not include required tests.")

        _write_test_report(test_report_path, test_command, test_return_code, test_output)
        patch_payload = _extract_patch_payload(_try_parse_json(output))
        no_op_evidence = _no_op_evidence(changed_files, test_return_code, preexisting_required_tests, patch_text)
        if patch_payload is None and not (no_op_evidence is not None and not timed_out):
            violations.append("OpenClaude did not return the required patch JSON.")
        summary = (
            patch_payload.get("summary", "OpenClaude produced a patch.")
            if patch_payload
            else "OpenClaude patch command completed."
        )
        if timed_out and not (patch_payload is not None and no_op_evidence is not None):
            violations.append("OpenClaude patch command timed out.")

        return AgentRunReport(
            backend=self.backend,
            status="pending",
            summary=summary,
            changed_files=changed_files,
            command=report_command,
            return_code=test_return_code if test_return_code is not None else return_code,
            output=test_output or output,
            violations=violations,
            patch_path=patch_path,
            test_report_path=test_report_path,
            trace_path=trace_path,
            workspace=workspace,
            metadata={
                "agent_return_code": return_code,
                "agent_timed_out": timed_out,
                "agent_output": output,
                "agent_patch_payload": patch_payload,
                "no_op_evidence": no_op_evidence,
            },
        )

    def _build_command(self, settings: Settings, prompt: str, repo_path: Path) -> list[str]:
        return [
            *self.command,
            "--print",
            "--bare",
            "--no-session-persistence",
            "--add-dir",
            str(repo_path.resolve()),
            "--provider",
            "openai",
            "--model",
            settings.openai_model,
            "--permission-mode",
            "bypassPermissions",
            "--tools",
            "Read,Glob,Grep,LS",
            "--disallowedTools",
            "Bash",
            "Write",
            "Edit",
            "MultiEdit",
            "NotebookEdit",
            "--json-schema",
            json.dumps(OPENCLAUDE_PLAN_SCHEMA, separators=(",", ":")),
            "--output-format",
            "json",
            prompt,
        ]

    def _build_patch_command(self, settings: Settings, prompt: str, workspace: Path) -> list[str]:
        return [
            *self.command,
            "--print",
            "--bare",
            "--no-session-persistence",
            "--add-dir",
            str(workspace.resolve()),
            "--provider",
            "openai",
            "--model",
            settings.openai_model,
            "--permission-mode",
            "bypassPermissions",
            "--tools",
            "Read",
            "Glob",
            "Grep",
            "LS",
            "Write",
            "Edit",
            "MultiEdit",
            "--disallowedTools",
            "Bash",
            "NotebookEdit",
            "--json-schema",
            json.dumps(OPENCLAUDE_PATCH_SCHEMA, separators=(",", ":")),
            "--output-format",
            "json",
            prompt,
        ]


class MockAgentAdapter:
    backend = "mock"

    def __init__(self, scenario: str = "valid") -> None:
        self.scenario = scenario

    def run(self, task: AgentTaskEnvelope, repo_path: Path, artifact_dir: Path) -> AgentRunReport:
        patch_path = artifact_dir / "patch.diff"
        test_report_path = artifact_dir / "test_report.json"
        trace_path = artifact_dir / "agent_trace.json"
        changed_files: list[str] = []
        command: list[str] = []
        return_code: int | None = None
        output = ""
        violations: list[str] = []

        if self.scenario == "unauthorized_path":
            changed_files = [".env"]
            patch_path.write_text(_synthetic_patch(".env", "", "OPENAI_API_KEY=leaked\n"), encoding="utf-8")
            violations.append("Mock scenario attempted to modify .env.")
        else:
            if self.scenario != "missing_tests":
                test_content = FAILING_PAYMENT_TEST if self.scenario == "failing_tests" else PAYMENT_VALIDATION_TEST
                test_path = repo_path / "tests" / "test_payment_validation.py"
                patch_text = _write_text_with_patch(test_path, test_content, repo_path)
                patch_path.write_text(patch_text, encoding="utf-8")
                changed_files.append(test_path.relative_to(repo_path).as_posix())
            else:
                patch_path.write_text(_synthetic_patch("payment_api.py", "", "# missing tests scenario\n"), encoding="utf-8")
                changed_files.append("payment_api.py")

            if task.required_tests:
                command = _test_command(task.required_tests[0])
                completed = _run_test(command, repo_path)
                return_code = completed.returncode
                output = completed.stdout.strip()
            else:
                violations.append("Agent task did not include required tests.")

        _write_test_report(test_report_path, command, return_code, output)

        report = AgentRunReport(
            backend=self.backend,
            status="pending",
            summary="Mock agent completed.",
            changed_files=changed_files,
            command=command,
            return_code=return_code,
            output=output,
            violations=violations,
            patch_path=patch_path,
            test_report_path=test_report_path,
            trace_path=trace_path,
            workspace=repo_path,
        )
        _write_trace(report, task, artifact_dir)
        return report


def _run_openclaude_command(
    command: list[str],
    repo_path: Path,
    env: dict[str, str],
    timeout_seconds: float,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=repo_path,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=timeout_seconds,
    )


def _prepare_agent_workspace(repo_path: Path, artifact_dir: Path, backend: str) -> Path:
    workspace_root = artifact_dir / "workspaces"
    workspace_root.mkdir(parents=True, exist_ok=True)
    workspace = workspace_root / f"{backend}-{int(time.time() * 1000)}"
    shutil.copytree(
        repo_path,
        workspace,
        ignore=shutil.ignore_patterns(
            ".git",
            "__pycache__",
            ".pytest_cache",
            ".mypy_cache",
            ".ruff_cache",
        ),
    )
    return workspace


def _default_openclaude_command() -> list[str]:
    npx = shutil.which("npx") or shutil.which("npx.cmd") or "npx"
    return [npx, "-y", "@gitlawb/openclaude"]


def _openclaude_env(settings: Settings) -> dict[str, str]:
    env = os.environ.copy()
    env["CLAUDE_CODE_USE_OPENAI"] = "1"
    env["OPENAI_API_KEY"] = settings.openai_api_key or ""
    env["OPENAI_MODEL"] = settings.openai_model
    if settings.openai_base_url:
        env["OPENAI_BASE_URL"] = settings.openai_base_url
    return env


def _openclaude_plan_prompt(task: AgentTaskEnvelope) -> str:
    task_json = task.model_dump_json(indent=2)
    return f"""You are an external code agent connected to DevDefender Lab.

Mode: plan-only. You may inspect files with read-only tools. Do not modify files, run shell commands, or request write/shell access.
Review the Agent Task Envelope and return only a compact JSON object with these keys:
- risk_summary: string
- proposed_tests: list of strings
- proposed_patch: list of strings
- verification_commands: list of strings
- gateway_notes: list of strings

Agent Task Envelope:
{task_json}
"""


def _openclaude_patch_prompt(task: AgentTaskEnvelope) -> str:
    task_json = task.model_dump_json(indent=2)
    return f"""You are an external code agent connected to DevDefender Lab.

Mode: patch execution inside an isolated workspace only.

This is an execution task, not a review task. Edit the current workspace now.

Required file operation:
Create `tests/test_payment_validation.py` in the current workspace before returning.

Required file content:
```python
{PAYMENT_VALIDATION_TEST.rstrip()}
```

Task to execute now:
Create `tests/test_payment_validation.py` in the current workspace with pytest tests proving:
1. `capture_payment(Payment(account_id="acct_123", amount_cents=0))` raises `ValueError` matching `amount must be positive`.
2. `capture_payment(Payment(account_id="", amount_cents=100))` raises `ValueError` matching `account_id is required`.
3. A valid payment still returns status `captured`, preserves `amount_cents`, and includes an authorization.

Rules:
- Modify files only inside the current workspace.
- Do not run shell commands.
- Do not read or write secrets, .env files, CI files, publish scripts, lock files, or files outside allowed_paths.
- Follow TDAD: add tests first. Only change production code if the tests require it.
- Keep changes minimal and limited to allowed_paths.
- Do not answer that you are waiting for instructions. The instructions are complete.
- If you cannot write the file, return the JSON with empty `changed_files`, empty `tests_written`, and explain the failure in `risk_notes`.
- Return only the requested compact JSON object.

Allowed paths:
{json.dumps(task.allowed_paths, ensure_ascii=False)}

Required test commands that the Gateway will run after you finish:
{json.dumps(task.required_tests, ensure_ascii=False)}

Agent Task Envelope:
{task_json}
"""


def _write_openclaude_plan(
    plan_path: Path,
    task: AgentTaskEnvelope,
    report: AgentRunReport,
    response_text: str,
) -> None:
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    parsed_response = _try_parse_json(response_text)
    payload: dict[str, Any] = {
        "backend": report.backend,
        "status": report.status,
        "summary": report.summary,
        "command": report.command,
        "return_code": report.return_code,
        "response": response_text,
        "parsed_response": parsed_response,
        "plan_payload": _extract_plan_payload(parsed_response),
        "task": task.model_dump(mode="json"),
    }
    plan_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _write_test_report(
    test_report_path: Path,
    command: list[str],
    return_code: int | None,
    output: str,
) -> None:
    payload = {
        "command": command,
        "return_code": return_code,
        "output": output,
    }
    test_report_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _try_parse_json(text: str) -> Any:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 3:
            stripped = "\n".join(lines[1:-1]).strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            return json.loads(stripped[start : end + 1])
        except json.JSONDecodeError:
            return None


def _extract_plan_payload(parsed: Any) -> dict[str, Any] | None:
    if isinstance(parsed, dict) and _is_plan_payload(parsed):
        return parsed
    if isinstance(parsed, dict):
        structured_output = parsed.get("structured_output")
        if isinstance(structured_output, dict) and _is_plan_payload(structured_output):
            return structured_output
        result = parsed.get("result")
        if isinstance(result, str):
            nested = _try_parse_json(result)
            if isinstance(nested, dict) and _is_plan_payload(nested):
                return nested
    return None


def _extract_patch_payload(parsed: Any) -> dict[str, Any] | None:
    if isinstance(parsed, dict) and _is_patch_payload(parsed):
        return parsed
    if isinstance(parsed, dict):
        structured_output = parsed.get("structured_output")
        if isinstance(structured_output, dict) and _is_patch_payload(structured_output):
            return structured_output
        result = parsed.get("result")
        if isinstance(result, str):
            nested = _try_parse_json(result)
            if isinstance(nested, dict) and _is_patch_payload(nested):
                return nested
    return None


def _is_plan_payload(value: dict[str, Any]) -> bool:
    return all(key in value for key in OPENCLAUDE_PLAN_KEYS)


def _is_patch_payload(value: dict[str, Any]) -> bool:
    return all(key in value for key in OPENCLAUDE_PATCH_KEYS)


def _changed_files(original: Path, modified: Path) -> list[str]:
    paths: set[str] = set()
    for base in (original, modified):
        for path in base.rglob("*"):
            if path.is_file() and not _is_ignored_workspace_file(path.relative_to(base).as_posix()):
                paths.add(path.relative_to(base).as_posix())

    changed: list[str] = []
    for rel in sorted(paths):
        original_path = original / rel
        modified_path = modified / rel
        if not original_path.exists() or not modified_path.exists():
            changed.append(rel)
            continue
        if original_path.read_bytes() != modified_path.read_bytes():
            changed.append(rel)
    return changed


def _diff_directories(original: Path, modified: Path) -> str:
    chunks: list[str] = []
    for rel in _changed_files(original, modified):
        original_path = original / rel
        modified_path = modified / rel
        before = original_path.read_text(encoding="utf-8") if original_path.exists() else ""
        after = modified_path.read_text(encoding="utf-8") if modified_path.exists() else ""
        chunks.append(_synthetic_patch(rel, before, after))
    return "".join(chunks)


def _is_ignored_workspace_file(path: str) -> bool:
    normalized = path.replace("\\", "/")
    return any(
        part in {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
        for part in normalized.split("/")
    )


def _command_for_report(command: list[str]) -> list[str]:
    if not command:
        return []
    return [*command[:-1], "<prompt>"]


def _redact_text(text: str, settings: Settings) -> str:
    redacted = text
    if settings.openai_api_key:
        redacted = redacted.replace(settings.openai_api_key, "<redacted>")
    return redacted


def validate_agent_report(task: AgentTaskEnvelope, report: AgentRunReport) -> list[str]:
    violations: list[str] = []
    if task.acceptance.must_return_patch_only and not report.patch_path:
        violations.append("Agent did not return a patch artifact.")
    if (
        task.acceptance.must_write_test_first
        and not _has_test_change(report.changed_files)
        and not _has_verified_no_op_evidence(report)
    ):
        violations.append("Agent did not write a test before implementation.")
    for changed_file in report.changed_files:
        normalized = _normalize_changed_path(changed_file)
        if not normalized:
            violations.append(f"Invalid changed path: {changed_file}")
            continue
        if _is_forbidden_path(normalized):
            violations.append(f"Changed path is forbidden: {normalized}")
        if not _is_allowed_path(normalized, task.allowed_paths):
            violations.append(f"Changed path is outside allowed paths: {normalized}")
    if task.acceptance.must_pass_existing_tests and report.return_code is None and not violations:
        violations.append("Agent did not run required tests.")
    violations.extend(_scan_report_artifacts(report))
    return violations


def _scan_report_artifacts(report: AgentRunReport) -> list[str]:
    violations: list[str] = []
    for artifact in [report.plan_path, report.patch_path, report.test_report_path, report.trace_path]:
        if not artifact or not artifact.exists() or artifact.is_dir():
            continue
        text = artifact.read_text(encoding="utf-8", errors="ignore")
        for marker in SECRET_MARKERS:
            if marker in text:
                violations.append(f"Artifact may leak secret marker {marker}: {artifact.name}")
    return violations


def _has_test_change(changed_files: list[str]) -> bool:
    return any(path.replace("\\", "/").startswith("tests/") or "/tests/" in path.replace("\\", "/") for path in changed_files)


def _has_verified_no_op_evidence(report: AgentRunReport) -> bool:
    evidence = report.metadata.get("no_op_evidence")
    return bool(
        isinstance(evidence, dict)
        and evidence.get("kind") == "preexisting_required_tests"
        and evidence.get("required_tests_passed") is True
        and evidence.get("patch_is_empty") is True
        and isinstance(evidence.get("preexisting_required_test_files"), list)
        and evidence.get("preexisting_required_test_files")
        and report.changed_files == []
        and report.return_code == 0
    )


def _existing_required_test_paths(required_tests: list[str], repo_path: Path) -> list[str]:
    existing: list[str] = []
    for test_path in _required_test_paths(required_tests):
        if (repo_path / test_path).is_file():
            existing.append(test_path)
    return sorted(set(existing))


def _required_test_paths(required_tests: list[str]) -> list[str]:
    paths: list[str] = []
    for command in required_tests:
        for part in command.split():
            normalized = part.strip("'\"").replace("\\", "/")
            if normalized.startswith("tests/") and normalized.endswith(".py"):
                paths.append(normalized)
    return paths


def _no_op_evidence(
    changed_files: list[str],
    test_return_code: int | None,
    preexisting_required_tests: list[str],
    patch_text: str,
) -> dict[str, object] | None:
    if changed_files or test_return_code != 0 or not preexisting_required_tests:
        return None
    return {
        "kind": "preexisting_required_tests",
        "required_tests_passed": True,
        "patch_is_empty": patch_text == "",
        "preexisting_required_test_files": preexisting_required_tests,
    }


def _normalize_changed_path(path: str) -> str | None:
    normalized = path.replace("\\", "/").strip("/")
    if not normalized or normalized.startswith("../") or "/../" in normalized or normalized == "..":
        return None
    if Path(normalized).is_absolute():
        return None
    return normalized


def _is_forbidden_path(path: str) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in FORBIDDEN_PATTERNS)


def _is_allowed_path(path: str, allowed_paths: list[str]) -> bool:
    return any(fnmatch.fnmatch(path, pattern.replace("\\", "/")) for pattern in allowed_paths)


def _test_command(command: str) -> list[str]:
    parts = command.split()
    if parts and parts[0] == "python":
        return [sys.executable, *parts[1:]]
    return parts


def _run_test(command: list[str], repo_path: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_path.resolve()) + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        command,
        cwd=repo_path,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


def _write_text_with_patch(path: Path, content: str, repo_path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    before = path.read_text(encoding="utf-8") if path.exists() else ""
    path.write_text(content, encoding="utf-8")
    rel_path = path.relative_to(repo_path).as_posix()
    return _synthetic_patch(rel_path, before, content)


def _synthetic_patch(path: str, before: str, after: str) -> str:
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        )
    )


def _write_trace(report: AgentRunReport, task: AgentTaskEnvelope, artifact_dir: Path) -> None:
    trace_path = report.trace_path or artifact_dir / "agent_trace.json"
    report.trace_path = trace_path
    trace = {
        "backend": report.backend,
        "status": report.status,
        "summary": report.summary,
        "command": report.command,
        "return_code": report.return_code,
        "changed_files": report.changed_files,
        "violations": report.violations,
        "plan_path": str(report.plan_path) if report.plan_path else None,
        "patch_path": str(report.patch_path) if report.patch_path else None,
        "test_report_path": str(report.test_report_path) if report.test_report_path else None,
        "workspace": str(report.workspace) if report.workspace else None,
        "metadata": report.metadata,
        "task": task.model_dump(mode="json"),
    }
    trace_path.write_text(json.dumps(trace, indent=2, ensure_ascii=False), encoding="utf-8")
