from devdefender_lab.meeting_provisioner import (
    LiveKitMeetingProvisioner,
    PROVISIONER_SOURCE,
    MockMeetingProvisioner,
    contains_forbidden_provisioning_artifact_fields,
    create_provisioner,
    meeting_created_event_payload,
    safe_provisioned_meeting,
)
from devdefender_lab.config import Settings


def test_mock_meeting_provisioner_returns_secret_ref_and_redacted_safe_payload() -> None:
    provisioner = MockMeetingProvisioner()
    meeting = provisioner.create_meeting(
        topic="Defense Session",
        duration_minutes=20,
        room_thread_id="thread-1",
    )

    safe = safe_provisioned_meeting(meeting)

    assert meeting.provider == "mock"
    assert meeting.meeting_id
    assert "mock-host-token" in meeting.host_start_url
    assert safe["provider"] == "mock"
    assert safe["meeting_id"] == meeting.meeting_id
    assert safe["secret_ref"].startswith("env:DEVDEFENDER_MEETING_HOST_START_URL:")
    assert "host_start_url" not in safe
    assert "mock-host-token" not in str(safe)
    assert "mock-join-token" not in str(safe)
    assert safe["join_url"].endswith("join_url=REDACTED&token=REDACTED")


def test_meeting_created_event_payload_uses_redacted_join_url() -> None:
    meeting = MockMeetingProvisioner().create_meeting(topic="Defense Session", room_thread_id="thread-1")

    event = meeting_created_event_payload(meeting)

    assert event == {
        "kind": "meeting_created",
        "source": PROVISIONER_SOURCE,
        "command": safe_provisioned_meeting(meeting)["join_url"],
        "confidence": 1,
        "offset_ms": 0,
    }


def test_livekit_meeting_provisioner_returns_room_handle_without_secret_artifacts() -> None:
    provisioner = LiveKitMeetingProvisioner(
        settings=Settings(
            livekit_url="wss://example.livekit.cloud",
            livekit_api_key="test-key",
            livekit_api_secret="test-secret-with-enough-length-for-hs256",
        ),
        create_room=False,
    )

    meeting = provisioner.create_meeting(topic="Defense Session", room_thread_id="thread-1")
    safe = safe_provisioned_meeting(meeting)
    teardown = provisioner.teardown_meeting(meeting)

    assert meeting.provider == "livekit"
    assert meeting.meeting_id.startswith("devdefender-")
    assert meeting.join_url == f"livekit://room/{meeting.meeting_id}"
    assert safe == {
        "provider": "livekit",
        "meeting_id": meeting.meeting_id,
        "topic": "Defense Session",
        "join_url": meeting.join_url,
        "expires_at": meeting.expires_at,
        "secret_ref": f"env:LIVEKIT_API_SECRET:{meeting.meeting_id}",
    }
    assert teardown.ok is True
    assert teardown.command == "livekit-room-scope-released"
    assert "test-secret" not in str(safe)
    assert "test-key" not in str(safe)


def test_livekit_meeting_provisioner_requires_credentials() -> None:
    provisioner = LiveKitMeetingProvisioner(settings=Settings(), create_room=False)

    try:
        provisioner.create_meeting(topic="Defense Session", room_thread_id="thread-1")
    except RuntimeError as exc:
        assert "LIVEKIT_URL" in str(exc)
    else:
        raise AssertionError("Expected missing LiveKit credentials to fail.")


def test_meeting_created_event_payload_uses_provider_specific_source() -> None:
    provisioner = LiveKitMeetingProvisioner(
        settings=Settings(
            livekit_url="wss://example.livekit.cloud",
            livekit_api_key="test-key",
            livekit_api_secret="test-secret-with-enough-length-for-hs256",
        ),
        create_room=False,
    )
    meeting = provisioner.create_meeting(topic="Defense Session", room_thread_id="thread-1")

    event = meeting_created_event_payload(meeting)

    assert event["source"] == "livekit-meeting-provisioner"
    assert event["command"] == meeting.join_url


def test_provisioning_forbidden_artifact_fields_detect_secrets() -> None:
    assert contains_forbidden_provisioning_artifact_fields({"host_start_url": "https://meeting.local/start"}) is True
    assert contains_forbidden_provisioning_artifact_fields({"token": "secret"}) is True
    assert contains_forbidden_provisioning_artifact_fields({"command": "https://meeting.local?token=REDACTED"}) is False
    assert contains_forbidden_provisioning_artifact_fields({"secret_ref": "env:DEVDEFENDER_MEETING_HOST_START_URL:abc"}) is False


def test_create_provisioner_rejects_unknown_provider() -> None:
    assert isinstance(create_provisioner("mock"), MockMeetingProvisioner)
    assert isinstance(
        create_provisioner(
            "livekit",
            settings=Settings(
                livekit_url="wss://example.livekit.cloud",
                livekit_api_key="test-key",
                livekit_api_secret="test-secret-with-enough-length-for-hs256",
            ),
            create_livekit_room=False,
        ),
        LiveKitMeetingProvisioner,
    )

    try:
        create_provisioner("zoom")
    except ValueError as exc:
        assert "Unsupported meeting provider" in str(exc)
    else:
        raise AssertionError("Expected unsupported provider to fail.")
