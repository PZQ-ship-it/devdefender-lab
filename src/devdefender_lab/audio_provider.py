from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Iterable, Protocol

from pydantic import BaseModel, ConfigDict, Field

from devdefender_lab.config import Settings
from devdefender_lab.timeline import TimelineEventKind


class AudioTimelineEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: TimelineEventKind
    source: str = "mock-audio"
    token: str | None = Field(default=None, max_length=128)
    command: str | None = Field(default=None, max_length=128)
    slide_index: int | None = Field(default=None, ge=1)
    confidence: float | None = Field(default=None, ge=0, le=1)
    offset_ms: int | None = Field(default=None, ge=0)


class AudioProvider(Protocol):
    backend: str

    def start_session(self) -> None:
        ...

    def stop_session(self) -> None:
        ...

    def emit_timeline_event(self) -> AudioTimelineEvent | None:
        ...


class MockAudioProvider:
    backend = "mock-audio"

    def __init__(self, script: Iterable[AudioTimelineEvent] | None = None) -> None:
        self.script = list(script or default_mock_audio_script())
        self._index = 0
        self._running = False

    def start_session(self) -> None:
        self._index = 0
        self._running = True

    def stop_session(self) -> None:
        self._running = False

    def emit_timeline_event(self) -> AudioTimelineEvent | None:
        if not self._running:
            raise RuntimeError("Audio provider session is not running.")
        if self._index >= len(self.script):
            return None
        event = self.script[self._index]
        self._index += 1
        return event


def default_mock_audio_script() -> list[AudioTimelineEvent]:
    return [
        AudioTimelineEvent(kind="speech_started", source="mock-audio", confidence=0.98, offset_ms=0),
        AudioTimelineEvent(kind="noise", source="mock-audio", confidence=0.87, offset_ms=420),
        AudioTimelineEvent(kind="tts_word", source="mock-audio", token="next", confidence=0.99, offset_ms=1250),
        AudioTimelineEvent(kind="speech_interrupted", source="mock-audio", confidence=0.93, offset_ms=2200),
    ]


def audio_event_payload(event: AudioTimelineEvent) -> dict[str, object]:
    return event.model_dump(exclude_none=True)


class LiveKitTokenReport(BaseModel):
    backend: str = "livekit"
    room_name: str
    identity: str
    token_length: int
    room_check: str = "not_run"
    room_count: int | None = None


class LiveKitBrowserToken(BaseModel):
    url: str
    room_name: str
    identity: str
    token: str
    token_length: int


@dataclass
class LiveKitAudioProvider:
    settings: Settings
    room_name: str = "devdefender-phase2"
    identity: str = "devdefender-local"
    check_room: bool = False

    backend: str = "livekit"

    def start_session(self) -> None:
        self._require_credentials()

    def stop_session(self) -> None:
        return

    def emit_timeline_event(self) -> AudioTimelineEvent | None:
        return None

    def create_join_token(self) -> str:
        self._require_credentials()
        api = _livekit_api_module()
        grants = api.VideoGrants(room_join=True, room=self.room_name, can_publish=True, can_subscribe=True)
        return (
            api.AccessToken(self.settings.livekit_api_key, self.settings.livekit_api_secret)
            .with_identity(self.identity)
            .with_name(self.identity)
            .with_grants(grants)
            .to_jwt()
        )

    def create_browser_token(self) -> LiveKitBrowserToken:
        token = self.create_join_token()
        return LiveKitBrowserToken(
            url=str(self.settings.livekit_url),
            room_name=self.room_name,
            identity=self.identity,
            token=token,
            token_length=len(token),
        )

    def smoke(self) -> LiveKitTokenReport:
        token = self.create_join_token()
        report = LiveKitTokenReport(
            room_name=self.room_name,
            identity=self.identity,
            token_length=len(token),
        )
        if self.check_room:
            room_count = asyncio.run(self._list_room_count())
            report.room_check = "ok"
            report.room_count = room_count
        return report

    async def _list_room_count(self) -> int:
        self._require_credentials()
        api = _livekit_api_module()
        client = api.LiveKitAPI(
            self.settings.livekit_url,
            self.settings.livekit_api_key,
            self.settings.livekit_api_secret,
        )
        try:
            response = await client.room.list_rooms(api.ListRoomsRequest())
        finally:
            await client.aclose()
        return len(getattr(response, "rooms", []))

    def _require_credentials(self) -> None:
        missing = []
        if not self.settings.livekit_url:
            missing.append("LIVEKIT_URL")
        if not self.settings.livekit_api_key:
            missing.append("LIVEKIT_API_KEY")
        if not self.settings.livekit_api_secret:
            missing.append("LIVEKIT_API_SECRET")
        if missing:
            raise RuntimeError(f"Missing LiveKit credentials: {', '.join(missing)}")


def _livekit_api_module():
    try:
        from livekit import api
    except ImportError as exc:
        raise RuntimeError("livekit-api is required for LiveKitAudioProvider.") from exc
    return api
