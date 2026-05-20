import json
from pathlib import Path

from scripts.zoom_web_discovery_smoke import build_report, local_zoom_discovery_test_url, write_report


def test_zoom_web_discovery_report_requires_prejoin_and_cleanup() -> None:
    before = [{"kind": "manual_voice_command", "source": "existing"}]
    timeline = {
        "events": [
            *before,
            {
                "kind": "meeting_join_started",
                "source": "zoom-web-discovery",
                "command": "https://zoom.us/wc/join/REDACTED?pwd=REDACTED",
            },
            {
                "kind": "meeting_joined",
                "source": "zoom-web-discovery",
                "command": "zoom-prejoin-detected",
            },
            {
                "kind": "meeting_left",
                "source": "zoom-web-discovery",
                "command": "zoom-discovery-complete",
            },
        ]
    }

    report = build_report(
        browser_path="browser",
        room_url="http://room.test",
        target_url=(
            "http://room.test/zoom-discovery-test?auto_zoom_discovery=1"
            "&zoom_url=https%3A%2F%2Fzoom.us%2Fwc%2Fjoin%2F123456789%3Fpwd%3Dsecret"
        ),
        before_events=before,
        timeline=timeline,
        browser_return_code=0,
        used_terminate=False,
        used_kill=False,
        profile_dir=None,
    )

    assert report["ok"] is True
    assert report["new_event_kinds"] == ["meeting_join_started", "meeting_joined", "meeting_left"]
    assert report["checks"]["zoom_prejoin_detected"] is True
    assert report["checks"]["target_url_redacted"] is True
    assert report["checks"]["join_command_redacted"] is True
    assert report["target_url"].endswith("zoom_url=REDACTED")


def test_zoom_web_discovery_report_rejects_errors_and_forbidden_fields() -> None:
    report = build_report(
        browser_path="browser",
        room_url="http://room.test",
        target_url="http://room.test/zoom-discovery-test?auto_zoom_discovery=1",
        before_events=[],
        timeline={
            "events": [
                {"kind": "meeting_join_started", "source": "zoom-web-discovery"},
                {"kind": "meeting_joined", "source": "manual", "command": "zoom-prejoin-detected", "cookies": "secret"},
                {"kind": "meeting_error", "source": "zoom-web-discovery"},
                {"kind": "meeting_left", "source": "zoom-web-discovery"},
            ]
        },
        browser_return_code=0,
        used_terminate=False,
        used_kill=False,
        profile_dir=None,
    )

    assert report["ok"] is False
    assert report["checks"]["zoom_discovery_source_used"] is False
    assert report["checks"]["no_meeting_error"] is False
    assert report["checks"]["no_forbidden_artifact_fields"] is False


def test_zoom_discovery_url_targets_local_page_and_preserves_probe_input() -> None:
    url = local_zoom_discovery_test_url("http://room.test/root?x=1", "https://zoom.us/wc/join/123456789?pwd=secret")

    assert url.startswith("http://room.test/zoom-discovery-test?")
    assert "x=1" in url
    assert "auto_zoom_discovery=1" in url
    assert "zoom_url=" in url


def test_zoom_web_discovery_writes_report(tmp_path: Path) -> None:
    report = {"ok": True, "checks": {"zoom_prejoin_detected": True}}
    out = tmp_path / "nested" / "zoom_web_discovery_smoke.json"

    write_report(report, out)

    assert json.loads(out.read_text(encoding="utf-8")) == report
