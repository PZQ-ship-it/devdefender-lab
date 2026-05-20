from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
DEFAULT_ARTIFACT_DIR = ROOT / "artifacts"
DEFAULT_OUT = DEFAULT_ARTIFACT_DIR / "evidence_chain_smoke.json"


if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from devdefender_lab.evidence import build_evidence_selection  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify replay evidence pointers propagated through Issue and Agent artifacts.")
    parser.add_argument("--artifact-dir", type=Path, default=DEFAULT_ARTIFACT_DIR, help="Artifact directory to inspect.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Path for the JSON smoke report.")
    args = parser.parse_args()

    report = build_report(args.artifact_dir)
    report["out"] = str(args.out)
    write_report(report, args.out)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if not report["ok"]:
        raise SystemExit(1)


def build_report(artifact_dir: Path) -> dict[str, object]:
    selection = build_evidence_selection(artifact_dir)
    persisted_selection = _load_json(artifact_dir / "evidence_selection.json")
    expected = selection["selected_pointers"]
    packet_evidence_count = selection["packet_evidence_count"]
    issue = _load_json(artifact_dir / "issue.json")
    agent_task = _load_json(artifact_dir / "agent_task.json")
    agent_trace = _load_json(artifact_dir / "agent_trace.json")
    refinement = _load_json(artifact_dir / "refinement.json")

    issue_evidence = _string_list(issue.get("evidence") if isinstance(issue, dict) else None)
    task_pointers = _string_list(agent_task.get("evidence_pointers") if isinstance(agent_task, dict) else None)
    trace_task = agent_trace.get("task") if isinstance(agent_trace, dict) else None
    trace_pointers = _string_list(trace_task.get("evidence_pointers") if isinstance(trace_task, dict) else None)
    refinement_evidence = _string_list(refinement.get("evidence") if isinstance(refinement, dict) else None)

    missing = {
        "issue": _missing(expected, issue_evidence),
        "agent_task": _missing(expected, task_pointers),
        "agent_trace": _missing(expected, trace_pointers),
        "refinement": _missing(expected, refinement_evidence),
    }
    checks = {
        "evidence_packet_pointers_present": bool(expected),
        "issue_json_present": isinstance(issue, dict),
        "agent_task_json_present": isinstance(agent_task, dict),
        "agent_trace_json_present": isinstance(agent_trace, dict),
        "refinement_json_present": isinstance(refinement, dict),
        "issue_contains_packet_pointers": bool(expected) and not missing["issue"],
        "agent_task_contains_packet_pointers": bool(expected) and not missing["agent_task"],
        "agent_trace_contains_packet_pointers": bool(expected) and not missing["agent_trace"],
        "refinement_contains_packet_pointers": bool(expected) and not missing["refinement"],
        "agent_trace_matches_agent_task": bool(task_pointers) and trace_pointers == task_pointers,
        "no_raw_audio_or_transcript_fragments": _no_raw_fragments(
            [*issue_evidence, *task_pointers, *trace_pointers, *refinement_evidence]
        ),
        "evidence_selection_json_present": isinstance(persisted_selection, dict),
        "evidence_selection_matches_loader": isinstance(persisted_selection, dict)
        and persisted_selection.get("selected_pointers") == expected,
    }
    return {
        "ok": all(checks.values()),
        "artifact_dir": str(artifact_dir),
        "checks": checks,
        "expected_pointers": expected,
        "missing": missing,
        "counts": {
            "expected_pointers": len(expected),
            "packet_evidence": packet_evidence_count,
            "safe_pointers": selection["safe_pointer_count"],
            "omitted_pointers": selection["omitted_pointer_count"],
            "issue_evidence": len(issue_evidence),
            "agent_task_pointers": len(task_pointers),
            "agent_trace_pointers": len(trace_pointers),
            "refinement_evidence": len(refinement_evidence),
        },
        "selection": {
            "budget": selection["budget"],
            "reason": selection["reason"],
            "selected_pointer_count": selection["selected_pointer_count"],
            "omitted_pointer_count": selection["omitted_pointer_count"],
        },
    }


def write_report(report: dict[str, object], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _load_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _missing(expected: list[str], actual: list[str]) -> list[str]:
    actual_set = set(actual)
    return [pointer for pointer in expected if pointer not in actual_set]


def _no_raw_fragments(values: list[str]) -> bool:
    forbidden_fragments = ("transcript://", "audio://", "data:audio", ".wav", ".mp3", ".webm", ".ogg")
    return not any(fragment in value.lower() for value in values for fragment in forbidden_fragments)


if __name__ == "__main__":
    main()
