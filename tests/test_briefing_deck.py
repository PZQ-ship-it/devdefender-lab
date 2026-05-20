from pathlib import Path

from pydantic import ValidationError

from devdefender_lab.briefing import MockBriefingAdapter, contains_forbidden_briefing_artifact_fields, default_briefing_context
from devdefender_lab.briefing_deck import BriefingDeckArtifact, render_briefing_deck, write_briefing_deck


def test_render_briefing_deck_outputs_slidev_markdown_and_script() -> None:
    report = MockBriefingAdapter().build_report(default_briefing_context())

    artifact = render_briefing_deck(report)

    assert artifact.deck_path is None
    assert artifact.script_path is None
    assert artifact.diagram_count == 1
    assert artifact.slide_count >= 9
    assert artifact.deck_markdown.startswith("---\ntheme: default\n")
    assert "# DevDefender Lab" in artifact.deck_markdown
    assert "## Stakeholder Summary" in artifact.deck_markdown
    assert "## Skill and Runtime Boundary" in artifact.deck_markdown
    assert "```mermaid\nflowchart LR" in artifact.deck_markdown
    assert "## Progress" in artifact.deck_markdown
    assert "## Requirements Coverage" in artifact.deck_markdown
    assert "## Experiment Results" in artifact.deck_markdown
    assert "## Risks and Decisions" in artifact.deck_markdown
    assert "## Stakeholder Questions" in artifact.deck_markdown
    assert "## Next Asks" in artifact.deck_markdown
    assert "## Evidence Pointers" in artifact.deck_markdown
    assert "Opening. This briefing is for DevDefender Lab." in artifact.presenter_script
    assert "Close. The supporting evidence is kept as structured pointers" in artifact.presenter_script
    assert contains_forbidden_briefing_artifact_fields(artifact.model_dump(mode="json")) is False


def test_write_briefing_deck_persists_deck_and_script(tmp_path: Path) -> None:
    report = MockBriefingAdapter().build_report(default_briefing_context())

    artifact = write_briefing_deck(report, tmp_path)

    assert artifact.deck_path == tmp_path / "briefing_deck" / "slides.md"
    assert artifact.script_path == tmp_path / "briefing_deck" / "presenter_script.md"
    assert artifact.deck_path.exists()
    assert artifact.script_path.exists()
    assert artifact.deck_path.read_text(encoding="utf-8") == artifact.deck_markdown
    assert artifact.script_path.read_text(encoding="utf-8") == artifact.presenter_script


def test_briefing_deck_artifact_rejects_secret_fragments() -> None:
    try:
        BriefingDeckArtifact(
            deck_markdown="# Demo\n\nLIVEKIT_API_SECRET=test-secret",
            presenter_script="Opening.",
            diagram_count=0,
            slide_count=1,
        )
    except ValidationError as exc:
        assert "forbidden secret" in str(exc)
    else:
        raise AssertionError("Expected forbidden deck artifact to fail.")


def test_render_briefing_deck_strips_wrapped_mermaid_fences() -> None:
    report = MockBriefingAdapter().build_report(default_briefing_context())
    report.architecture_diagrams[0].mermaid_hint = "```mermaid\nflowchart TD\n  A --> B\n```"

    artifact = render_briefing_deck(report)

    assert "```mermaid\nflowchart TD\n  A --> B\n```" in artifact.deck_markdown
    assert "```mermaid\n```mermaid" not in artifact.deck_markdown
