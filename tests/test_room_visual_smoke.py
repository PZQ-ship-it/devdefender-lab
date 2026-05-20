from pathlib import Path

from scripts.room_visual_smoke import png_dimensions, run_html_checks


def test_room_visual_smoke_accepts_expected_room_html() -> None:
    html = """
    <h1>DevDefender Room</h1>
    <span>Phase 2 local sync harness</span>
    <nav role="tablist">
      <button data-tool-tab="control" aria-selected="true">Control</button>
      <button data-tool-tab="audio" aria-selected="false">Audio</button>
      <button data-tool-tab="logs" aria-selected="false">Logs</button>
    </nav>
    <section data-tool-panel="control" role="tabpanel"></section>
    <section data-tool-panel="audio" role="tabpanel" hidden></section>
    <section data-tool-panel="logs" role="tabpanel" hidden></section>
    <script>
      button.setAttribute('aria-selected', String(active));
    </script>
    <div>livekit browser client</div>
    <div>browser interruption detector</div>
    <div>presenter cue player</div>
    <div>voice command harness</div>
    <div>timeline replay log</div>
    <div id="interruptionState"></div>
    <button id="interruptButton">Interrupt</button>
    <div>auto_livekit</div>
    <div>auto_interruption</div>
    <div>auto_presenter_cue</div>
    <script>
      const source = 'manual-interrupt';
      const detectorSource = 'browser-interruption-detector';
      const cueSource = 'browser-presenter-cue';
      function renderInterruptionState(interruption) {
        const status = interruption.active ? 'Interruption active' : 'Last interruption handled';
      }
    </script>
    """

    checks = run_html_checks(html)

    assert all(check.ok for check in checks)


def test_room_visual_smoke_rejects_secret_or_stacked_mobile_tabs() -> None:
    html = """
    DevDefender Room
    Phase 2 local sync harness
    role="tablist"
    data-tool-tab="control"
    data-tool-tab="audio"
    data-tool-tab="logs"
    aria-selected="true"
    role="tabpanel"
    button.setAttribute('aria-selected', String(active))
    livekit browser client
    browser interruption detector
    presenter cue player
    voice command harness
    timeline replay log
    interruptionState
    function renderInterruptionState(interruption)
    Interruption active
    interruptButton
    manual-interrupt
    auto_livekit
    auto_interruption
    auto_presenter_cue
    browser-interruption-detector
    browser-presenter-cue
    data-tool-panel="audio" hidden
    data-tool-panel="logs" hidden
    .metrics, .tool-tabs { grid-template-columns: 1fr; }
    LIVEKIT_API_SECRET
    """

    failed = {check.name for check in run_html_checks(html) if not check.ok}

    assert "livekit-api-secret-env" in failed
    assert "compact-narrow-tabs" in failed


def test_png_dimensions_reads_browser_screenshot_header(tmp_path: Path) -> None:
    png = tmp_path / "tiny.png"
    png.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR"
        + (390).to_bytes(4, "big")
        + (920).to_bytes(4, "big")
        + b"\x08\x02\x00\x00\x00"
    )

    assert png_dimensions(png) == (390, 920)
