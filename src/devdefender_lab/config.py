from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field


class Settings(BaseModel):
    openai_api_key: str | None = Field(default=None)
    openai_base_url: str | None = Field(default=None)
    openai_model: str = Field(default="gpt-5.5")
    livekit_url: str | None = Field(default=None)
    livekit_api_key: str | None = Field(default=None)
    livekit_api_secret: str | None = Field(default=None)
    llm_mode: str = Field(default="openai")
    graph_backend: str = Field(default="embedded")
    agent_backend: str = Field(default="mock")
    agent_timeout_seconds: float = Field(default=120)
    artifact_dir: Path = Field(default=Path("artifacts"))
    slidev_port: int = Field(default=3030)
    room_host: str = Field(default="127.0.0.1")
    room_port: int = Field(default=8765)


def load_settings() -> Settings:
    load_dotenv()
    return Settings(
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        openai_base_url=os.getenv("OPENAI_BASE_URL"),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-5.5"),
        livekit_url=os.getenv("LIVEKIT_URL"),
        livekit_api_key=os.getenv("LIVEKIT_API_KEY"),
        livekit_api_secret=os.getenv("LIVEKIT_API_SECRET"),
        llm_mode=os.getenv("DEVDEFENDER_LLM_MODE", "openai"),
        graph_backend=os.getenv("DEVDEFENDER_GRAPH_BACKEND", "embedded"),
        agent_backend=os.getenv("DEVDEFENDER_AGENT_BACKEND", "mock"),
        agent_timeout_seconds=float(os.getenv("DEVDEFENDER_AGENT_TIMEOUT_SECONDS", "120")),
        artifact_dir=Path(os.getenv("DEVDEFENDER_ARTIFACT_DIR", "artifacts")),
        slidev_port=int(os.getenv("DEVDEFENDER_SLIDEV_PORT", "3030")),
        room_host=os.getenv("DEVDEFENDER_ROOM_HOST", "127.0.0.1"),
        room_port=int(os.getenv("DEVDEFENDER_ROOM_PORT", "8765")),
    )
