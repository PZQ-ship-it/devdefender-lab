from pathlib import Path


def test_install_project_briefing_room_skill_script_has_safe_defaults() -> None:
    script = Path("scripts/install_project_briefing_room_skill.ps1").read_text(encoding="utf-8")

    assert 'Join-Path $RepoRoot "skills\\project-briefing-room"' in script
    assert 'Join-Path $CodexHome "skills"' in script
    assert 'project-briefing-room' in script
    assert "quick_validate.py" in script
    assert "Copy-Item" in script
    assert "Remove-Item" not in script
    assert "git reset" not in script


def test_install_project_briefing_room_skill_script_reports_invocation_hint() -> None:
    script = Path("scripts/install_project_briefing_room_skill.ps1").read_text(encoding="utf-8")

    assert "InvocationHint" in script
    assert "Use $project-briefing-room to brief me and update the execution plan from my feedback." in script
    assert "ConvertTo-Json" in script
