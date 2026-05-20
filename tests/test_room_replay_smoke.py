import json

from scripts.room_replay_smoke import build_report, load_session_thread_id


def _write_jsonl(path, rows) -> None:
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def test_room_replay_smoke_accepts_replayable_slide_and_timeline_logs(tmp_path) -> None:
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    (artifact_dir / "session.json").write_text('{"thread_id":"thread-1"}', encoding="utf-8")
    _write_jsonl(
        artifact_dir / "timeline_events.jsonl",
        [
            {
                "timestamp": "2026-01-01T00:00:00+00:00",
                "thread_id": "thread-1",
                "kind": "speech_interrupted",
                "source": "judge",
                "confidence": 0.9,
                "offset_ms": 120,
            },
            {
                "timestamp": "2026-01-01T00:00:01+00:00",
                "thread_id": "thread-1",
                "kind": "tts_word",
                "source": "tts-anchor-smoke",
                "token": "next",
                "offset_ms": 1250,
            },
        ],
    )
    _write_jsonl(
        artifact_dir / "slide_events.jsonl",
        [
            {
                "timestamp": "2026-01-01T00:00:01+00:00",
                "thread_id": "thread-1",
                "action": "next",
                "slide_index": 2,
                "source": "timeline:tts-anchor-smoke",
            }
        ],
    )

    report = build_report(artifact_dir)

    assert report["ok"] is True
    assert report["current_slide_index"] == 2
    assert report["interruption"]["active"] is False
    assert report["mapped_slide_count"] == 1
    assert report["expected_mappings"] == [{"action": "next", "source": "timeline:tts-anchor-smoke"}]
    assert report["actual_mappings"] == [{"action": "next", "source": "timeline:tts-anchor-smoke"}]
    assert report["slide_sequence_violations"] == []
    assert report["timeline_slide_pointers"] == [
        {
            "timestamp": "2026-01-01T00:00:00+00:00",
            "kind": "speech_interrupted",
            "source": "judge",
            "slide_index_at_event": 1,
        },
        {
            "timestamp": "2026-01-01T00:00:01+00:00",
            "kind": "tts_word",
            "source": "tts-anchor-smoke",
            "slide_index_at_event": 2,
        },
    ]


def test_room_replay_smoke_rejects_missing_mapped_slide_event(tmp_path) -> None:
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    _write_jsonl(
        artifact_dir / "timeline_events.jsonl",
        [
            {
                "timestamp": "2026-01-01T00:00:00+00:00",
                "thread_id": "thread-1",
                "kind": "tts_word",
                "source": "tts-anchor-smoke",
                "token": "next",
            }
        ],
    )
    _write_jsonl(
        artifact_dir / "slide_events.jsonl",
        [
            {
                "timestamp": "2026-01-01T00:00:00+00:00",
                "thread_id": "thread-1",
                "action": "next",
                "slide_index": 2,
                "source": "manual",
            }
        ],
    )

    report = build_report(artifact_dir)

    assert report["ok"] is False
    assert report["checks"]["timeline_mappings_match_slide_events"] is False
    assert report["missing_mappings"] == [{"action": "next", "source": "timeline:tts-anchor-smoke"}]


def test_room_replay_smoke_can_filter_thread_id(tmp_path) -> None:
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    _write_jsonl(
        artifact_dir / "timeline_events.jsonl",
        [
            {
                "timestamp": "2026-01-01T00:00:00+00:00",
                "thread_id": "old-thread",
                "kind": "tts_word",
                "source": "old",
                "token": "next",
            },
            {
                "timestamp": "2026-01-01T00:00:01+00:00",
                "thread_id": "current-thread",
                "kind": "manual_voice_command",
                "source": "operator",
                "command": "next",
            },
        ],
    )
    _write_jsonl(
        artifact_dir / "slide_events.jsonl",
        [
            {
                "timestamp": "2026-01-01T00:00:01+00:00",
                "thread_id": "current-thread",
                "action": "next",
                "slide_index": 2,
                "source": "timeline:operator",
            }
        ],
    )

    report = build_report(artifact_dir, thread_id="current-thread")

    assert report["ok"] is True
    assert report["timeline_threads"] == ["current-thread"]
    assert report["slide_threads"] == ["current-thread"]


def test_room_replay_smoke_rejects_same_source_wrong_action_mapping(tmp_path) -> None:
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    (artifact_dir / "session.json").write_text('{"thread_id":"thread-1"}', encoding="utf-8")
    _write_jsonl(
        artifact_dir / "timeline_events.jsonl",
        [
            {
                "timestamp": "2026-01-01T00:00:00+00:00",
                "thread_id": "thread-1",
                "kind": "manual_voice_command",
                "source": "operator",
                "command": "next",
            }
        ],
    )
    _write_jsonl(
        artifact_dir / "slide_events.jsonl",
        [
            {
                "timestamp": "2026-01-01T00:00:00+00:00",
                "thread_id": "thread-1",
                "action": "prev",
                "slide_index": 1,
                "source": "timeline:operator",
            }
        ],
    )

    report = build_report(artifact_dir)

    assert report["ok"] is False
    assert report["checks"]["timeline_mapped_event_count_matches"] is True
    assert report["checks"]["timeline_mappings_match_slide_events"] is False
    assert report["missing_mappings"] == [{"action": "next", "source": "timeline:operator"}]
    assert report["unexpected_mappings"] == [{"action": "prev", "source": "timeline:operator"}]


def test_room_replay_smoke_allows_manual_slide_before_timeline_mapping(tmp_path) -> None:
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    (artifact_dir / "session.json").write_text('{"thread_id":"thread-1"}', encoding="utf-8")
    _write_jsonl(
        artifact_dir / "timeline_events.jsonl",
        [
            {
                "timestamp": "2026-01-01T00:00:01+00:00",
                "thread_id": "thread-1",
                "kind": "tts_word",
                "source": "tts-anchor-smoke",
                "token": "next",
            }
        ],
    )
    _write_jsonl(
        artifact_dir / "slide_events.jsonl",
        [
            {
                "timestamp": "2026-01-01T00:00:00+00:00",
                "thread_id": "thread-1",
                "action": "next",
                "slide_index": 2,
                "source": "slide-sync-smoke",
            },
            {
                "timestamp": "2026-01-01T00:00:01+00:00",
                "thread_id": "thread-1",
                "action": "next",
                "slide_index": 3,
                "source": "timeline:tts-anchor-smoke",
            },
        ],
    )

    report = build_report(artifact_dir)

    assert report["ok"] is True
    assert report["current_slide_index"] == 3
    assert report["expected_mappings"] == [{"action": "next", "source": "timeline:tts-anchor-smoke"}]
    assert report["slide_sequence_violations"] == []


def test_room_replay_smoke_rejects_non_replayable_slide_sequence(tmp_path) -> None:
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    (artifact_dir / "session.json").write_text('{"thread_id":"thread-1"}', encoding="utf-8")
    _write_jsonl(
        artifact_dir / "timeline_events.jsonl",
        [
            {
                "timestamp": "2026-01-01T00:00:00+00:00",
                "thread_id": "thread-1",
                "kind": "tts_word",
                "source": "tts-anchor-smoke",
                "token": "next",
            }
        ],
    )
    _write_jsonl(
        artifact_dir / "slide_events.jsonl",
        [
            {
                "timestamp": "2026-01-01T00:00:00+00:00",
                "thread_id": "thread-1",
                "action": "next",
                "slide_index": 4,
                "source": "timeline:tts-anchor-smoke",
            }
        ],
    )

    report = build_report(artifact_dir)

    assert report["ok"] is False
    assert report["checks"]["slide_event_sequence_replayable"] is False
    assert report["slide_sequence_violations"] == [
        {
            "timestamp": "2026-01-01T00:00:00+00:00",
            "action": "next",
            "source": "timeline:tts-anchor-smoke",
            "expected_slide_index": 2,
            "actual_slide_index": 4,
        }
    ]


def test_room_replay_smoke_correlates_timeline_events_to_slide_at_event_time(tmp_path) -> None:
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    (artifact_dir / "session.json").write_text('{"thread_id":"thread-1"}', encoding="utf-8")
    _write_jsonl(
        artifact_dir / "timeline_events.jsonl",
        [
            {
                "timestamp": "2026-01-01T00:00:00.500000+00:00",
                "thread_id": "thread-1",
                "kind": "speech_started",
                "source": "judge",
            },
            {
                "timestamp": "2026-01-01T00:00:01.500000+00:00",
                "thread_id": "thread-1",
                "kind": "speech_interrupted",
                "source": "judge",
            },
        ],
    )
    _write_jsonl(
        artifact_dir / "slide_events.jsonl",
        [
            {
                "timestamp": "2026-01-01T00:00:01+00:00",
                "thread_id": "thread-1",
                "action": "goto",
                "slide_index": 4,
                "source": "manual",
            }
        ],
    )

    report = build_report(artifact_dir)

    assert report["ok"] is False
    assert report["checks"]["timeline_events_have_slide_pointers"] is True
    assert report["timeline_slide_pointers"] == [
        {
            "timestamp": "2026-01-01T00:00:00.500000+00:00",
            "kind": "speech_started",
            "source": "judge",
            "slide_index_at_event": 1,
        },
        {
            "timestamp": "2026-01-01T00:00:01.500000+00:00",
            "kind": "speech_interrupted",
            "source": "judge",
            "slide_index_at_event": 4,
        },
    ]


def test_room_replay_smoke_accepts_meeting_lifecycle_events_without_extra_slide_mapping(tmp_path) -> None:
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    (artifact_dir / "session.json").write_text('{"thread_id":"thread-1"}', encoding="utf-8")
    _write_jsonl(
        artifact_dir / "timeline_events.jsonl",
        [
            {
                "timestamp": "2026-01-01T00:00:00+00:00",
                "thread_id": "thread-1",
                "kind": "tts_word",
                "source": "tts-anchor-smoke",
                "token": "next",
            },
            {
                "timestamp": "2026-01-01T00:00:01+00:00",
                "thread_id": "thread-1",
                "kind": "meeting_join_started",
                "source": "local-meeting-test",
                "command": "https://meeting.local/devdefender?token=REDACTED",
            },
            {
                "timestamp": "2026-01-01T00:00:02+00:00",
                "thread_id": "thread-1",
                "kind": "meeting_joined",
                "source": "local-meeting-test",
                "command": "https://meeting.local/devdefender?token=REDACTED",
            },
            {
                "timestamp": "2026-01-01T00:00:03+00:00",
                "thread_id": "thread-1",
                "kind": "meeting_left",
                "source": "local-meeting-test",
                "command": "https://meeting.local/devdefender?token=REDACTED",
            },
        ],
    )
    _write_jsonl(
        artifact_dir / "slide_events.jsonl",
        [
            {
                "timestamp": "2026-01-01T00:00:00+00:00",
                "thread_id": "thread-1",
                "action": "next",
                "slide_index": 2,
                "source": "timeline:tts-anchor-smoke",
            }
        ],
    )

    report = build_report(artifact_dir)

    assert report["ok"] is True
    assert report["expected_mappings"] == [{"action": "next", "source": "timeline:tts-anchor-smoke"}]
    assert report["timeline_slide_pointers"] == [
        {
            "timestamp": "2026-01-01T00:00:00+00:00",
            "kind": "tts_word",
            "source": "tts-anchor-smoke",
            "slide_index_at_event": 2,
        },
        {
            "timestamp": "2026-01-01T00:00:01+00:00",
            "kind": "meeting_join_started",
            "source": "local-meeting-test",
            "slide_index_at_event": 2,
        },
        {
            "timestamp": "2026-01-01T00:00:02+00:00",
            "kind": "meeting_joined",
            "source": "local-meeting-test",
            "slide_index_at_event": 2,
        },
        {
            "timestamp": "2026-01-01T00:00:03+00:00",
            "kind": "meeting_left",
            "source": "local-meeting-test",
            "slide_index_at_event": 2,
        },
    ]


def test_room_replay_smoke_accepts_media_route_events_without_extra_slide_mapping(tmp_path) -> None:
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    (artifact_dir / "session.json").write_text('{"thread_id":"thread-1"}', encoding="utf-8")
    _write_jsonl(
        artifact_dir / "timeline_events.jsonl",
        [
            {
                "timestamp": "2026-01-01T00:00:00+00:00",
                "thread_id": "thread-1",
                "kind": "manual_voice_command",
                "source": "media-route-smoke",
                "command": "goto",
                "slide_index": 1,
            },
            {
                "timestamp": "2026-01-01T00:00:01+00:00",
                "thread_id": "thread-1",
                "kind": "virtual_audio_ready",
                "source": "mock-media-router",
                "command": "deterministic-audio",
            },
            {
                "timestamp": "2026-01-01T00:00:02+00:00",
                "thread_id": "thread-1",
                "kind": "virtual_video_ready",
                "source": "mock-media-router",
                "command": "slidev-canvas",
            },
            {
                "timestamp": "2026-01-01T00:00:03+00:00",
                "thread_id": "thread-1",
                "kind": "media_published",
                "source": "mock-media-router",
                "command": "local-test-target",
            },
        ],
    )
    _write_jsonl(
        artifact_dir / "slide_events.jsonl",
        [
            {
                "timestamp": "2026-01-01T00:00:00+00:00",
                "thread_id": "thread-1",
                "action": "goto",
                "slide_index": 1,
                "source": "timeline:media-route-smoke",
            }
        ],
    )

    report = build_report(artifact_dir)

    assert report["ok"] is True
    assert report["expected_mappings"] == [{"action": "goto", "source": "timeline:media-route-smoke"}]
    assert report["timeline_slide_pointers"][-3:] == [
        {
            "timestamp": "2026-01-01T00:00:01+00:00",
            "kind": "virtual_audio_ready",
            "source": "mock-media-router",
            "slide_index_at_event": 1,
        },
        {
            "timestamp": "2026-01-01T00:00:02+00:00",
            "kind": "virtual_video_ready",
            "source": "mock-media-router",
            "slide_index_at_event": 1,
        },
        {
            "timestamp": "2026-01-01T00:00:03+00:00",
            "kind": "media_published",
            "source": "mock-media-router",
            "slide_index_at_event": 1,
        },
    ]


def test_room_replay_smoke_defaults_to_session_thread_id(tmp_path) -> None:
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    (artifact_dir / "session.json").write_text('{"thread_id":"current-thread"}', encoding="utf-8")
    _write_jsonl(
        artifact_dir / "timeline_events.jsonl",
        [
            {
                "timestamp": "2026-01-01T00:00:00+00:00",
                "thread_id": "old-thread",
                "kind": "tts_word",
                "source": "old",
                "token": "next",
            },
            {
                "timestamp": "2026-01-01T00:00:01+00:00",
                "thread_id": "current-thread",
                "kind": "manual_voice_command",
                "source": "operator",
                "command": "next",
            },
        ],
    )
    _write_jsonl(
        artifact_dir / "slide_events.jsonl",
        [
            {
                "timestamp": "2026-01-01T00:00:00+00:00",
                "thread_id": "old-thread",
                "action": "next",
                "slide_index": 2,
                "source": "timeline:old",
            }
        ],
    )

    report = build_report(artifact_dir)

    assert report["ok"] is False
    assert report["thread_id"] == "current-thread"
    assert report["thread_id_source"] == "session.json"
    assert report["slide_threads"] == []
    assert report["timeline_threads"] == ["current-thread"]
    assert report["checks"]["slide_events_present"] is False


def test_room_replay_smoke_loads_session_thread_id(tmp_path) -> None:
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    (artifact_dir / "session.json").write_text('{"thread_id":"thread-from-session"}', encoding="utf-8")

    assert load_session_thread_id(artifact_dir) == "thread-from-session"
