from __future__ import annotations

import json
from pathlib import Path

from devdefender_lab.briefing import contains_forbidden_briefing_artifact_fields


DEFAULT_PLAN_UPDATE_REPORT = Path("artifacts/briefing_plan_update.json")


def evaluate_briefing_execution_gate(report_path: Path | str = DEFAULT_PLAN_UPDATE_REPORT) -> dict[str, object]:
    path = Path(report_path)
    payload = _load_report(path)
    if payload is None:
        return {
            "ok": False,
            "can_continue": False,
            "source_of_truth": False,
            "report_path": str(path),
            "blocking_reason": f"Missing, invalid, or unsafe briefing plan update report: {path}",
            "next_steps": [],
            "pending_questions": [],
            "checks": {
                "report_loaded": False,
                "no_forbidden_artifact_fields": False,
                "source_of_truth_ready": False,
                "has_execution_next_steps": False,
            },
        }

    source_of_truth = bool(payload.get("execution_source_of_truth"))
    next_steps = _string_list(payload.get("execution_next_steps"))
    pending_questions = _string_list(payload.get("pending_questions"))
    blocking_reason = str(payload.get("blocking_reason") or "")
    can_continue = source_of_truth and bool(next_steps) and not pending_questions and not blocking_reason
    if not source_of_truth and not blocking_reason:
        blocking_reason = "Briefing feedback plan is not marked as the execution source of truth."
    if source_of_truth and not next_steps:
        blocking_reason = "Briefing plan update is ready but has no execution next steps."
    if pending_questions and not blocking_reason:
        blocking_reason = f"{len(pending_questions)} clarification question(s) must be answered before execution continues."

    checks = {
        "report_loaded": True,
        "no_forbidden_artifact_fields": not contains_forbidden_briefing_artifact_fields(payload),
        "source_of_truth_ready": source_of_truth,
        "has_execution_next_steps": bool(next_steps),
    }
    return {
        "ok": checks["report_loaded"] and checks["no_forbidden_artifact_fields"],
        "can_continue": can_continue and checks["no_forbidden_artifact_fields"],
        "source_of_truth": source_of_truth,
        "report_path": str(path),
        "blocking_reason": "" if can_continue else blocking_reason,
        "next_steps": next_steps if can_continue else [],
        "pending_questions": pending_questions,
        "checks": checks,
    }


def _load_report(path: Path) -> dict[str, object] | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    if contains_forbidden_briefing_artifact_fields(text):
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or contains_forbidden_briefing_artifact_fields(payload):
        return None
    return payload


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]
