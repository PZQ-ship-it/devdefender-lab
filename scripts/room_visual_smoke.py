from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOM_URL = "http://127.0.0.1:8765"
DEFAULT_OUT_DIR = ROOT / "artifacts" / "visual"

REQUIRED_HTML_FRAGMENTS = (
    ("room-title", "DevDefender Room"),
    ("phase-subtitle", "Phase 2 local sync harness"),
    ("tool-tablist", 'role="tablist"'),
    ("control-tab", 'data-tool-tab="control"'),
    ("audio-tab", 'data-tool-tab="audio"'),
    ("logs-tab", 'data-tool-tab="logs"'),
    ("selected-tab-state", 'aria-selected="true"'),
    ("tabpanel", 'role="tabpanel"'),
    ("selected-state-update", "button.setAttribute('aria-selected', String(active))"),
    ("livekit-browser-client", "livekit browser client"),
    ("browser-interruption-detector", "browser interruption detector"),
    ("presenter-cue-player", "presenter cue player"),
    ("voice-command-harness", "voice command harness"),
    ("timeline-replay-log", "timeline replay log"),
    ("interruption-state-ui", "interruptionState"),
    ("interruption-renderer", "function renderInterruptionState(interruption)"),
    ("interruption-active-label", "Interruption active"),
    ("manual-interruption-button", "interruptButton"),
    ("manual-interruption-event", "manual-interrupt"),
    ("auto-livekit-test-hook", "auto_livekit"),
    ("auto-interruption-test-hook", "auto_interruption"),
    ("auto-presenter-cue-test-hook", "auto_presenter_cue"),
    ("browser-interruption-source", "browser-interruption-detector"),
    ("browser-presenter-cue-source", "browser-presenter-cue"),
)

FORBIDDEN_HTML_FRAGMENTS = (
    ("livekit-api-key-env", "LIVEKIT_API_KEY"),
    ("livekit-api-secret-env", "LIVEKIT_API_SECRET"),
    ("raw-api-secret-field", "api_secret"),
    ("raw-api-key-field", "api_key"),
)


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str


@dataclass(frozen=True)
class ScreenshotResult:
    name: str
    path: str
    width: int
    height: int
    bytes: int


def fetch_html(room_url: str, timeout: int = 10) -> str:
    request = Request(room_url, headers={"User-Agent": "devdefender-room-visual-smoke/1.0"})
    try:
        with urlopen(request, timeout=timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset)
    except (HTTPError, URLError, TimeoutError) as exc:
        raise RuntimeError(f"Room is not reachable at {room_url}: {exc}") from exc


def run_html_checks(html: str) -> list[CheckResult]:
    checks: list[CheckResult] = []
    for name, fragment in REQUIRED_HTML_FRAGMENTS:
        checks.append(CheckResult(name=name, ok=fragment in html, detail=f"requires {fragment!r}"))

    for name, fragment in FORBIDDEN_HTML_FRAGMENTS:
        checks.append(CheckResult(name=name, ok=fragment not in html, detail=f"forbids {fragment!r}"))

    hidden_panels = len(re.findall(r'<[^>]*data-tool-panel="[^"]+"[^>]*\shidden(?:\s|>|=)', html))
    checks.append(
        CheckResult(
            name="default-hidden-panels",
            ok=hidden_panels == 2,
            detail=f"expected 2 hidden tool panels, found {hidden_panels}",
        )
    )

    selected_tabs = html.count('aria-selected="true"')
    checks.append(
        CheckResult(
            name="single-selected-tab",
            ok=selected_tabs == 1,
            detail=f"expected 1 selected tab, found {selected_tabs}",
        )
    )

    stacked_tool_tabs = ".metrics, .tool-tabs { grid-template-columns: 1fr; }" in html
    checks.append(
        CheckResult(
            name="compact-narrow-tabs",
            ok=not stacked_tool_tabs,
            detail="tool tabs should not be forced into a one-column mobile stack",
        )
    )
    return checks


def find_browser(explicit_browser: str | None = None) -> str:
    candidates: list[str] = []
    if explicit_browser:
        candidates.append(explicit_browser)
    if os.getenv("DEVDEFENDER_BROWSER"):
        candidates.append(os.environ["DEVDEFENDER_BROWSER"])

    candidates.extend(
        [
            "msedge",
            "microsoft-edge",
            "google-chrome",
            "chrome",
            "chromium",
            "chromium-browser",
        ]
    )

    program_files = [os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles")]
    for base in program_files:
        if not base:
            continue
        candidates.extend(
            [
                str(Path(base) / "Microsoft" / "Edge" / "Application" / "msedge.exe"),
                str(Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe"),
            ]
        )

    for candidate in candidates:
        resolved = shutil.which(candidate) or candidate
        if Path(resolved).exists():
            return resolved

    raise RuntimeError("No Edge/Chrome/Chromium browser found. Pass --browser or set DEVDEFENDER_BROWSER.")


def capture_screenshot(browser: str, room_url: str, path: Path, width: int, height: int) -> ScreenshotResult:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()

    command = [
        browser,
        "--headless=new",
        "--disable-gpu",
        "--hide-scrollbars",
        f"--window-size={width},{height}",
        f"--screenshot={path}",
        room_url,
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        fallback = command.copy()
        fallback[1] = "--headless"
        result = subprocess.run(fallback, capture_output=True, text=True, timeout=60)

    if result.returncode != 0:
        stderr = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"Browser screenshot failed: {stderr[:600]}")
    if not path.exists():
        raise RuntimeError(f"Browser did not write screenshot: {path}")

    actual_width, actual_height = png_dimensions(path)
    byte_count = path.stat().st_size
    if byte_count < 2000:
        raise RuntimeError(f"Screenshot is unexpectedly small: {path} ({byte_count} bytes)")
    if actual_width <= 0 or actual_height <= 0:
        raise RuntimeError(f"Screenshot has invalid dimensions: {path}")

    return ScreenshotResult(
        name=path.stem,
        path=str(path),
        width=actual_width,
        height=actual_height,
        bytes=byte_count,
    )


def png_dimensions(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
        raise RuntimeError(f"Not a PNG screenshot: {path}")
    return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")


def run_smoke(room_url: str, out_dir: Path, browser: str | None = None) -> dict[str, object]:
    html = fetch_html(room_url)
    checks = run_html_checks(html)
    browser_path = find_browser(browser)
    screenshots = [
        capture_screenshot(browser_path, room_url, out_dir / "room-desktop-smoke.png", 1440, 960),
        capture_screenshot(browser_path, room_url, out_dir / "room-narrow-smoke.png", 390, 920),
    ]
    ok = all(check.ok for check in checks)
    report: dict[str, object] = {
        "ok": ok,
        "room_url": room_url,
        "browser": browser_path,
        "checks": [asdict(check) for check in checks],
        "screenshots": [asdict(item) for item in screenshots],
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "room_visual_smoke.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run browser-level visual smoke checks against a running DevDefender room.")
    parser.add_argument("--room-url", default=DEFAULT_ROOM_URL, help="Running DevDefender room URL.")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR, help="Directory for screenshots and report.")
    parser.add_argument("--browser", help="Path to Edge/Chrome/Chromium. Defaults to auto-discovery.")
    args = parser.parse_args()

    try:
        report = run_smoke(args.room_url.rstrip("/"), args.out_dir, args.browser)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 1

    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
