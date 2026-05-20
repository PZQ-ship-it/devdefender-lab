from __future__ import annotations

import re
from collections.abc import Iterable
from urllib.parse import parse_qs, urlparse


SAFE_THREAD_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
SAFE_KIND_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


def dedupe_strings(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value or value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def is_safe_evidence_pointer(pointer: str) -> bool:
    if not isinstance(pointer, str):
        return False
    if pointer != pointer.strip():
        return False
    lowered = pointer.lower()
    forbidden_fragments = (
        "data:audio",
        ".wav",
        ".mp3",
        "\\",
        "..",
        "transcript://",
        "audio://",
        "token=",
        "api_key=",
        "api_secret=",
    )
    if any(fragment in lowered for fragment in forbidden_fragments):
        return False
    parsed = urlparse(pointer)
    if parsed.scheme == "timeline":
        return _is_safe_timeline_pointer(parsed)
    if parsed.scheme == "slide":
        return _is_safe_slide_pointer(parsed)
    return False


def _is_safe_timeline_pointer(parsed) -> bool:
    if not _is_safe_pointer_host(parsed.netloc):
        return False
    if parsed.path not in {"", "/"} or parsed.params or parsed.query:
        return False
    try:
        fragment = parse_qs(parsed.fragment, keep_blank_values=True, strict_parsing=True)
    except ValueError:
        return False
    if set(fragment) != {"event", "kind"}:
        return False
    event_values = fragment["event"]
    kind_values = fragment["kind"]
    if len(event_values) != 1 or len(kind_values) != 1:
        return False
    if not event_values[0].isdigit():
        return False
    if int(event_values[0]) < 0:
        return False
    return bool(SAFE_KIND_RE.fullmatch(kind_values[0]))


def _is_safe_slide_pointer(parsed) -> bool:
    if not _is_safe_pointer_host(parsed.netloc):
        return False
    if parsed.path not in {"", "/"} or parsed.params or parsed.query:
        return False
    try:
        fragment = parse_qs(parsed.fragment, keep_blank_values=True, strict_parsing=True)
    except ValueError:
        return False
    if set(fragment) != {"page"}:
        return False
    page_values = fragment["page"]
    if len(page_values) != 1 or not page_values[0].isdigit():
        return False
    return int(page_values[0]) >= 1


def _is_safe_pointer_host(value: str) -> bool:
    return bool(SAFE_THREAD_RE.fullmatch(value))
