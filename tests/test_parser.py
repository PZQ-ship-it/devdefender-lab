from pathlib import Path

from devdefender_lab.parser import parse_python_repo


def test_parse_sample_repo_finds_functions_and_calls() -> None:
    payload = parse_python_repo(Path("sample_repo"))
    names = {node.name for node in payload.nodes}
    calls = {(edge.source, edge.target, edge.kind) for edge in payload.edges}

    assert "capture_payment" in names
    assert "authorize_payment" in names
    assert "validate_payment" in names
    assert any("capture_payment" in source and "authorize_payment" in target and kind == "CALLS" for source, target, kind in calls)
