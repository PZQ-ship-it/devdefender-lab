import pytest
from pydantic import ValidationError

from devdefender_lab.audio_provider import (
    AudioTimelineEvent,
    LiveKitAudioProvider,
    MockAudioProvider,
    audio_event_payload,
)
from devdefender_lab.config import Settings


def test_mock_audio_provider_emits_structured_timeline_events() -> None:
    provider = MockAudioProvider()
    provider.start_session()

    events = []
    while True:
        event = provider.emit_timeline_event()
        if event is None:
            break
        events.append(event)
    provider.stop_session()

    assert [event.kind for event in events] == ["speech_started", "noise", "tts_word", "speech_interrupted"]
    assert events[2].token == "next"
    assert all(event.source == "mock-audio" for event in events)


def test_mock_audio_provider_requires_running_session() -> None:
    provider = MockAudioProvider()

    with pytest.raises(RuntimeError, match="not running"):
        provider.emit_timeline_event()


def test_audio_event_payload_excludes_raw_audio_and_transcript_fields() -> None:
    event = AudioTimelineEvent(kind="tts_word", token="next", source="mock")

    payload = audio_event_payload(event)

    assert payload == {"kind": "tts_word", "source": "mock", "token": "next"}
    assert "audio" not in payload
    assert "transcript" not in payload
    assert "raw" not in payload


def test_audio_timeline_event_forbids_unknown_raw_fields() -> None:
    with pytest.raises(ValidationError):
        AudioTimelineEvent(kind="tts_word", token="next", raw_audio_path="meeting.wav")


def test_livekit_provider_requires_credentials() -> None:
    provider = LiveKitAudioProvider(settings=Settings())

    with pytest.raises(RuntimeError, match="LIVEKIT_URL"):
        provider.start_session()


def test_livekit_provider_generates_redacted_token_report() -> None:
    provider = LiveKitAudioProvider(
        settings=Settings(
            livekit_url="wss://example.livekit.cloud",
            livekit_api_key="test-key",
            livekit_api_secret="test-secret-with-enough-length-for-hs256",
        ),
        room_name="room-1",
        identity="identity-1",
    )

    report = provider.smoke()
    payload = report.model_dump_json()

    assert report.room_name == "room-1"
    assert report.identity == "identity-1"
    assert report.token_length > 100
    assert report.room_check == "not_run"
    assert "test-secret" not in payload
    assert "test-key" not in payload
