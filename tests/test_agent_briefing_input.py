import json
from pathlib import Path

import pytest

from scripts.agent_briefing_input import generate_agent_briefing_input


def test_generate_agent_briefing_input_from_workspace_facts(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Demo\n\nProject Briefing Room docs.\n", encoding="utf-8")
    (tmp_path / "plan.md").write_text(
        "## Product entry accepted: provider-neutral agent briefing contract\n\nObserved result: `27 passed`.\n",
        encoding="utf-8",
    )
    (tmp_path / ".env").write_text("LIVEKIT_API_SECRET=super-secret-value\n", encoding="utf-8")
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    product_dir = artifact_dir / "project_briefing_room"
    product_dir.mkdir()
    (product_dir / "session.json").write_text(
        json.dumps({"ok": True, "checks": {"briefing_artifacts": True}}),
        encoding="utf-8",
    )

    result = generate_agent_briefing_input(repo=tmp_path, out=artifact_dir / "agent_briefing_input.json", agent_kind="codex")
    payload = json.loads((artifact_dir / "agent_briefing_input.json").read_text(encoding="utf-8"))

    assert result["ok"] is True
    assert result["agent_kind"] == "codex"
    assert payload["schema_version"] == "1"
    assert payload["agent_kind"] == "codex"
    assert payload["project_name"] == tmp_path.name
    assert "artifacts/project_briefing_room/session.json" in payload["artifacts"]
    assert "super-secret-value" not in json.dumps(payload)


def test_generate_agent_briefing_input_no_overwrite(tmp_path: Path) -> None:
    output = tmp_path / "artifacts" / "agent_briefing_input.json"
    output.parent.mkdir()
    output.write_text("{}", encoding="utf-8")

    with pytest.raises(FileExistsError):
        generate_agent_briefing_input(repo=tmp_path, out=output, overwrite=False)
