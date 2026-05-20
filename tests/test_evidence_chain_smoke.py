import json
from pathlib import Path

from scripts.evidence_chain_smoke import build_report, write_report


def test_evidence_chain_smoke_accepts_propagated_pointers(tmp_path: Path) -> None:
    pointers = _write_complete_chain(tmp_path)

    report = build_report(tmp_path)

    assert report["ok"] is True
    assert report["expected_pointers"] == pointers
    assert report["checks"]["evidence_selection_json_present"] is True
    assert report["checks"]["evidence_selection_matches_loader"] is True
    assert report["selection"]["selected_pointer_count"] == 2
    assert report["missing"] == {
        "issue": [],
        "agent_task": [],
        "agent_trace": [],
        "refinement": [],
    }


def test_evidence_chain_smoke_fails_when_issue_missing_pointer(tmp_path: Path) -> None:
    pointers = _write_complete_chain(tmp_path)
    issue = json.loads((tmp_path / "issue.json").read_text(encoding="utf-8"))
    issue["evidence"] = [item for item in issue["evidence"] if item != pointers[0]]
    (tmp_path / "issue.json").write_text(json.dumps(issue), encoding="utf-8")

    report = build_report(tmp_path)

    assert report["ok"] is False
    assert report["checks"]["issue_contains_packet_pointers"] is False
    assert report["missing"]["issue"] == [pointers[0]]


def test_evidence_chain_smoke_fails_on_raw_audio_or_transcript_fragments(tmp_path: Path) -> None:
    _write_complete_chain(tmp_path)
    refinement = json.loads((tmp_path / "refinement.json").read_text(encoding="utf-8"))
    refinement["evidence"].append("transcript://thread-1#t=12.3")
    (tmp_path / "refinement.json").write_text(json.dumps(refinement), encoding="utf-8")

    report = build_report(tmp_path)

    assert report["ok"] is False
    assert report["checks"]["no_raw_audio_or_transcript_fragments"] is False


def test_evidence_chain_smoke_writes_report(tmp_path: Path) -> None:
    report = {"ok": True, "checks": {"issue_contains_packet_pointers": True}}
    out = tmp_path / "nested" / "evidence_chain_smoke.json"

    write_report(report, out)

    assert json.loads(out.read_text(encoding="utf-8")) == report


def _write_complete_chain(tmp_path: Path) -> list[str]:
    pointers = [
        "timeline://thread-1#event=0&kind=speech_interrupted",
        "slide://thread-1#page=3",
    ]
    packet = {
        "ok": True,
        "checks": {"no_raw_audio_or_transcript": True},
        "evidence": [
            {
                "timeline_pointer": pointers[0],
                "slide_pointer": pointers[1],
            }
        ],
    }
    (tmp_path / "evidence_packet.json").write_text(json.dumps(packet), encoding="utf-8")
    (tmp_path / "issue.json").write_text(
        json.dumps({"evidence": ["typed feedback", *pointers]}),
        encoding="utf-8",
    )
    (tmp_path / "agent_task.json").write_text(
        json.dumps({"evidence_pointers": ["repo://sample_repo", *pointers]}),
        encoding="utf-8",
    )
    (tmp_path / "agent_trace.json").write_text(
        json.dumps({"task": {"evidence_pointers": ["repo://sample_repo", *pointers]}}),
        encoding="utf-8",
    )
    (tmp_path / "refinement.json").write_text(
        json.dumps({"evidence": ["typed feedback", *pointers, "pytest output"]}),
        encoding="utf-8",
    )
    (tmp_path / "evidence_selection.json").write_text(
        json.dumps(
            {
                "ok": True,
                "reason": "ok",
                "budget": 24,
                "packet_evidence_count": 1,
                "safe_pointer_count": 2,
                "selected_pointer_count": 2,
                "omitted_pointer_count": 0,
                "selected_pointers": pointers,
                "omitted_pointers": [],
            }
        ),
        encoding="utf-8",
    )
    return pointers
