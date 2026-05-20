from scripts.artifact_secret_smoke import build_report, load_secret_values


def test_artifact_secret_smoke_detects_raw_env_secret_without_echoing_value(tmp_path) -> None:
    env = tmp_path / ".env"
    env.write_text("LIVEKIT_API_SECRET=super-secret-value\n", encoding="utf-8")
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "report.json").write_text('{"token":"super-secret-value"}', encoding="utf-8")

    secrets = load_secret_values(env, ("LIVEKIT_API_SECRET",))
    report = build_report(artifacts, env, ("LIVEKIT_API_SECRET",), secrets)

    assert report["ok"] is False
    assert report["findings"] == [
        {
            "secret_name": "LIVEKIT_API_SECRET",
            "path": str(artifacts / "report.json"),
            "relative_path": "report.json",
        }
    ]
    assert "super-secret-value" not in str(report)


def test_artifact_secret_smoke_ignores_short_or_placeholder_values(tmp_path) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "OPENAI_API_KEY=short\nLIVEKIT_API_SECRET=placeholder-secret\n",
        encoding="utf-8",
    )

    assert load_secret_values(env, ("OPENAI_API_KEY", "LIVEKIT_API_SECRET")) == {}


def test_artifact_secret_smoke_skips_binary_files_and_workspaces(tmp_path) -> None:
    env = tmp_path / ".env"
    env.write_text("OPENAI_API_KEY=real-secret-value\n", encoding="utf-8")
    artifacts = tmp_path / "artifacts"
    (artifacts / "visual").mkdir(parents=True)
    (artifacts / "visual" / "shot.png").write_bytes(b"\x89PNG\r\n\x1a\nreal-secret-value")
    (artifacts / "workspaces" / "repo").mkdir(parents=True)
    (artifacts / "workspaces" / "repo" / "trace.txt").write_text("real-secret-value", encoding="utf-8")
    (artifacts / "safe.json").write_text('{"ok": true}', encoding="utf-8")

    report = build_report(artifacts, env, ("OPENAI_API_KEY",), load_secret_values(env, ("OPENAI_API_KEY",)))

    assert report["ok"] is True
    assert report["findings"] == []
    assert report["scanned_file_count"] == 1
