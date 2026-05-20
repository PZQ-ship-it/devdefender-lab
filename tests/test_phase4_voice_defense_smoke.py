import json
from pathlib import Path

from scripts.phase4_voice_defense_smoke import build_report, browser_auto_voice_defense_url, write_report


def test_phase4_voice_defense_report_requires_tts_interruption_resume_and_slide_mapping() -> None:
    baseline_timeline = {"events": [{"kind": "noise", "source": "existing"}]}
    baseline_slides = {"current_slide_index": 2, "events": []}
    timeline = {
        "interruption": {
            "active": False,
            "event_count": 1,
            "source": "browser-voice-interruption",
            "confidence": 0.96,
            "offset_ms": 120,
        },
        "events": [
            *baseline_timeline["events"],
            {"kind": "speech_started", "source": "browser-voice-defense", "command": "opening"},
            {"kind": "tts_word", "source": "browser-voice-defense", "token": "next", "offset_ms": 220},
            {"kind": "speech_started", "source": "browser-voice-interruption", "command": "reviewer-question"},
            {"kind": "speech_interrupted", "source": "browser-voice-interruption", "confidence": 0.96},
            {"kind": "speech_started", "source": "browser-voice-defense", "command": "answer"},
            {"kind": "speech_started", "source": "browser-voice-defense", "command": "resume"},
            {"kind": "tts_word", "source": "browser-voice-defense", "token": "next", "offset_ms": 260},
        ],
    }
    slides = {
        "current_slide_index": 4,
        "events": [
            {"action": "next", "slide_index": 3, "source": "timeline:browser-voice-defense"},
            {"action": "next", "slide_index": 4, "source": "timeline:browser-voice-defense"},
        ],
    }

    report = build_report(
        "browser",
        "http://room.test",
        "http://room.test/voice-defense-test?auto_voice_defense=1",
        baseline_timeline,
        baseline_slides,
        timeline,
        slides,
    )

    assert report["ok"] is True
    assert report["checks"]["opening_speech_started"] is True
    assert report["checks"]["answer_speech_started"] is True
    assert report["checks"]["resume_speech_started"] is True
    assert report["checks"]["two_tts_anchors_recorded"] is True
    assert report["checks"]["speech_interrupted_recorded"] is True
    assert report["checks"]["interruption_handled_after_answer"] is True
    assert report["checks"]["slide_advanced_twice"] is True


def test_phase4_voice_defense_report_rejects_raw_audio_or_transcript_fields() -> None:
    report = build_report(
        "browser",
        "http://room.test",
        "http://room.test/voice-defense-test?auto_voice_defense=1",
        {"events": []},
        {"current_slide_index": 1, "events": []},
        {
            "interruption": {"active": False, "source": "browser-voice-interruption"},
            "events": [
                {"kind": "speech_started", "source": "browser-voice-defense", "command": "opening"},
                {"kind": "tts_word", "source": "browser-voice-defense", "token": "next", "transcript": "raw"},
                {"kind": "speech_interrupted", "source": "browser-voice-interruption"},
            ],
        },
        {"current_slide_index": 2, "events": [{"source": "timeline:browser-voice-defense"}]},
    )

    assert report["ok"] is False
    assert report["checks"]["no_audio_or_transcript_fields"] is False


def test_phase4_voice_defense_url_targets_test_page() -> None:
    assert (
        browser_auto_voice_defense_url("http://room.test/root?x=1")
        == "http://room.test/voice-defense-test?x=1&auto_voice_defense=1"
    )


def test_phase4_voice_defense_writes_report(tmp_path: Path) -> None:
    report = {"ok": True, "checks": {"voice_defense": True}}
    out = tmp_path / "nested" / "phase4_voice_defense.json"

    write_report(report, out)

    assert json.loads(out.read_text(encoding="utf-8")) == report
