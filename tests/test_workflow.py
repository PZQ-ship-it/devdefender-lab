from pathlib import Path

from devdefender_lab.config import Settings
from devdefender_lab.models import Phase1Status
from devdefender_lab.workflow import resume_phase1, start_phase1


def test_phase1_interrupts_then_resumes_with_artifacts(tmp_path: Path) -> None:
    settings = Settings(llm_mode="mock", artifact_dir=tmp_path)

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
    assert state["refinement"].status == "verified"
    assert state["refinement"].return_code == 0
    assert state["refinement"].test_path is not None
    assert state["refinement"].test_path.exists()
    assert (tmp_path / "state.json").exists()
    assert (tmp_path / "defense.md").exists()
    assert (tmp_path / "issue.json").exists()
    assert (tmp_path / "refinement.json").exists()
