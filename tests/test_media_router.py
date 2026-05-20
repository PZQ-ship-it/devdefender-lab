from devdefender_lab.media_router import (
    contains_forbidden_media_artifact_fields,
    default_mock_media_route_script,
    media_route_event_payload,
)


def test_media_route_event_payload_redacts_sensitive_command() -> None:
    payload = media_route_event_payload("media_published", command="target?token=secret")

    assert payload == {
        "kind": "media_published",
        "source": "mock-media-router",
        "command": "REDACTED",
    }


def test_default_mock_media_route_script_has_required_events() -> None:
    script = default_mock_media_route_script()

    assert [event.kind for event in script] == [
        "virtual_audio_ready",
        "virtual_video_ready",
        "media_published",
    ]
    assert all(event.source == "mock-media-router" for event in script)


def test_forbidden_media_artifact_fields_detect_nested_sensitive_payloads() -> None:
    assert contains_forbidden_media_artifact_fields({"event": {"video_path": "raw.webm"}}) is True
    assert contains_forbidden_media_artifact_fields({"event": {"audio_path": "raw.wav"}}) is True
    assert contains_forbidden_media_artifact_fields({"event": {"token": "secret"}}) is True
    assert contains_forbidden_media_artifact_fields({"event": {"token": None}}) is False
    assert contains_forbidden_media_artifact_fields({"event": {"command": "local-test-target"}}) is False
