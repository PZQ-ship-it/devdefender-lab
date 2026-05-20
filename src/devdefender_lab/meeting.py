from __future__ import annotations

from typing import Literal
from urllib.parse import ParseResult, parse_qsl, urlencode, urlparse, urlunparse

from pydantic import BaseModel, ConfigDict, Field


MeetingEventKind = Literal[
    "meeting_join_started",
    "meeting_joined",
    "meeting_left",
    "meeting_error",
]

MEETING_SOURCE = "local-meeting-test"
SENSITIVE_QUERY_NAMES = {
    "access_token",
    "auth",
    "code",
    "jwt",
    "key",
    "host_start_url",
    "host_token",
    "join_url",
    "meeting_url",
    "passcode",
    "password",
    "pwd",
    "secret",
    "signature",
    "sig",
    "start_token",
    "start_url",
    "token",
    "zoom_url",
    "zak",
}


class MeetingTimelineEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: MeetingEventKind
    source: str = MEETING_SOURCE
    command: str | None = Field(default=None, max_length=128)
    confidence: float | None = Field(default=None, ge=0, le=1)
    offset_ms: int | None = Field(default=None, ge=0)


def meeting_event_payload(
    kind: MeetingEventKind,
    *,
    meeting_url: str | None = None,
    source: str = MEETING_SOURCE,
) -> dict[str, object]:
    event = MeetingTimelineEvent(kind=kind, source=source, command=redact_meeting_url(meeting_url))
    return event.model_dump(exclude_none=True)


def redact_meeting_url(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlparse(value.strip())
    if not parsed.scheme:
        return _truncate(value.strip())

    redacted_query = []
    for key, item_value in parse_qsl(parsed.query, keep_blank_values=True):
        if key.lower() in SENSITIVE_QUERY_NAMES:
            redacted_query.append((key, "REDACTED"))
        else:
            redacted_query.append((key, item_value))
    redacted = parsed._replace(path=_redact_sensitive_path(parsed), query=urlencode(redacted_query), fragment="")
    return _truncate(urlunparse(redacted))


def _redact_sensitive_path(parsed: ParseResult) -> str:
    hostname = (parsed.hostname or "").lower()
    is_zoom_host = hostname in {"zoom.com", "zoom.us"} or hostname.endswith((".zoom.com", ".zoom.us"))
    if not is_zoom_host:
        return parsed.path

    redacted_parts = ["REDACTED" if part.isdigit() and len(part) >= 6 else part for part in parsed.path.split("/")]
    return "/".join(redacted_parts)


def contains_forbidden_meeting_artifact_fields(payload: object) -> bool:
    forbidden_keys = {
        "audio",
        "audio_path",
        "audio_url",
        "browser_profile",
        "cookie",
        "cookies",
        "local_storage",
        "meeting_password",
        "raw_audio",
        "text",
        "token",
        "transcript",
    }
    forbidden_fragments = ("data:audio", ".wav", ".mp3")
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in forbidden_keys and value not in {None, ""}:
                return True
            if contains_forbidden_meeting_artifact_fields(value):
                return True
        return False
    if isinstance(payload, list):
        return any(contains_forbidden_meeting_artifact_fields(value) for value in payload)
    if isinstance(payload, str):
        lowered = payload.lower()
        return any(fragment in lowered for fragment in forbidden_fragments)
    return False


def _truncate(value: str, max_len: int = 128) -> str:
    return value[:max_len]
