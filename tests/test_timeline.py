from pathlib import Path

from devdefender_lab.slide_control import SlideEventLog
from devdefender_lab.timeline import (
    TimelineEventLog,
    TimelineEvent,
    VoiceTimelineAdapter,
    replay_timeline_events,
    timeline_event_slide_action,
    timeline_interruption_state,
)


def test_tts_anchor_word_triggers_next_slide(tmp_path: Path) -> None:
    timeline_log = TimelineEventLog(tmp_path / "timeline_events.jsonl", thread_id="thread-1")
    slide_log = SlideEventLog(tmp_path / "slide_events.jsonl", thread_id="thread-1")
    adapter = VoiceTimelineAdapter(timeline_log, slide_log)

    result = adapter.ingest(kind="tts_word", token="下一页", source="tts", offset_ms=1200)

    assert result.slide_event is not None
    assert result.slide_event.action == "next"
    assert result.slide_event.slide_index == 2
    assert slide_log.current_slide_index() == 2
    assert replay_timeline_events(timeline_log.path)[0].token == "下一页"


def test_noise_event_does_not_trigger_slide_change(tmp_path: Path) -> None:
    timeline_log = TimelineEventLog(tmp_path / "timeline_events.jsonl", thread_id="thread-1")
    slide_log = SlideEventLog(tmp_path / "slide_events.jsonl", thread_id="thread-1")
    adapter = VoiceTimelineAdapter(timeline_log, slide_log)

    result = adapter.ingest(kind="noise", source="mic", confidence=0.91)

    assert result.slide_event is None
    assert slide_log.current_slide_index() == 1
    assert len(timeline_log.events()) == 1


def test_interruption_event_records_timeline_without_slide_change(tmp_path: Path) -> None:
    timeline_log = TimelineEventLog(tmp_path / "timeline_events.jsonl", thread_id="thread-1")
    slide_log = SlideEventLog(tmp_path / "slide_events.jsonl", thread_id="thread-1")
    adapter = VoiceTimelineAdapter(timeline_log, slide_log)

    result = adapter.ingest(kind="speech_interrupted", source="mic", offset_ms=2400)

    assert result.slide_event is None
    assert slide_log.events() == []
    assert timeline_log.events()[0].kind == "speech_interrupted"


def test_interruption_state_tracks_active_and_handled_events(tmp_path: Path) -> None:
    timeline_log = TimelineEventLog(tmp_path / "timeline_events.jsonl", thread_id="thread-1")
    slide_log = SlideEventLog(tmp_path / "slide_events.jsonl", thread_id="thread-1")
    adapter = VoiceTimelineAdapter(timeline_log, slide_log)

    adapter.ingest(kind="speech_interrupted", source="mic", confidence=0.91, offset_ms=2400)
    active = timeline_interruption_state(timeline_log.events())

    assert active.active is True
    assert active.event_count == 1
    assert active.source == "mic"
    assert active.confidence == 0.91
    assert active.offset_ms == 2400

    adapter.ingest(kind="manual_voice_command", command="next", source="operator")
    handled = timeline_interruption_state(timeline_log.events())

    assert handled.active is False
    assert handled.event_count == 1


def test_manual_voice_command_can_goto_slide(tmp_path: Path) -> None:
    timeline_log = TimelineEventLog(tmp_path / "timeline_events.jsonl", thread_id="thread-1")
    slide_log = SlideEventLog(tmp_path / "slide_events.jsonl", thread_id="thread-1")
    adapter = VoiceTimelineAdapter(timeline_log, slide_log)

    result = adapter.ingest(kind="manual_voice_command", command="goto", slide_index=5, source="test")

    assert result.slide_event is not None
    assert result.slide_event.action == "goto"
    assert result.slide_event.slide_index == 5


def test_livekit_browser_events_are_recorded_without_slide_change(tmp_path: Path) -> None:
    timeline_log = TimelineEventLog(tmp_path / "timeline_events.jsonl", thread_id="thread-1")
    slide_log = SlideEventLog(tmp_path / "slide_events.jsonl", thread_id="thread-1")
    adapter = VoiceTimelineAdapter(timeline_log, slide_log)

    result = adapter.ingest(kind="livekit_connected", command="room-1", source="browser-livekit")

    assert result.slide_event is None
    assert slide_log.events() == []
    event = timeline_log.events()[0]
    assert event.kind == "livekit_connected"
    assert event.command == "room-1"
    assert event.source == "browser-livekit"


def test_meeting_lifecycle_events_are_recorded_without_slide_change(tmp_path: Path) -> None:
    timeline_log = TimelineEventLog(tmp_path / "timeline_events.jsonl", thread_id="thread-1")
    slide_log = SlideEventLog(tmp_path / "slide_events.jsonl", thread_id="thread-1")
    adapter = VoiceTimelineAdapter(timeline_log, slide_log)

    result = adapter.ingest(kind="meeting_joined", command="https://meeting.local/devdefender", source="local-meeting-test")

    assert result.slide_event is None
    assert slide_log.events() == []
    event = timeline_log.events()[0]
    assert event.kind == "meeting_joined"
    assert event.command == "https://meeting.local/devdefender"
    assert event.source == "local-meeting-test"


def test_meeting_provisioning_events_are_recorded_without_slide_change(tmp_path: Path) -> None:
    timeline_log = TimelineEventLog(tmp_path / "timeline_events.jsonl", thread_id="thread-1")
    slide_log = SlideEventLog(tmp_path / "slide_events.jsonl", thread_id="thread-1")
    adapter = VoiceTimelineAdapter(timeline_log, slide_log)

    result = adapter.ingest(
        kind="meeting_created",
        command="https://meeting.local/provisioned/abc?token=REDACTED",
        source="mock-meeting-provisioner",
    )

    assert result.slide_event is None
    assert slide_log.events() == []
    event = timeline_log.events()[0]
    assert event.kind == "meeting_created"
    assert event.command == "https://meeting.local/provisioned/abc?token=REDACTED"
    assert event.source == "mock-meeting-provisioner"


def test_media_route_events_are_recorded_without_slide_change(tmp_path: Path) -> None:
    timeline_log = TimelineEventLog(tmp_path / "timeline_events.jsonl", thread_id="thread-1")
    slide_log = SlideEventLog(tmp_path / "slide_events.jsonl", thread_id="thread-1")
    adapter = VoiceTimelineAdapter(timeline_log, slide_log)

    result = adapter.ingest(kind="media_published", command="local-test-target", source="mock-media-router")

    assert result.slide_event is None
    assert slide_log.events() == []
    event = timeline_log.events()[0]
    assert event.kind == "media_published"
    assert event.command == "local-test-target"
    assert event.source == "mock-media-router"


def test_timeline_event_log_filters_replay_to_current_thread(tmp_path: Path) -> None:
    path = tmp_path / "timeline_events.jsonl"
    thread_1 = TimelineEventLog(path, thread_id="thread-1")
    thread_2 = TimelineEventLog(path, thread_id="thread-2")

    thread_1.record(kind="tts_word", token="next", source="old")
    thread_2.record(kind="livekit_connected", command="room-2", source="current")

    assert [event.thread_id for event in thread_2.events()] == ["thread-2"]
    assert thread_2.events()[0].kind == "livekit_connected"
    assert [event.thread_id for event in replay_timeline_events(path)] == ["thread-1", "thread-2"]
    assert [event.thread_id for event in replay_timeline_events(path, thread_id="thread-1")] == ["thread-1"]


def test_timeline_event_slide_action_is_replayable_without_logs() -> None:
    assert (
        timeline_event_slide_action(
            TimelineEvent(
                timestamp="2026-01-01T00:00:00+00:00",
                thread_id="thread-1",
                kind="tts_word",
                source="tts",
                token="next",
            )
        )
        == "next"
    )
    assert (
        timeline_event_slide_action(
            TimelineEvent(
                timestamp="2026-01-01T00:00:00+00:00",
                thread_id="thread-1",
                kind="manual_voice_command",
                source="operator",
                command="goto",
                slide_index=3,
            )
        )
        == "goto"
    )
    assert (
        timeline_event_slide_action(
            TimelineEvent(
                timestamp="2026-01-01T00:00:00+00:00",
                thread_id="thread-1",
                kind="noise",
                source="mic",
            )
        )
        is None
    )
