import json
from pathlib import Path

from devdefender_lab.config import Settings
from devdefender_lab.models import Phase1Status
from devdefender_lab.workflow import resume_phase1, start_phase1


def test_phase1_interrupts_then_resumes_with_artifacts(tmp_path: Path) -> None:
    settings = Settings(llm_mode="mock", artifact_dir=tmp_path)
    evidence_packet = {
        "ok": True,
        "checks": {
            "replay_ok": True,
            "thread_id_present": True,
            "evidence_present": True,
            "all_events_have_slide_pointer": True,
            "all_pointers_structured": True,
            "no_raw_audio_or_transcript": True,
        },
        "thread_id": "test-phase1",
        "evidence": [
            {
                "event_index": 0,
                "kind": "speech_interrupted",
                "slide_index": 3,
                "timeline_pointer": "timeline://test-phase1#event=0&kind=speech_interrupted",
                "slide_pointer": "slide://test-phase1#page=3",
            }
        ],
    }
    (tmp_path / "evidence_packet.json").write_text(json.dumps(evidence_packet), encoding="utf-8")

    session = start_phase1(settings, Path("sample_repo"), thread_id="test-phase1")

    interrupt = session["interrupt"]
    assert interrupt.thread_id == "test-phase1"
    assert interrupt.node_count >= 4
    assert interrupt.edge_count >= 3
    assert interrupt.deck_path.exists()
    assert (tmp_path / "graph.json").exists()
    assert (tmp_path / "session.json").exists()

    state = resume_phase1(
        session["app"],
        settings,
        session["thread_id"],
        "Can invalid payment amounts be captured?",
    )

    assert state["status"] == Phase1Status.COMPLETE.value
    assert "validate_payment" in state["defense"]
    assert state["issue"].title
    assert "timeline://test-phase1#event=0&kind=speech_interrupted" in state["issue"].evidence
    assert "slide://test-phase1#page=3" in state["issue"].evidence
    assert state["refinement"].status == "verified"
    assert state["refinement"].return_code == 0
    assert state["refinement"].test_path is not None
    assert state["refinement"].test_path.exists()
    assert state["refinement"].agent_task_path is not None
    assert state["refinement"].agent_task_path.exists()
    assert state["refinement"].agent_patch_path is not None
    assert state["refinement"].agent_patch_path.exists()
    assert state["refinement"].agent_test_report_path is not None
    assert state["refinement"].agent_test_report_path.exists()
    assert state["refinement"].agent_trace_path is not None
    assert state["refinement"].agent_trace_path.exists()
    assert (tmp_path / "state.json").exists()
    assert (tmp_path / "defense.md").exists()
    assert (tmp_path / "issue.json").exists()
    assert (tmp_path / "refinement.json").exists()
    assert (tmp_path / "agent_task.json").exists()
    assert (tmp_path / "patch.diff").exists()
    assert (tmp_path / "test_report.json").exists()
    assert (tmp_path / "agent_trace.json").exists()
    assert (tmp_path / "evidence_selection.json").exists()
    issue_payload = json.loads((tmp_path / "issue.json").read_text(encoding="utf-8"))
    task_payload = json.loads((tmp_path / "agent_task.json").read_text(encoding="utf-8"))
    selection_payload = json.loads((tmp_path / "evidence_selection.json").read_text(encoding="utf-8"))
    assert "timeline://test-phase1#event=0&kind=speech_interrupted" in issue_payload["evidence"]
    assert "slide://test-phase1#page=3" in issue_payload["evidence"]
    assert "timeline://test-phase1#event=0&kind=speech_interrupted" in task_payload["evidence_pointers"]
    assert "slide://test-phase1#page=3" in task_payload["evidence_pointers"]
    assert selection_payload["selected_pointers"] == [
        "timeline://test-phase1#event=0&kind=speech_interrupted",
        "slide://test-phase1#page=3",
    ]
