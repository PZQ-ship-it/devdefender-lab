import json

from pydantic import ValidationError

from devdefender_lab.briefing import (
    BriefingContext,
    BriefingEvidencePointer,
    MockBriefingAdapter,
    ProjectBriefingReport,
    contains_forbidden_briefing_artifact_fields,
    default_briefing_context,
)


def test_mock_briefing_adapter_returns_stakeholder_report() -> None:
    context = BriefingContext(
        project_name="DevDefender Lab",
        task_goal="Package the briefing room skill.",
        changed_files=[
            "skills/project-briefing-room/SKILL.md",
            "skills/project-briefing-room/SKILL.md",
        ],
        tests=["quick_validate.py skills/project-briefing-room"],
        evidence_pointers=[
            "timeline://thread-1#event=0&kind=meeting_created",
            "slide://thread-1#page=1",
        ],
    )

    report = MockBriefingAdapter().build_report(context)
    payload = report.model_dump(mode="json")

    assert report.generated_by == "mock-briefing-adapter"
    assert "stakeholder" in report.audience_summary
    assert report.architecture_diagrams[0].kind == "architecture"
    assert report.progress_status
    assert report.requirements_coverage
    assert report.experiment_results
    assert report.risks_and_unknowns
    assert report.stakeholder_questions
    assert report.follow_up_tasks
    assert report.evidence_pointers[0].pointer == "timeline://thread-1#event=0&kind=meeting_created"
    assert context.changed_files == ["skills/project-briefing-room/SKILL.md"]
    json.dumps(payload)
    assert contains_forbidden_briefing_artifact_fields(payload) is False


def test_default_briefing_context_builds_serializable_report() -> None:
    report = MockBriefingAdapter().build_report(default_briefing_context())

    payload = json.loads(report.model_dump_json())

    assert payload["project_name"] == "DevDefender Lab"
    assert payload["evidence_pointers"] == [
        {
            "pointer": "timeline://phase4d#event=0&kind=meeting_created",
            "label": "Primary meeting/evidence timeline pointer",
        },
        {
            "pointer": "slide://phase4d#page=1",
            "label": "Primary slide/deck pointer",
        },
    ]


def test_briefing_evidence_pointer_rejects_unsafe_pointer() -> None:
    try:
        BriefingEvidencePointer(pointer="transcript://thread-1#t=12", label="unsafe")
    except ValidationError as exc:
        assert "Unsafe evidence pointer" in str(exc)
    else:
        raise AssertionError("Expected unsafe evidence pointer to fail.")


def test_project_briefing_report_forbids_extra_fields() -> None:
    payload = MockBriefingAdapter().build_report(default_briefing_context()).model_dump(mode="json")
    payload["raw_audio"] = "data:audio/wav;base64,abc"

    try:
        ProjectBriefingReport.model_validate(payload)
    except ValidationError as exc:
        assert "Extra inputs are not permitted" in str(exc)
    else:
        raise AssertionError("Expected extra raw_audio field to fail.")


def test_project_briefing_report_rejects_secret_fragments() -> None:
    payload = MockBriefingAdapter().build_report(default_briefing_context()).model_dump(mode="json")
    payload["audience_summary"] = "LIVEKIT_API_SECRET=test-secret"

    try:
        ProjectBriefingReport.model_validate(payload)
    except ValidationError as exc:
        assert "forbidden secret" in str(exc)
    else:
        raise AssertionError("Expected secret fragment to fail.")


def test_context_rejects_invalid_evidence_pointer() -> None:
    try:
        BriefingContext(task_goal="Package briefing.", evidence_pointers=["audio://thread/file.wav"])
    except ValidationError as exc:
        assert "Unsafe evidence pointers" in str(exc)
    else:
        raise AssertionError("Expected invalid evidence pointer to fail.")


def test_forbidden_briefing_artifact_field_detector_checks_nested_payloads() -> None:
    assert contains_forbidden_briefing_artifact_fields({"safe": ["timeline://thread#event=0&kind=meeting_created"]}) is False
    assert contains_forbidden_briefing_artifact_fields({"nested": {"token": "abc"}}) is True
    assert contains_forbidden_briefing_artifact_fields({"summary": "Bearer abc.def"}) is True
