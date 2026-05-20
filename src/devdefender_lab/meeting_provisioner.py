from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import uuid5, NAMESPACE_URL

from pydantic import BaseModel, ConfigDict, Field, field_validator

from devdefender_lab.config import Settings, load_settings
from devdefender_lab.meeting import contains_forbidden_meeting_artifact_fields, redact_meeting_url


MeetingProviderName = Literal["mock", "livekit"]
PROVISIONER_SOURCE = "mock-meeting-provisioner"


class ProvisionedMeeting(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: MeetingProviderName
    meeting_id: str = Field(min_length=1, max_length=80)
    topic: str = Field(min_length=1, max_length=120)
    join_url: str = Field(min_length=1, max_length=512)
    host_start_url: str = Field(min_length=1, max_length=512)
    expires_at: str
    secret_ref: str = Field(min_length=1, max_length=128)

    @field_validator("expires_at")
    @classmethod
    def validate_expires_at(cls, value: str) -> str:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return value


class SafeProvisionedMeeting(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: MeetingProviderName
    meeting_id: str
    topic: str
    join_url: str | None
    expires_at: str
    secret_ref: str


class ProvisioningResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    provider: MeetingProviderName
    meeting_id: str | None = None
    command: str | None = None
    error: str | None = None


class MockMeetingProvisioner:
    provider: MeetingProviderName = "mock"

    def create_meeting(
        self,
        *,
        topic: str,
        duration_minutes: int = 30,
        room_thread_id: str = "local-thread",
    ) -> ProvisionedMeeting:
        meeting_id = _stable_meeting_id(room_thread_id, topic)
        expires_at = (datetime.now(timezone.utc) + timedelta(minutes=duration_minutes)).replace(microsecond=0)
        join_url = f"https://meeting.local/provisioned/{meeting_id}?join_url=visible&token=mock-join-token"
        host_start_url = f"https://meeting.local/provisioned/{meeting_id}/start?start_token=mock-host-token&password=mock-password"
        return ProvisionedMeeting(
            provider=self.provider,
            meeting_id=meeting_id,
            topic=topic,
            join_url=join_url,
            host_start_url=host_start_url,
            expires_at=expires_at.isoformat(),
            secret_ref=f"env:DEVDEFENDER_MEETING_HOST_START_URL:{meeting_id}",
        )

    def teardown_meeting(self, meeting: ProvisionedMeeting) -> ProvisioningResult:
        return ProvisioningResult(
            ok=True,
            provider=self.provider,
            meeting_id=meeting.meeting_id,
            command="mock-meeting-torn-down",
        )


class LiveKitMeetingProvisioner:
    provider: MeetingProviderName = "livekit"

    def __init__(self, settings: Settings | None = None, create_room: bool = True) -> None:
        self.settings = settings or load_settings()
        self.create_room = create_room

    def create_meeting(
        self,
        *,
        topic: str,
        duration_minutes: int = 30,
        room_thread_id: str = "local-thread",
    ) -> ProvisionedMeeting:
        self._require_credentials()
        meeting_id = f"devdefender-{_stable_meeting_id(room_thread_id, topic)}"
        expires_at = (datetime.now(timezone.utc) + timedelta(minutes=duration_minutes)).replace(microsecond=0)
        if self.create_room:
            asyncio.run(self._create_livekit_room(meeting_id, topic, duration_minutes, room_thread_id))
        return ProvisionedMeeting(
            provider=self.provider,
            meeting_id=meeting_id,
            topic=topic,
            join_url=f"livekit://room/{meeting_id}",
            host_start_url=f"livekit://room/{meeting_id}/host",
            expires_at=expires_at.isoformat(),
            secret_ref=f"env:LIVEKIT_API_SECRET:{meeting_id}",
        )

    def teardown_meeting(self, meeting: ProvisionedMeeting) -> ProvisioningResult:
        if not self.create_room:
            return ProvisioningResult(
                ok=True,
                provider=self.provider,
                meeting_id=meeting.meeting_id,
                command="livekit-room-scope-released",
            )
        try:
            asyncio.run(self._delete_livekit_room(meeting.meeting_id))
        except Exception as exc:
            return ProvisioningResult(
                ok=False,
                provider=self.provider,
                meeting_id=meeting.meeting_id,
                error=_safe_error(exc),
            )
        return ProvisioningResult(
            ok=True,
            provider=self.provider,
            meeting_id=meeting.meeting_id,
            command="livekit-room-deleted",
        )

    async def _create_livekit_room(
        self,
        meeting_id: str,
        topic: str,
        duration_minutes: int,
        room_thread_id: str,
    ) -> None:
        api = _livekit_api_module()
        client = api.LiveKitAPI(
            self.settings.livekit_url,
            self.settings.livekit_api_key,
            self.settings.livekit_api_secret,
        )
        try:
            metadata = json.dumps(
                {"topic": topic, "thread_id": room_thread_id, "provider": self.provider},
                ensure_ascii=False,
            )
            request = api.CreateRoomRequest(
                name=meeting_id,
                empty_timeout=max(60, int(duration_minutes) * 60),
                max_participants=8,
                metadata=metadata,
            )
            await client.room.create_room(request)
        finally:
            await client.aclose()

    async def _delete_livekit_room(self, meeting_id: str) -> None:
        api = _livekit_api_module()
        client = api.LiveKitAPI(
            self.settings.livekit_url,
            self.settings.livekit_api_key,
            self.settings.livekit_api_secret,
        )
        try:
            await client.room.delete_room(api.DeleteRoomRequest(room=meeting_id))
        finally:
            await client.aclose()

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


def create_provisioner(
    provider: str,
    *,
    settings: Settings | None = None,
    create_livekit_room: bool = True,
) -> MockMeetingProvisioner | LiveKitMeetingProvisioner:
    normalized = provider.strip().lower()
    if normalized == "mock":
        return MockMeetingProvisioner()
    if normalized == "livekit":
        return LiveKitMeetingProvisioner(settings=settings, create_room=create_livekit_room)
    raise ValueError(f"Unsupported meeting provider: {provider}")


def safe_provisioned_meeting(meeting: ProvisionedMeeting) -> dict[str, object]:
    safe = SafeProvisionedMeeting(
        provider=meeting.provider,
        meeting_id=meeting.meeting_id,
        topic=meeting.topic,
        join_url=redact_meeting_url(meeting.join_url),
        expires_at=meeting.expires_at,
        secret_ref=meeting.secret_ref,
    )
    return safe.model_dump(exclude_none=True)


def meeting_created_event_payload(meeting: ProvisionedMeeting) -> dict[str, object]:
    return {
        "kind": "meeting_created",
        "source": provisioner_source(meeting.provider),
        "command": redact_meeting_url(meeting.join_url),
        "confidence": 1,
        "offset_ms": 0,
    }


def meeting_provision_failed_event_payload(provider: str, error: str) -> dict[str, object]:
    return {
        "kind": "meeting_provision_failed",
        "source": provisioner_source(provider),
        "command": error[:128],
    }


def provisioner_source(provider: str) -> str:
    return f"{provider.strip().lower() or 'unknown'}-meeting-provisioner"


def contains_forbidden_provisioning_artifact_fields(payload: object) -> bool:
    forbidden_keys = {
        "access_token",
        "host_start_url",
        "host_token",
        "meeting_password",
        "oauth_token",
        "password",
        "start_token",
        "start_url",
        "token",
        "zak",
    }
    forbidden_fragments = (
        "mock-host-token",
        "mock-join-token",
        "mock-password",
        "livekit_api_key",
        "livekit_api_secret",
        "start_token=",
        "host_start_url",
        "password=",
    )
    if contains_forbidden_meeting_artifact_fields(payload):
        return True
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key == "secret_ref":
                if not isinstance(value, str) or not value.startswith(("env:", "vault:", "secret:")):
                    return True
                continue
            if key in forbidden_keys and value not in {None, ""}:
                return True
            if contains_forbidden_provisioning_artifact_fields(value):
                return True
        return False
    if isinstance(payload, list):
        return any(contains_forbidden_provisioning_artifact_fields(value) for value in payload)
    if isinstance(payload, str):
        lowered = payload.lower()
        return any(fragment in lowered for fragment in forbidden_fragments)
    return False


def _stable_meeting_id(room_thread_id: str, topic: str) -> str:
    return uuid5(NAMESPACE_URL, f"{room_thread_id}:{topic}").hex[:12]


def _safe_error(exc: Exception) -> str:
    return str(exc).replace("\n", " ")[:128]


def _livekit_api_module():
    try:
        from livekit import api
    except ImportError as exc:
        raise RuntimeError("livekit-api is required for LiveKitMeetingProvisioner.") from exc
    return api
