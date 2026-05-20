from __future__ import annotations

import json
import threading
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from devdefender_lab.slide_control import SlideControlEvent, SlideEventLog


TimelineEventKind = Literal[
    "speech_started",
    "speech_interrupted",
    "tts_word",
    "manual_voice_command",
    "noise",
    "livekit_connected",
    "livekit_disconnected",
    "livekit_error",
    "audio_track_published",
    "meeting_created",
    "meeting_provision_failed",
    "meeting_join_started",
    "meeting_joined",
    "meeting_left",
    "meeting_error",
    "virtual_audio_ready",
    "virtual_video_ready",
    "media_published",
    "media_route_error",
]

DEFAULT_NEXT_ANCHORS = {"next", "continue", "\u4e0b\u4e00\u9875", "\u4e0b\u4e00\u4e2a", "\u7ee7\u7eed"}
DEFAULT_PREV_ANCHORS = {"previous", "prev", "back", "\u4e0a\u4e00\u9875", "\u4e0a\u4e00\u4e2a", "\u8fd4\u56de"}


class TimelineEvent(BaseModel):
    timestamp: str
    thread_id: str
    kind: TimelineEventKind
    source: str = "manual"
    token: str | None = None
    command: str | None = None
    slide_index: int | None = Field(default=None, ge=1)
    confidence: float | None = Field(default=None, ge=0, le=1)
    offset_ms: int | None = Field(default=None, ge=0)


class TimelineMappingResult(BaseModel):
    timeline_event: TimelineEvent
    slide_event: SlideControlEvent | None = None


class InterruptionState(BaseModel):
    active: bool = False
    event_count: int = 0
    timestamp: str | None = None
    source: str | None = None
    confidence: float | None = None
    offset_ms: int | None = None


class TimelineEventLog:
    def __init__(self, path: Path, thread_id: str) -> None:
        self.path = path
        self.thread_id = thread_id
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(
        self,
        kind: str,
        source: str = "manual",
        token: str | None = None,
        command: str | None = None,
        slide_index: int | None = None,
        confidence: float | None = None,
        offset_ms: int | None = None,
    ) -> TimelineEvent:
        with self._lock:
            event = TimelineEvent(
                timestamp=datetime.now(timezone.utc).isoformat(),
                thread_id=self.thread_id,
                kind=kind,
                source=source,
                token=_sanitize_short_text(token),
                command=_sanitize_short_text(command),
                slide_index=slide_index,
                confidence=confidence,
                offset_ms=offset_ms,
            )
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(event.model_dump_json() + "\n")
            return event

    def events(self) -> list[TimelineEvent]:
        return replay_timeline_events(self.path, thread_id=self.thread_id)


class VoiceTimelineAdapter:
    def __init__(
        self,
        timeline_log: TimelineEventLog,
        slide_log: SlideEventLog,
        next_anchors: set[str] | None = None,
        prev_anchors: set[str] | None = None,
    ) -> None:
        self.timeline_log = timeline_log
        self.slide_log = slide_log
        self.next_anchors = next_anchors or DEFAULT_NEXT_ANCHORS
        self.prev_anchors = prev_anchors or DEFAULT_PREV_ANCHORS

    def ingest(
        self,
        kind: str,
        source: str = "manual",
        token: str | None = None,
        command: str | None = None,
        slide_index: int | None = None,
        confidence: float | None = None,
        offset_ms: int | None = None,
    ) -> TimelineMappingResult:
        timeline_event = self.timeline_log.record(
            kind=kind,
            source=source,
            token=token,
            command=command,
            slide_index=slide_index,
            confidence=confidence,
            offset_ms=offset_ms,
        )
        slide_event = self._map_to_slide_event(timeline_event)
        return TimelineMappingResult(timeline_event=timeline_event, slide_event=slide_event)

    def _map_to_slide_event(self, event: TimelineEvent) -> SlideControlEvent | None:
        action = timeline_event_slide_action(event, self.next_anchors, self.prev_anchors)
        if action:
            return self.slide_log.record(action, slide_index=event.slide_index, source=f"timeline:{event.source}")
        return None


def replay_timeline_events(path: Path, thread_id: str | None = None) -> list[TimelineEvent]:
    if not path.exists():
        return []
    events: list[TimelineEvent] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        event = TimelineEvent.model_validate(json.loads(line))
        if thread_id is None or event.thread_id == thread_id:
            events.append(event)
    return events


def timeline_interruption_state(events: Sequence[TimelineEvent]) -> InterruptionState:
    interruptions = [event for event in events if event.kind == "speech_interrupted"]
    if not interruptions:
        return InterruptionState()

    last_interruption = interruptions[-1]
    last_resume = next(
        (event for event in reversed(events) if event.kind in {"tts_word", "manual_voice_command"}),
        None,
    )
    active = last_resume is None or last_resume.timestamp < last_interruption.timestamp
    return InterruptionState(
        active=active,
        event_count=len(interruptions),
        timestamp=last_interruption.timestamp,
        source=last_interruption.source,
        confidence=last_interruption.confidence,
        offset_ms=last_interruption.offset_ms,
    )


def timeline_event_slide_action(
    event: TimelineEvent,
    next_anchors: set[str] | None = None,
    prev_anchors: set[str] | None = None,
) -> str | None:
    if event.kind == "manual_voice_command":
        return _command_to_slide_action(event.command)
    if event.kind == "tts_word":
        token = _normalize_token(event.token)
        normalized_next = {_normalize_token(anchor) for anchor in (next_anchors or DEFAULT_NEXT_ANCHORS)}
        normalized_prev = {_normalize_token(anchor) for anchor in (prev_anchors or DEFAULT_PREV_ANCHORS)}
        if token in normalized_next:
            return "next"
        if token in normalized_prev:
            return "prev"
    return None


def _command_to_slide_action(command: str | None) -> str | None:
    normalized = _normalize_token(command)
    if normalized in {_normalize_token(anchor) for anchor in DEFAULT_NEXT_ANCHORS}:
        return "next"
    if normalized in {_normalize_token(anchor) for anchor in DEFAULT_PREV_ANCHORS}:
        return "prev"
    if normalized in {"goto", "\u8df3\u8f6c"}:
        return "goto"
    return None


def _normalize_token(value: str | None) -> str:
    if not value:
        return ""
    return value.strip().lower()


def _sanitize_short_text(value: str | None, max_len: int = 128) -> str | None:
    if value is None:
        return None
    return value.strip()[:max_len]
