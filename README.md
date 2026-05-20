# DevDefender Lab

Phase 1 integration lab for an AI code defense workflow. This repo intentionally keeps the surface small: parse a sample repo, persist a local code graph, generate a Slidev deck, call OpenAI for a defense answer, and extract a GitHub-Issue-shaped JSON payload from typed feedback.

## Local Setup

```powershell
conda env create -f environment.yml
conda activate devdefender-lab
npm install
Copy-Item .env.example .env
```

Set `OPENAI_API_KEY` in `.env` or in your shell. `OPENAI_MODEL` defaults to `gpt-5.5`.

For an OpenAI-compatible provider such as SiliconFlow, set:

```powershell
OPENAI_BASE_URL=https://api.siliconflow.cn/v1
OPENAI_MODEL=Pro/moonshotai/Kimi-K2.6
```

When `OPENAI_BASE_URL` is set, the lab uses the Chat Completions-compatible API. Without it, the lab uses OpenAI's Responses API.

## Phase 1 Defense Room

Run the local text-based defense MVP:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe -m devdefender_lab.room --repo sample_repo
```

For a credential-free demo:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe -m devdefender_lab.room --repo sample_repo --mock
```

Open `http://127.0.0.1:8765`. The room starts Slidev on `http://127.0.0.1:3030`, shows the generated deck in an iframe, waits at a LangGraph `interrupt()`, then resumes when typed reviewer feedback is submitted. After the Issue is extracted, the local TDAD refiner sends an Agent Task Envelope through the Mock Agent Gateway, validates the returned patch/test artifacts, and records the result.

Generated artifacts land in `artifacts/`:

- `graph.json`
- `deck/slides.md`
- `session.json`
- `state.json`
- `defense.md`
- `issue.json`
- `refinement.json`
- `agent_task.json`
- `patch.diff`
- `test_report.json`
- `agent_trace.json`
- `slidev-url.txt`

## Code Agent Gateway

Phase 1 keeps code agents behind a Gateway contract. The default room path still uses `MockAgentAdapter` so the full TDAD loop is deterministic and safe for tests.

OpenClaude is wired in as a CLI subprocess adapter. Plan-only mode verifies that the model can inspect the Agent Task Envelope and return structured JSON:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\openclaude_plan_smoke.py
```

The adapter launches `npx -y @gitlawb/openclaude` with `--print`, `--bare`, `--no-session-persistence`, `--provider openai`, a read-only tool set (`Read,Glob,Grep,LS`), and a strict JSON schema for the plan. Permission prompts are bypassed only inside that read-only tool set. It passes `OPENAI_API_KEY`, `OPENAI_BASE_URL`, and `OPENAI_MODEL` from `.env`, but it does not write them into artifacts. Plan output is stored as:

- `artifacts/openclaude/agent_plan.json`
- `artifacts/openclaude/agent_trace.json`

Patch mode runs OpenClaude in a disposable workspace copy and lets it use file edit tools only inside that workspace. Shell execution remains disabled; the Gateway runs the configured tests after the agent exits and then validates changed paths:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\openclaude_patch_smoke.py
```

Patch output is stored as:

- `artifacts/openclaude-patch/patch.diff`
- `artifacts/openclaude-patch/test_report.json`
- `artifacts/openclaude-patch/agent_trace.json`

Replay any Gateway trace without calling an LLM or code agent:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\replay_agent_trace.py .\artifacts\openclaude-patch\agent_trace.json
```

To use OpenClaude patch mode in the Phase 1 workflow instead of the mock adapter:

```powershell
$env:DEVDEFENDER_AGENT_BACKEND="openclaude-cli"
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe -m devdefender_lab.smoke --mode e2e
```

## Phase 1 Acceptance

Deterministic local acceptance:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe -m pytest tests
$env:DEVDEFENDER_LLM_MODE="mock"
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe -m devdefender_lab.smoke --mode e2e
```

Gateway safety and replay acceptance:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe -m pytest tests/test_agent_gateway.py
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\replay_agent_trace.py .\artifacts\agent_trace.json
```

Real OpenClaude CLI acceptance:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\openclaude_plan_smoke.py
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\openclaude_patch_smoke.py --timeout 300
```

Phase 1 is considered locally closed when deterministic local acceptance and Gateway safety/replay acceptance pass. Real OpenClaude CLI acceptance is the provider-backed integration check; if it fails, inspect `agent_trace.json`, `patch.diff`, and `test_report.json` before changing Gateway policy.

## Phase 2 Local Sync Room

Phase 2 starts with a minimal local split-screen sync room before adding meeting automation. The existing room now includes a Slidev iframe, manual `prev/next/goto` controls, a WebSocket broadcast channel, and a replayable event log:

- HTTP control endpoint: `POST /api/slide-control`
- HTTP replay endpoint: `GET /api/slide-events`
- WebSocket channel: `/ws/slides`
- Event log artifact: `artifacts/slide_events.jsonl`

The room also includes a structured voice/timeline adapter without storing raw audio or full transcripts:

- Timeline ingest endpoint: `POST /api/timeline-event`
- Timeline replay endpoint: `GET /api/timeline-events`
- Timeline artifact: `artifacts/timeline_events.jsonl`
- Supported event kinds: `speech_started`, `speech_interrupted`, `tts_word`, `manual_voice_command`, `noise`, `livekit_connected`, `livekit_disconnected`, `livekit_error`, `audio_track_published`
- Interruption state is derived from replayed `speech_interrupted` events and returned as `timeline.interruption`; it records the latest source, confidence, offset, count, and whether the interruption is still active.
- The local control panel includes a manual `Interrupt` button that emits `speech_interrupted` for debugging the replay/UI contract before a real microphone interruption model is connected.
- The browser audio panel includes a minimal Web Audio RMS interruption detector. It emits only structured `speech_started` and `speech_interrupted` timeline events; it does not persist raw audio or transcripts.
- The browser audio panel also includes a presenter cue player that simulates a spoken cue by emitting `speech_started` followed by a `tts_word` anchor. This validates the slide-sync contract without requiring a real TTS provider.

Audio providers are kept behind a small boundary:

- Provider interface: `start_session()`, `emit_timeline_event()`, `stop_session()`
- Mock provider: `MockAudioProvider`
- LiveKit credential/token provider: `LiveKitAudioProvider`
- Browser LiveKit client: the room page mints a join token, dynamically loads the LiveKit JS SDK, joins the configured room, publishes a microphone track, and records connection status into the timeline log.
- Provider smoke: `scripts/audio_provider_smoke.py`

Run it with the same local room command:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe -m devdefender_lab.room --repo sample_repo --mock
```

Then send mock audio events into the room:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\audio_provider_smoke.py
```

The audio smoke now fails if the mock sequence does not produce a mapped slide event and an active replayed `timeline.interruption` state.

Verify slide WebSocket sync and replay consistency:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\slide_sync_smoke.py
```

The slide sync smoke is state-relative and can be run repeatedly. It fails unless `/ws/slides` emits the current slide snapshot, receives the next broadcast after `POST /api/slide-control`, and agrees with `/api/slide-events`.

Verify that a TTS anchor word drives the same slide sync path:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\tts_anchor_smoke.py
```

The TTS anchor smoke posts `tts_word: next` to `/api/timeline-event`, waits for the `/ws/slides` broadcast, and fails unless the posted timeline event, mapped slide event, WebSocket broadcast, `/api/slide-events`, and `/api/timeline-events` all agree.

Verify the browser presenter cue path:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\presenter_cue_smoke.py
```

The presenter cue smoke opens the room with `auto_presenter_cue=1`, emits `speech_started` plus `tts_word: next`, and fails unless the timeline anchor maps to a replayed slide advance without audio or transcript fields.

Verify the manual interruption contract without running the full mock audio sequence:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\interruption_smoke.py
```

The interruption smoke is state-relative and can be run repeatedly. It first verifies that `POST /api/timeline-event`, `GET /api/timeline-events`, and `GET /api/session` agree on a newly active `manual-interrupt` state. It then posts `manual_voice_command: next` and fails unless replay/session mark the interruption handled and the slide advances from the baseline.

Verify the browser interruption detector with a deterministic in-browser test tone:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\browser_interruption_smoke.py
```

The browser interruption smoke opens the room with `auto_interruption=1`, runs the Web Audio detector against a generated test burst, and fails unless replay contains `speech_started`, `speech_interrupted`, an active interruption state, and no raw audio artifact fields.

Verify the room UI with browser-level HTML checks and desktop/narrow screenshots while the room is running:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\room_visual_smoke.py
```

The visual smoke writes:

- `artifacts/visual/room-desktop-smoke.png`
- `artifacts/visual/room-narrow-smoke.png`
- `artifacts/visual/room_visual_smoke.json`

These room smokes mutate slide and timeline state. Run them one at a time when they share the same running room.

Run the local Phase 2 room acceptance sequence serially:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\room_acceptance_smoke.py
```

The sequence expects a running room by default. Use `--managed-room` to start a mock room for the run, wait for `/api/session`, execute the serial smokes, and shut the room down through a temporary local shutdown token so Slidev does not remain listening on the test port.
The sequence writes `artifacts/room_acceptance_smoke.json` by default. Use `--out <path>` for a separate report file. Use `--skip-visual` when a browser is unavailable; the non-visual acceptance still checks slide sync, interruption replay, and mock audio timeline behavior.
The final acceptance step runs `scripts/artifact_secret_smoke.py`, which scans text artifacts for raw secret values loaded from `.env` and reports only variable names and file paths.
The sequence also runs `scripts/room_replay_smoke.py`, which replays `slide_events.jsonl` and `timeline_events.jsonl` directly from disk to verify current slide state, interruption state, timeline-to-slide action/source mappings, timeline event slide pointers, and the full slide event sequence without a running room process. By default it filters to the current `session.json` `thread_id`; pass `--thread-id <id>` to replay another session.
After replay, `scripts/evidence_packet_smoke.py` writes `artifacts/evidence_packet.json`, converting timeline slide pointers into structured `timeline://...` and `slide://...` evidence pointers for later Issue extraction and Agent Gateway envelopes. It fails if replay failed, a slide pointer is missing, or raw audio/transcript fields appear.
When the packet is valid, `extract_issue()` appends a budgeted high-value pointer subset to Issue evidence, and `run_tdad_refinement()` loads the same subset into the Agent Task Envelope `evidence_pointers` field. They are persisted into `issue.json`, `agent_task.json`, `agent_trace.json`, and `refinement.json`. The complete packet remains in `evidence_packet.json` for audit, while `evidence_selection.json` records the pointer budget, selected/omitted counts, and selected/omitted pointers used by downstream artifacts. The shared loader fails closed if a packet contains raw audio, transcript text, local audio paths, LiveKit tokens, or malformed pointer grammar. Valid pointers are restricted to `timeline://<thread>#event=<n>&kind=<known-kind>` and `slide://<thread>#page=<n>`.
After a Phase 1/refinement run has generated those downstream artifacts, verify the full evidence chain:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\evidence_chain_smoke.py
```

To run the managed room acceptance and immediately consume its evidence packet through the Phase 1 e2e/refinement chain:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\phase1_room_closure_smoke.py --include-livekit-token --include-livekit-browser
```

The current verified Phase 2 closure gate uses real LiveKit browser credentials and the OpenClaude backend:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\phase1_room_closure_smoke.py --include-livekit-token --include-livekit-browser --agent-backend openclaude-cli --agent-timeout 240 --out artifacts\phase1_room_closure_livekit_openclaude_smoke.json --full-out artifacts\phase1_room_closure_livekit_openclaude_smoke.full.json --room-acceptance-out artifacts\room_acceptance_livekit_openclaude_gate.json
```

The passing report is `artifacts/phase1_room_closure_livekit_openclaude_smoke.json`. It verifies managed room shutdown, LiveKit browser connect/publish events, Phase 1 e2e refinement through OpenClaude, evidence-chain continuity into Issue evidence, and artifact secret scanning. The OpenClaude path may produce a verified no-op when the required tests already exist and pass; that state is recorded in `agent_trace.json` as no-op evidence rather than treated as an uncontrolled patch.

The closure smoke writes a compact summary to `artifacts/phase1_room_closure_smoke.json` and full child-step details to `artifacts/phase1_room_closure_smoke.full.json`. Use `--include-full-results` only when you want the main report to embed all nested payloads.
When `--include-livekit-browser` is used, the closure report also asserts cross-step evidence continuity: `livekit_connected` and `audio_track_published` must appear in both the evidence chain and the extracted Issue evidence.
The same closure cross-checks also require `room_replay`, `evidence_packet`, evidence-chain pointers, and Issue evidence to refer to the same room thread so stale artifacts cannot satisfy a new run.

Use `--include-livekit-token` when `.env` contains valid `LIVEKIT_URL`, `LIVEKIT_API_KEY`, and `LIVEKIT_API_SECRET`; this adds the browser token smoke to the same report without printing credentials.
Use `--include-livekit-browser` for the stricter browser path: a headless Edge/Chrome instance loads the room with fake media, clicks through the LiveKit client path, and verifies `livekit_connected` plus `audio_track_published` in the replayed timeline.
The strict local gate for real LiveKit credentials is:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\room_acceptance_smoke.py --managed-room --include-livekit-token --include-livekit-browser --out artifacts\room_acceptance_livekit_browser_gate.json
```

Verify LiveKit credentials and token generation without printing secrets:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\livekit_provider_smoke.py
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\livekit_provider_smoke.py --check-room
```

The local room mints browser join tokens through the same API used by the browser client:

- Browser token endpoint: `POST /api/livekit-token`
- Token smoke: `scripts/livekit_token_smoke.py`

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\livekit_token_smoke.py
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\livekit_browser_smoke.py
```

The current Phase 2 skeleton intentionally does not include a real microphone interruption model, browser meeting automation, or Docker audio routing. Those Phase 3 layers should emit structured timeline events and consume the same slide-control events instead of bypassing the log.

## Smoke Tests

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe --version
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe -m pytest tests
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe -m pytest tests/test_slide_control.py tests/test_timeline.py tests/test_audio_provider.py tests/test_room.py
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\audio_provider_smoke.py
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\slide_sync_smoke.py
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\tts_anchor_smoke.py
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\presenter_cue_smoke.py
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\interruption_smoke.py
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\browser_interruption_smoke.py
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\room_visual_smoke.py
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\room_replay_smoke.py
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\evidence_packet_smoke.py
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\evidence_chain_smoke.py
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\artifact_secret_smoke.py
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\phase1_room_closure_smoke.py
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\room_acceptance_smoke.py --managed-room
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\room_acceptance_smoke.py --managed-room --include-livekit-token
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\room_acceptance_smoke.py --managed-room --include-livekit-browser
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\livekit_provider_smoke.py
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\livekit_token_smoke.py
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\livekit_browser_smoke.py
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe -m devdefender_lab.smoke --mode graph
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe -m devdefender_lab.smoke --mode openai
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe -m devdefender_lab.smoke --mode e2e
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\openclaude_plan_smoke.py
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\openclaude_patch_smoke.py
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\replay_agent_trace.py .\artifacts\agent_trace.json
npm run slides
```

If you want to verify the local harness without an API key first:

```powershell
$env:DEVDEFENDER_LLM_MODE="mock"
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe -m devdefender_lab.smoke --mode e2e
```

The end-to-end smoke writes artifacts into `artifacts/`:

- `graph.json`
- `deck/slides.md`
- `session.json`
- `state.json`
- `defense.md`
- `issue.json`
- `refinement.json`
- `agent_task.json`
- `patch.diff`
- `test_report.json`
- `agent_trace.json`
- `slidev-url.txt`

On newer conda installations, the same Python checks can also be run with:

```powershell
conda run -n devdefender-lab python -m devdefender_lab.smoke --mode graph
```

## Publish

```powershell
$env:GH_TOKEN="github_pat_..."
.\scripts\publish_github.ps1
```

## Third-Party Bring-Up

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\third_party_smoke.py --list
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\third_party_smoke.py --phase 1
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\third_party_smoke.py --name openclaude
```

Local upstream clones are stored in `third_party/src/` and are gitignored. Phase 1 results are summarized in `third_party/PHASE1_STATUS.md`.

## Architecture Notes

- `embedded` graph backend is the default because Docker/Memgraph is intentionally out of scope for this first local run.
- `MemgraphGraphStore` exists as a boundary and raises a clear runtime error until Phase 2/production infrastructure is introduced.
- The local room uses LangGraph `interrupt()` with an in-process checkpointer for the Phase 1 demo. Artifacts are persisted to disk; swapping the checkpointer for Postgres is the Phase 2/production path.
- The Phase 1 refiner is intentionally conservative: it uses a Mock Agent Gateway contract first, rejects forbidden paths or missing tests, and marks the issue as verified, rejected, or needing a guarded code change instead of freely editing production code.
- OpenClaude is attached through a CLI subprocess adapter. Plan mode is read-only; patch mode edits only a disposable workspace copy and returns artifacts to the Gateway for path validation and test execution.
- The code path uses OpenAI's Responses API through the official Python SDK.
