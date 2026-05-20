import json
from pathlib import Path

from scripts.project_briefing_room import run_session
from scripts.project_briefing_room_smoke import DEFAULT_FEEDBACK_CLARIFICATIONS


def test_project_briefing_room_session_blocks_on_pending_clarifications(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Demo\n", encoding="utf-8")

    report = run_session(
        repo=repo,
        agent_backend="workspace",
        artifact_dir=tmp_path / "artifacts",
        feedback="The briefing is too one-way. Please clarify my feedback before continuing.",
        clarification_answers=[],
        out=tmp_path / "session.json",
        session_md=tmp_path / "session.md",
    )

    text = (tmp_path / "session.md").read_text(encoding="utf-8")

    assert report["ok"] is True
    assert report["can_continue"] is False
    assert report["pending_questions"]
    assert "needs_clarification" in text
    assert "## Stakeholder Feedback" in text
    assert "## Execution Gate" in text
    assert json.loads((tmp_path / "session.json").read_text(encoding="utf-8"))["can_continue"] is False


def test_project_briefing_room_session_can_continue_with_clarifications(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Demo\n", encoding="utf-8")

    report = run_session(
        repo=repo,
        agent_backend="workspace",
        artifact_dir=tmp_path / "artifacts",
        feedback="The briefing should listen to my feedback and update the execution plan.",
        clarification_answers=DEFAULT_FEEDBACK_CLARIFICATIONS,
        out=tmp_path / "session.json",
        session_md=tmp_path / "session.md",
    )

    text = (tmp_path / "session.md").read_text(encoding="utf-8")

    assert report["ok"] is True
    assert report["can_continue"] is True
    assert report["pending_questions"] == []
    assert "ready_to_continue" in text
    assert "Ready: continue in the same Codex session" in text
    assert (tmp_path / "artifacts" / "briefing_deck" / "slides.md").exists()
