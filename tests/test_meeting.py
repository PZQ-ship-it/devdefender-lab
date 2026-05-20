from devdefender_lab.meeting import (
    contains_forbidden_meeting_artifact_fields,
    meeting_event_payload,
    redact_meeting_url,
)


def test_meeting_event_payload_redacts_sensitive_url_parts() -> None:
    payload = meeting_event_payload(
        "meeting_joined",
        meeting_url="https://meeting.example/join?room=abc&token=secret-token&pwd=secret-password#fragment",
    )

    assert payload == {
        "kind": "meeting_joined",
        "source": "local-meeting-test",
        "command": "https://meeting.example/join?room=abc&token=REDACTED&pwd=REDACTED",
    }


def test_redact_meeting_url_truncates_plain_values() -> None:
    redacted = redact_meeting_url("x" * 200)

    assert redacted == "x" * 128


def test_redact_meeting_url_masks_zoom_meeting_id_and_outer_zoom_url() -> None:
    redacted = redact_meeting_url("https://zoom.us/wc/join/123456789?pwd=secret&token=secret-token")
    outer = redact_meeting_url(
        "http://room.test/zoom-discovery-test?auto_zoom_discovery=1"
        "&zoom_url=https%3A%2F%2Fzoom.us%2Fwc%2Fjoin%2F123456789%3Fpwd%3Dsecret"
    )

    assert redacted == "https://zoom.us/wc/join/REDACTED?pwd=REDACTED&token=REDACTED"
    assert outer == "http://room.test/zoom-discovery-test?auto_zoom_discovery=1&zoom_url=REDACTED"


def test_redact_meeting_url_preserves_livekit_room_handle() -> None:
    assert redact_meeting_url("livekit://room/devdefender-abc") == "livekit://room/devdefender-abc"


def test_forbidden_meeting_artifact_fields_detect_nested_sensitive_payloads() -> None:
    assert contains_forbidden_meeting_artifact_fields({"event": {"cookies": "secret"}}) is True
    assert contains_forbidden_meeting_artifact_fields({"event": {"token": "secret"}}) is True
    assert contains_forbidden_meeting_artifact_fields({"event": {"token": None}}) is False
    assert contains_forbidden_meeting_artifact_fields({"event": {"audio_path": "raw.wav"}}) is True
    assert contains_forbidden_meeting_artifact_fields({"event": {"command": "room=abc"}}) is False
