from devdefender_lab.evidence import dedupe_strings, is_safe_evidence_pointer


def test_dedupe_strings_preserves_order() -> None:
    assert dedupe_strings(["a", "b", "a", "", "c", "b"]) == ["a", "b", "c"]


def test_is_safe_evidence_pointer_enforces_pointer_grammar() -> None:
    valid = [
        "timeline://thread-1#event=0&kind=briefing_generated",
        "timeline://workspace#kind=feedback_plan_written&event=23",
        "slide://thread-1#page=3",
    ]
    invalid = [
        "timeline://thread-1#event=-1&kind=briefing_generated",
        "timeline://thread-1#event=0&kind=bad-kind",
        "timeline://thread-1#event=0&kind=briefing_generated&token=secret",
        "timeline://thread-1/path#event=0&kind=briefing_generated",
        "timeline://../thread#event=0&kind=briefing_generated",
        "slide://thread-1#page=0",
        "slide://thread-1#page=3&token=secret",
        "slide://thread-1/path#page=3",
        "transcript://thread-1#t=12.3",
        "audio://thread-1/file.wav",
        " timeline://thread-1#event=0&kind=briefing_generated",
    ]

    assert all(is_safe_evidence_pointer(pointer) for pointer in valid)
    assert not any(is_safe_evidence_pointer(pointer) for pointer in invalid)
