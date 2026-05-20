from pathlib import Path

import pytest

from devdefender_lab.slide_control import SlideEventLog, replay_slide_events


def test_slide_event_log_records_and_replays_actions(tmp_path: Path) -> None:
    log = SlideEventLog(tmp_path / "slide_events.jsonl", thread_id="thread-1")

    first = log.record("next")
    second = log.record("goto", slide_index=7, source="test")
    third = log.record("prev")

    replayed = replay_slide_events(log.path)

    assert [event.action for event in replayed] == ["next", "goto", "prev"]
    assert [event.slide_index for event in replayed] == [2, 7, 6]
    assert [event.thread_id for event in replayed] == ["thread-1", "thread-1", "thread-1"]
    assert replayed[0].timestamp == first.timestamp
    assert replayed[1].source == second.source
    assert replayed[2].slide_index == third.slide_index
    assert log.current_slide_index() == 6


def test_slide_event_log_rejects_invalid_goto(tmp_path: Path) -> None:
    log = SlideEventLog(tmp_path / "slide_events.jsonl", thread_id="thread-1")

    with pytest.raises(ValueError, match="goto requires"):
        log.record("goto", slide_index=0)


def test_slide_event_log_filters_replay_to_current_thread(tmp_path: Path) -> None:
    path = tmp_path / "slide_events.jsonl"
    thread_1 = SlideEventLog(path, thread_id="thread-1")
    thread_2 = SlideEventLog(path, thread_id="thread-2")

    thread_1.record("goto", slide_index=9, source="old")
    thread_2.record("next", source="current")

    assert [event.thread_id for event in thread_2.events()] == ["thread-2"]
    assert thread_2.current_slide_index() == 2
    assert [event.thread_id for event in replay_slide_events(path)] == ["thread-1", "thread-2"]
    assert [event.thread_id for event in replay_slide_events(path, thread_id="thread-1")] == ["thread-1"]
