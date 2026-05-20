from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


MediaRouteEventKind = Literal[
    "virtual_audio_ready",
    "virtual_video_ready",
    "media_published",
    "media_route_error",
]

MEDIA_SOURCE = "mock-media-router"


class MediaRouteTimelineEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: MediaRouteEventKind
    source: str = MEDIA_SOURCE
    command: str | None = Field(default=None, max_length=128)
    confidence: float | None = Field(default=None, ge=0, le=1)
    offset_ms: int | None = Field(default=None, ge=0)


def media_route_event_payload(
    kind: MediaRouteEventKind,
    *,
    source: str = MEDIA_SOURCE,
    command: str | None = None,
    confidence: float | None = None,
    offset_ms: int | None = None,
) -> dict[str, object]:
    event = MediaRouteTimelineEvent(
        kind=kind,
        source=source,
        command=_redact_media_command(command),
        confidence=confidence,
        offset_ms=offset_ms,
    )
    return event.model_dump(exclude_none=True)


def default_mock_media_route_script() -> list[MediaRouteTimelineEvent]:
    return [
        MediaRouteTimelineEvent(kind="virtual_audio_ready", command="deterministic-audio", confidence=1.0, offset_ms=0),
        MediaRouteTimelineEvent(kind="virtual_video_ready", command="slidev-canvas", confidence=1.0, offset_ms=0),
        MediaRouteTimelineEvent(kind="media_published", command="local-test-target", confidence=1.0, offset_ms=120),
    ]


def contains_forbidden_media_artifact_fields(payload: object) -> bool:
    forbidden_keys = {
        "audio",
        "audio_path",
        "audio_url",
        "browser_profile",
        "cookie",
        "cookies",
        "local_storage",
        "raw_audio",
        "screenshot",
        "text",
        "token",
        "transcript",
        "video",
        "video_path",
        "video_url",
    }
    forbidden_fragments = ("data:audio", "data:video", ".mp3", ".mp4", ".wav", ".webm")
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in forbidden_keys and value not in {None, ""}:
                return True
            if contains_forbidden_media_artifact_fields(value):
                return True
        return False
    if isinstance(payload, list):
        return any(contains_forbidden_media_artifact_fields(value) for value in payload)
    if isinstance(payload, str):
        lowered = payload.lower()
        return any(fragment in lowered for fragment in forbidden_fragments)
    return False


def _redact_media_command(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = value.strip()[:128]
    lowered = cleaned.lower()
    if any(fragment in lowered for fragment in ("token=", "secret=", "password=", "pwd=")):
        return "REDACTED"
    return cleaned
