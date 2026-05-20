import json
import subprocess
from pathlib import Path

from devdefender_lab.briefing import contains_forbidden_briefing_artifact_fields
from devdefender_lab.briefing_workspace import WorkspaceBriefingAdapter


def test_workspace_briefing_adapter_collects_repo_docs_artifacts_and_git_status(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    (tmp_path / "README.md").write_text("# Demo Project\n\nProject Briefing Room docs.\n", encoding="utf-8")
    (tmp_path / "plan.md").write_text(
        "## Phase 4E iteration plan: workspace briefing adapter\n\nAccepted result: `29 passed`.\n",
        encoding="utf-8",
    )
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    product_dir = artifact_dir / "project_briefing_room"
    product_dir.mkdir()
    (product_dir / "session.json").write_text(
        json.dumps({"ok": True, "checks": {"briefing_artifacts": True, "briefing_feedback_plan": True}}),
        encoding="utf-8",
    )
    deck_dir = product_dir / "briefing_deck"
    deck_dir.mkdir()
    (deck_dir / "briefing_report.json").write_text(
        json.dumps(
            {
                "ok": True,
                "project_name": "Demo Project",
                "evidence_pointers": [
                    {"pointer": "timeline://thread-1#event=0&kind=briefing_generated", "label": "Briefing"},
                    {"pointer": "slide://thread-1#page=1", "label": "Slide"},
                ],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / ".env").write_text("LIVEKIT_API_SECRET=super-secret-value\n", encoding="utf-8")
    (tmp_path / "src.py").write_text("print('changed')\n", encoding="utf-8")

    adapter = WorkspaceBriefingAdapter(tmp_path)
    context = adapter.build_context()
    report = adapter.build_report(context)
    payload = report.model_dump(mode="json")

    assert "src.py" in context.changed_files
    assert "README.md" in context.docs
    assert "plan.md" in context.docs
    assert "artifacts/project_briefing_room/session.json" in context.artifacts
    assert context.evidence_pointers[0] == "timeline://thread-1#event=0&kind=briefing_generated"
    assert report.generated_by == "workspace-briefing-adapter"
    assert "changed file" in report.audience_summary
    assert report.architecture_diagrams[0].diagram_id == "workspace-briefing-flow"
    assert report.requirements_coverage[0].status == "met"
    assert "super-secret-value" not in json.dumps(payload)
    assert contains_forbidden_briefing_artifact_fields(payload) is False


def test_workspace_briefing_adapter_falls_back_without_git_or_artifacts(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")

    report = WorkspaceBriefingAdapter(tmp_path).build_report()

    assert report.project_name == tmp_path.name
    assert report.progress_status
    assert report.evidence_pointers[0].pointer == "timeline://workspace#event=0&kind=briefing_generated"
    assert contains_forbidden_briefing_artifact_fields(report.model_dump(mode="json")) is False


def test_workspace_briefing_adapter_uses_agent_briefing_input(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")
    agent_input = tmp_path / "agent.json"
    agent_input.write_text(
        json.dumps(
            {
                "schema_version": "1",
                "agent_kind": "codex",
                "project_name": "Agent Portable Briefing",
                "task_goal": "Let any code agent submit briefing context with one JSON file.",
                "current_task": "Implement the provider-neutral briefing contract.",
                "completed_work": ["Workspace backend is accepted."],
                "in_progress_work": ["Contract merge is being implemented."],
                "blockers": ["Need a product decision on external agent traces."],
                "next_steps": ["Run the workspace quick gate with --agent-input."],
                "requirements": ["One JSON file can steer the stakeholder briefing."],
                "open_questions": ["Should Aider be the next external adapter?"],
                "evidence_pointers": ["timeline://agent-thread#event=0&kind=briefing_generated"],
            }
        ),
        encoding="utf-8",
    )

    adapter = WorkspaceBriefingAdapter(tmp_path, agent_input_path=agent_input)
    context = adapter.build_context()
    report = adapter.build_report(context)
    payload = report.model_dump(mode="json")

    assert context.project_name == "Agent Portable Briefing"
    assert context.current_task == "Implement the provider-neutral briefing contract."
    assert "Workspace backend is accepted." in context.completed_work
    assert report.project_name == "Agent Portable Briefing"
    assert "Current task focus" in report.audience_summary
    assert any(item["status"] == "blocked" for item in payload["progress_status"])
    assert any(item["task"] == "Run the workspace quick gate with --agent-input." for item in payload["follow_up_tasks"])
    assert any(item["question"] == "Should Aider be the next external adapter?" for item in payload["stakeholder_questions"])
    assert contains_forbidden_briefing_artifact_fields(payload) is False


def _init_git_repo(path: Path) -> None:
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=path, check=True)
