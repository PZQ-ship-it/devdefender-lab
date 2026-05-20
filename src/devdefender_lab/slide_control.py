from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


SlideAction = Literal["next", "prev", "goto"]


class SlideControlEvent(BaseModel):
    timestamp: str
    thread_id: str
    action: SlideAction
    slide_index: int = Field(ge=1)
    source: str = "manual"


class SlideEventLog:
    def __init__(self, path: Path, thread_id: str, initial_slide_index: int = 1) -> None:
        self.path = path
        self.thread_id = thread_id
        self.initial_slide_index = initial_slide_index
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, action: str, slide_index: int | None = None, source: str = "manual") -> SlideControlEvent:
        with self._lock:
            next_index = self._resolve_slide_index(action, slide_index)
            event = SlideControlEvent(
                timestamp=datetime.now(timezone.utc).isoformat(),
                thread_id=self.thread_id,
                action=action,
                slide_index=next_index,
                source=source,
            )
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(event.model_dump_json() + "\n")
            return event

    def events(self) -> list[SlideControlEvent]:
        return replay_slide_events(self.path, thread_id=self.thread_id)

    def current_slide_index(self) -> int:
        events = self.events()
        if not events:
            return self.initial_slide_index
        return events[-1].slide_index

    def _resolve_slide_index(self, action: str, slide_index: int | None) -> int:
        current = self.current_slide_index()
        if action == "next":
            return current + 1
        if action == "prev":
            return max(1, current - 1)
        if action == "goto":
            if slide_index is None or slide_index < 1:
                raise ValueError("goto requires slide_index >= 1")
            return slide_index
        raise ValueError(f"Unsupported slide action: {action}")


def replay_slide_events(path: Path, thread_id: str | None = None) -> list[SlideControlEvent]:
    if not path.exists():
        return []
    events: list[SlideControlEvent] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        event = SlideControlEvent.model_validate(json.loads(line))
        if thread_id is None or event.thread_id == thread_id:
            events.append(event)
    return events
