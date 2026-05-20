from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from devdefender_lab.briefing import ProjectBriefingReport, contains_forbidden_briefing_artifact_fields


class BriefingDeckArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deck_markdown: str = Field(min_length=1)
    presenter_script: str = Field(min_length=1)
    diagram_count: int = Field(ge=0)
    slide_count: int = Field(ge=1)
    deck_path: Path | None = None
    script_path: Path | None = None

    @model_validator(mode="after")
    def reject_forbidden_artifacts(self):
        if contains_forbidden_briefing_artifact_fields(self.model_dump(mode="json")):
            raise ValueError("Briefing deck contains forbidden secret, raw audio, or transcript artifact fields.")
        return self


def render_briefing_deck(report: ProjectBriefingReport) -> BriefingDeckArtifact:
    slides = [
        _title_slide(report),
        _summary_slide(report),
        *_diagram_slides(report),
        _progress_slide(report),
        _requirements_slide(report),
        _experiments_slide(report),
        _risks_slide(report),
        _questions_slide(report),
        _follow_up_slide(report),
        _evidence_slide(report),
    ]
    deck_markdown = "\n\n---\n\n".join([_frontmatter(report), *slides]).rstrip() + "\n"
    presenter_script = render_presenter_script(report)
    return BriefingDeckArtifact(
        deck_markdown=deck_markdown,
        presenter_script=presenter_script,
        diagram_count=len(report.architecture_diagrams),
        slide_count=len(slides),
    )


def write_briefing_deck(report: ProjectBriefingReport, artifact_dir: Path) -> BriefingDeckArtifact:
    artifact = render_briefing_deck(report)
    deck_dir = Path(artifact_dir) / "briefing_deck"
    deck_dir.mkdir(parents=True, exist_ok=True)
    deck_path = deck_dir / "slides.md"
    script_path = deck_dir / "presenter_script.md"
    deck_path.write_text(artifact.deck_markdown, encoding="utf-8")
    script_path.write_text(artifact.presenter_script, encoding="utf-8")
    return artifact.model_copy(update={"deck_path": deck_path, "script_path": script_path})


def render_presenter_script(report: ProjectBriefingReport) -> str:
    paragraphs = [
        (
            f"Opening. This briefing is for {report.project_name}. "
            f"The current goal is: {_one_line(report.task_goal)}"
        ),
        f"Summary. {_one_line(report.audience_summary)}",
    ]
    if report.architecture_diagrams:
        diagram_titles = ", ".join(diagram.title for diagram in report.architecture_diagrams)
        paragraphs.append(f"Architecture. I will explain the system using these diagram views: {diagram_titles}.")
    if report.progress_status:
        paragraphs.append(
            "Progress. "
            + " ".join(
                f"{item.label} is {item.status.replace('_', ' ')}: {_one_line(item.plain_language_summary)}"
                for item in report.progress_status[:5]
            )
        )
    if report.requirements_coverage:
        paragraphs.append(
            "Requirements. "
            + " ".join(
                f"{item.requirement} is {item.status}: {_one_line(item.explanation)}"
                for item in report.requirements_coverage[:5]
            )
        )
    if report.experiment_results:
        paragraphs.append(
            "Experiments. "
            + " ".join(
                f"{item.name} {item.status}: {_one_line(item.summary)}" for item in report.experiment_results[:5]
            )
        )
    if report.risks_and_unknowns:
        paragraphs.append(
            "Risks. "
            + " ".join(
                f"{item.severity} risk, {item.risk} Mitigation: {_one_line(item.mitigation)}"
                for item in report.risks_and_unknowns[:5]
            )
        )
    if report.stakeholder_questions:
        paragraphs.append(
            "Questions for the user. "
            + " ".join(
                f"{item.question} This matters because {_one_line(item.why_it_matters)}"
                for item in report.stakeholder_questions[:5]
            )
        )
    if report.follow_up_tasks:
        paragraphs.append(
            "Next asks. "
            + " ".join(
                f"{item.priority} priority for {item.owner_hint}: {_one_line(item.task)}"
                for item in report.follow_up_tasks[:5]
            )
        )
    paragraphs.append("Close. The supporting evidence is kept as structured pointers, not raw meeting data.")
    return "\n\n".join(paragraphs).rstrip() + "\n"


def _frontmatter(report: ProjectBriefingReport) -> str:
    return "\n".join(
        [
            "---",
            "theme: default",
            f"title: {_yaml_safe(report.project_name)} Project Briefing",
            "---",
        ]
    )


def _title_slide(report: ProjectBriefingReport) -> str:
    return "\n".join(
        [
            f"# {_markdown_text(report.project_name)}",
            "",
            "Project Briefing Room",
            "",
            f"Goal: {_markdown_text(report.task_goal)}",
            "",
            f"Generated by: `{_markdown_text(report.generated_by)}`",
        ]
    )


def _summary_slide(report: ProjectBriefingReport) -> str:
    return "\n".join(["## Stakeholder Summary", "", _markdown_text(report.audience_summary)])


def _diagram_slides(report: ProjectBriefingReport) -> list[str]:
    if not report.architecture_diagrams:
        return [
            "\n".join(
                [
                    "## Architecture View",
                    "",
                    "No diagram request was provided.",
                    "",
                    "```mermaid",
                    "flowchart LR",
                    "  Skill[Briefing skill] --> Runtime[DevDefender runtime]",
                    "  Runtime --> Deck[Stakeholder deck]",
                    "  Runtime --> Feedback[Stakeholder feedback plan]",
                    "```",
                ]
            )
        ]
    slides = []
    for diagram in report.architecture_diagrams:
        slides.append(
            "\n".join(
                [
                    f"## {_markdown_text(diagram.title)}",
                    "",
                    _markdown_text(diagram.audience_goal),
                    "",
                    "```mermaid",
                    _clean_mermaid(diagram.mermaid_hint),
                    "```",
                    "",
                    *_pointer_lines(diagram.evidence_pointers),
                ]
            )
        )
    return slides


def _progress_slide(report: ProjectBriefingReport) -> str:
    return "\n".join(["## Progress", "", *_progress_lines(report)])


def _requirements_slide(report: ProjectBriefingReport) -> str:
    return "\n".join(["## Requirements Coverage", "", *_requirement_lines(report)])


def _experiments_slide(report: ProjectBriefingReport) -> str:
    return "\n".join(["## Experiment Results", "", *_experiment_lines(report)])


def _risks_slide(report: ProjectBriefingReport) -> str:
    return "\n".join(["## Risks and Decisions", "", *_risk_lines(report)])


def _questions_slide(report: ProjectBriefingReport) -> str:
    return "\n".join(["## Stakeholder Questions", "", *_question_lines(report)])


def _follow_up_slide(report: ProjectBriefingReport) -> str:
    return "\n".join(["## Next Asks", "", *_follow_up_lines(report)])


def _evidence_slide(report: ProjectBriefingReport) -> str:
    lines = ["## Evidence Pointers", ""]
    if not report.evidence_pointers:
        lines.append("- No evidence pointers attached.")
    else:
        lines.extend(f"- `{item.pointer}` - {_markdown_text(item.label)}" for item in report.evidence_pointers)
    return "\n".join(lines)


def _progress_lines(report: ProjectBriefingReport) -> list[str]:
    if not report.progress_status:
        return ["- No progress items provided."]
    return [
        f"- **{_status_label(item.status)}** {_markdown_text(item.label)}: "
        f"{_markdown_text(item.plain_language_summary)}"
        for item in report.progress_status
    ]


def _requirement_lines(report: ProjectBriefingReport) -> list[str]:
    if not report.requirements_coverage:
        return ["- No requirement coverage items provided."]
    return [
        f"- **{_status_label(item.status)}** {_markdown_text(item.requirement)}: {_markdown_text(item.explanation)}"
        for item in report.requirements_coverage
    ]


def _experiment_lines(report: ProjectBriefingReport) -> list[str]:
    if not report.experiment_results:
        return ["- No experiment results provided."]
    lines = []
    for item in report.experiment_results:
        command = f" Command: `{_markdown_text(item.command)}`" if item.command else ""
        lines.append(f"- **{_status_label(item.status)}** {_markdown_text(item.name)}: {_markdown_text(item.summary)}{command}")
    return lines


def _risk_lines(report: ProjectBriefingReport) -> list[str]:
    if not report.risks_and_unknowns:
        return ["- No risks provided."]
    return [
        f"- **{_status_label(item.severity)}** {_markdown_text(item.risk)} "
        f"Mitigation: {_markdown_text(item.mitigation)} Decision needed: {'yes' if item.decision_needed else 'no'}."
        for item in report.risks_and_unknowns
    ]


def _question_lines(report: ProjectBriefingReport) -> list[str]:
    if not report.stakeholder_questions:
        return ["- No stakeholder questions provided."]
    lines = []
    for item in report.stakeholder_questions:
        lines.append(f"- {_markdown_text(item.question)} Why it matters: {_markdown_text(item.why_it_matters)}")
        if item.options:
            lines.extend(f"  - Option: {_markdown_text(option)}" for option in item.options)
    return lines


def _follow_up_lines(report: ProjectBriefingReport) -> list[str]:
    if not report.follow_up_tasks:
        return ["- No follow-up tasks provided."]
    return [
        f"- **{_status_label(item.priority)}** {_markdown_text(item.task)} Owner: `{_markdown_text(item.owner_hint)}`"
        for item in report.follow_up_tasks
    ]


def _pointer_lines(pointers: list[str]) -> list[str]:
    if not pointers:
        return []
    return ["Evidence:", *[f"- `{pointer}`" for pointer in pointers]]


def _clean_mermaid(value: str | None) -> str:
    if not value:
        return "\n".join(
            [
                "flowchart LR",
                "  Skill[Briefing skill] --> Runtime[DevDefender runtime]",
                "  Runtime --> Deck[Stakeholder deck]",
                "  Runtime --> Feedback[Stakeholder feedback plan]",
            ]
        )
    cleaned = value.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    return cleaned or _clean_mermaid(None)


def _status_label(value: str) -> str:
    return value.replace("_", " ").upper()


def _one_line(value: str) -> str:
    return " ".join(str(value).split())


def _markdown_text(value: object) -> str:
    text = _one_line(str(value))
    return text.replace("`", "'")


def _yaml_safe(value: str) -> str:
    return _markdown_text(value).replace('"', "'")
