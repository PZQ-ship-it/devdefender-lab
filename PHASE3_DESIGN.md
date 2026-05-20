# Phase 3 Design Brief

## Goal

Package the accepted Phase 2 room into an engineering-grade meeting automation harness that can join a browser meeting, publish controlled audio/video, preserve replayable evidence, and feed the same Issue and Agent Gateway chain without exposing raw secrets, raw audio, or full transcripts.

Phase 3 must extend the Phase 2 contract instead of replacing it.

## Audience

- Local developers validating the automation harness before production hardening.
- Reviewers who need replayable evidence that the meeting layer did not bypass the defense workflow.
- Operators who need clear failure reports when credentials, browser permissions, virtual devices, or meeting pages fail.

## Source Contract From Phase 2

The accepted Phase 2 closure is documented in `PHASE2_HANDOFF.md`.

Phase 3 must continue to use these stable interfaces:

- Room API: `/api/timeline-event`
- LiveKit token API: `/api/livekit-token`
- Slide WebSocket: `/ws/slides`
- Timeline log: `artifacts/timeline_events.jsonl`
- Slide log: `artifacts/slide_events.jsonl`
- Evidence packet and evidence chain: `artifacts/evidence_packet.json`, `scripts/evidence_chain_smoke.py`
- Final closure style: compact report plus full child-step report

No Phase 3 component may write directly to downstream Issue, Agent Task Envelope, agent trace, or refinement artifacts. Those artifacts remain produced through the existing evidence loader and workflow chain.

## Primary Workflow

1. Start a managed Phase 2 room and verify `/api/session`.
2. Ask the meeting provisioner to create or allocate a meeting for the current defense session.
3. Store only a redacted join URL and non-secret meeting handle in normal artifacts; keep host/start URLs and API tokens in env or a secret store.
4. Start an automation browser profile with deterministic permissions and isolated state.
5. Join the provisioned meeting through an adapter for the target meeting provider.
6. Publish the Slidev room as video and controlled speech/audio as audio.
7. Record only structured provisioning, meeting lifecycle, and media-route events into the timeline.
8. Drive slide changes through TTS anchor events or explicit timeline commands.
9. Capture interruptions as structured timeline events.
10. Shut down browser, room, virtual media processes, and any provisioned meeting resources through managed teardown.
11. Run replay, evidence packet, evidence chain, secret scan, and Phase 1/OpenClaude closure.

## Components

### Meeting Adapter

Owns provider-specific browser automation.

Initial target should be one adapter only, preferably a generic browser-meeting adapter with configurable selectors. Provider-specific adapters such as Zoom Web or Tencent Meeting should be added only after the generic lifecycle is stable.

Responsibilities:

- Navigate to a meeting URL.
- Handle pre-join screens and permission prompts.
- Set display name or identity.
- Click join, mute/unmute, camera controls, and leave.
- Emit lifecycle events such as `meeting_join_started`, `meeting_joined`, `meeting_left`, and `meeting_error`.

### Meeting Provisioner

Owns AI-initiated meeting creation before browser automation.

The provisioner prevents the system from depending on a human-prepared meeting URL. It creates or allocates a meeting through a provider API or through a local/mock provider, then passes a sanitized meeting handle to the meeting adapter.

Responsibilities:

- Create a meeting for the current defense session with topic, duration, and optional attendee metadata.
- Return a provider-neutral record with `provider`, `meeting_id`, `join_url`, `host_start_url`, `expires_at`, and `secret_ref` fields.
- Redact or omit `host_start_url`, passwords, start tokens, OAuth tokens, and provider secrets from normal artifacts.
- Emit provisioning events such as `meeting_created` and `meeting_provision_failed`.
- Support a deterministic local/mock provider for CI and Phase 3D closure.
- Support a self-hosted LiveKit provider as the first real AI-owned meeting route.
- Support external SaaS provider adapters later, starting with Zoom or Tencent only after credentials are supplied outside artifacts.

Provider examples:

- LiveKit creates a programmable RTC room for the current defense thread, then the browser joins with a short-lived token from `/api/livekit-token`.
- Zoom can be integrated through a Meetings API adapter.
- Tencent Meeting can be integrated through its REST meeting creation API where the account tier supports it.
- Microsoft Teams can be integrated through Microsoft Graph online meeting creation.
- Google Meet can be integrated through Calendar event creation with conferencing data.

### Media Router

Owns virtual audio/video plumbing.

Responsibilities:

- Provide a deterministic audio input to the meeting browser.
- Provide a deterministic video input generated from the Slidev/room viewport.
- Keep raw media out of normal artifacts.
- Emit only structured route events such as `virtual_audio_ready`, `virtual_video_ready`, `media_route_error`, and `media_published`.

Preferred local implementation path:

- Linux container or WSL/Linux host first.
- Xvfb or equivalent virtual display for headed browser automation.
- PulseAudio or PipeWire virtual sink/source for audio routing.
- Browser fake-device flags only for smoke tests, not as the final meeting publishing path.

### Presenter Driver

Owns the connection between generated speech, TTS word anchors, and slide actions.

Responsibilities:

- Publish TTS anchor events through `/api/timeline-event`.
- Use the existing timeline-to-slide mapping for `tts_word`.
- Avoid direct iframe manipulation outside existing slide APIs.
- Emit timing metadata only as offsets and confidence values, not raw transcript text.
- Phase 4 starts with a browser Web Speech Synthesis harness that emits only structured `speech_started` and `tts_word` events.

### Interruption Detector

Owns real microphone or meeting-audio interruption detection.

Responsibilities:

- Convert detector outputs into `speech_started`, `speech_interrupted`, or `noise`.
- Preserve confidence and offset metadata.
- Never persist raw audio, audio paths, or full transcript text in the default artifact set.
- Support a mock/deterministic mode for CI and local smoke tests.
- Phase 4 starts with a deterministic browser Web Audio test burst that emits interruption events without saving audio.

### Phase 4 Voice Defense Flow

Owns the first local "AI defense" speaking loop after LiveKit is the default meeting substrate.

Responsibilities:

- Open with generated/browser TTS speech.
- Emit a `tts_word` anchor that advances the slide through the existing timeline mapping.
- Simulate a reviewer interruption with structured speech activity and interruption events.
- Answer the interruption, clearing the active interruption state through a follow-up speech event.
- Resume the defense and emit another `tts_word` anchor.
- Preserve only structured timeline and slide evidence pointers.

### Phase 4B LiveKit TTS Audio Route

Owns the first real LiveKit audio-track route for generated defense speech.

Responsibilities:

- Create a LiveKit room through the accepted LiveKit meeting provisioner.
- Generate local TTS audio through the room server's `/api/tts-audio` endpoint without writing the WAV into normal artifacts.
- Decode the TTS WAV in the browser and route it through a Web Audio `MediaStreamDestination`.
- Publish that generated audio `MediaStreamTrack` to LiveKit as `devdefender-tts-audio`.
- Emit only structured timeline events: `meeting_created`, `livekit_connected`, `tts_audio_track_created`, `tts_audio_track_published`, `speech_started`, and `tts_word`.
- Preserve no raw audio, audio paths, full transcript, browser token, API secret, cookies, screenshots, or local storage in normal artifacts.

### Phase 4C LiveKit Remote Interruption Detection

Owns the first real remote-audio interruption path inside a LiveKit room.

Responsibilities:

- Create a LiveKit room through the accepted LiveKit meeting provisioner.
- Connect a detector participant and a reviewer participant to the same LiveKit room.
- Publish generated reviewer speech as a real LiveKit audio track.
- Subscribe to the reviewer track from the detector participant.
- Attach and capture the remote audio element, then run browser Web Audio RMS detection.
- Emit only structured `speech_started` and `speech_interrupted` events for the remote interruption.
- Preserve no raw audio, audio paths, full transcript, browser token, API secret, cookies, screenshots, or local storage in normal artifacts.

### Orchestrator

Owns process lifecycle and final report assembly.

Responsibilities:

- Start and stop room, Slidev, browser, virtual display, and media route processes.
- Enforce teardown and lingering-port/process checks.
- Write compact and full reports.
- Fail closed if required evidence or shutdown checks are missing.

## Timeline Event Extension

Phase 3 should add meeting and media lifecycle event kinds, but preserve the same timeline event shape:

- `meeting_created`
- `meeting_provision_failed`
- `meeting_join_started`
- `meeting_joined`
- `meeting_left`
- `meeting_error`
- `virtual_audio_ready`
- `virtual_video_ready`
- `media_published`
- `media_route_error`

Each event may use existing fields:

- `source`: adapter or subsystem name.
- `command`: redacted room/provider state, never a credential or full meeting URL with tokens.
- `confidence`: detector confidence when applicable.
- `offset_ms`: media timing offset when applicable.

If these fields become insufficient, add a small structured metadata field only after updating the evidence safety scanner and pointer grammar tests.

## Security Constraints

- Do not write `.env` values, LiveKit tokens, meeting passwords, meeting join tokens, cookies, raw audio, local audio paths, screenshots containing secrets, or full transcripts into normal artifacts.
- Meeting URLs must be redacted before being written to reports.
- Browser profiles must be temporary and deleted or explicitly marked as disposable.
- Automation logs must not include request headers, cookies, or local storage dumps.
- Default evidence pointers must remain `timeline://...` and `slide://...`.
- Any retained media or screenshot must be opt-in, separately located, and excluded from the default closure gate.

## Non-goals

- Multi-provider automation in the first Phase 3 slice.
- Production deployment or autoscaling.
- Human-like avatar rendering.
- Full meeting transcript capture in the default workflow.
- Replacing LiveKit or the Phase 2 room as the local acceptance base.
- Direct Code Agent access to meeting recordings, raw transcripts, cookies, or browser profiles.

## Acceptance Checks

### Slice 3A: Automation Shell

- A managed command starts the Phase 2 room, launches a browser automation profile, opens a harmless local meeting test page, and shuts everything down cleanly.
- The report records browser start, join attempt, joined, left, and clean shutdown.
- No raw secrets or browser profile data appear in artifacts.

Current local gate:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\meeting_automation_smoke.py --managed-room --out artifacts\meeting_automation_smoke.json
```

The accepted report is `artifacts/meeting_automation_smoke.json`. It records `meeting_join_started`, `meeting_joined`, and `meeting_left` from the local `/meeting-test` page, redacts the seeded meeting URL, removes the temporary browser profile, and shuts down the managed room without lingering ports.

### Slice 3B: Virtual Media Smoke

- The automation browser can publish deterministic fake or virtual audio/video to a local test target.
- The timeline records `virtual_audio_ready`, `virtual_video_ready`, and `media_published`.
- Replay and evidence packet smokes accept those events without raw media fields.

Current local gate:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\media_route_smoke.py --managed-room --out artifacts\media_route_smoke.json
```

The accepted report is `artifacts/media_route_smoke.json`. It records deterministic `virtual_audio_ready`, `virtual_video_ready`, and `media_published` events from the mock media router, keeps raw media fields out of artifacts, and shuts down the managed room without lingering ports.

### Slice 3C: Real Meeting Adapter

- One configured provider adapter joins a real meeting URL using credentials supplied outside artifacts.
- The adapter records redacted lifecycle events.
- Shutdown leaves no managed browser, room, virtual display, or media-route processes behind.

Current first 3C target:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\webrtc_meeting_smoke.py --managed-room --out artifacts\webrtc_meeting_smoke.json
```

The accepted report is `artifacts/webrtc_meeting_smoke.json`. It uses a local generic WebRTC meeting page with browser fake media on native Windows/Edge, records `meeting_join_started`, `virtual_audio_ready`, `virtual_video_ready`, `meeting_joined`, `media_published`, and `meeting_left`, redacts the seeded meeting URL, removes the temporary browser profile, and shuts down the managed room without lingering ports.

This is a real browser WebRTC lifecycle gate, not a Zoom Web or Tencent Meeting provider adapter.

Current Zoom Web discovery target:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\zoom_web_discovery_smoke.py --managed-room --out artifacts\zoom_web_discovery_smoke.json
```

The accepted report is `artifacts/zoom_web_discovery_smoke.json`. It uses a local Zoom-like discovery page on native Windows/Edge, records `meeting_join_started`, `meeting_joined`, and `meeting_left` from `zoom-web-discovery`, detects prejoin controls without saving cookies, screenshots, page HTML, local storage, credentials, or raw meeting artifacts, redacts the seeded Zoom URL including the meeting id path segment, removes the temporary browser profile, and shuts down the managed room without lingering ports.

This is an adapter discovery gate, not proof of full Zoom Web login, waiting room handling, or real meeting join.

### Slice 3D: End-to-End Closure

- The meeting automation gate runs room acceptance, local meeting adapter smoke, the default AI-initiated LiveKit provisioner, media route smoke, replay, evidence packet, evidence chain, artifact secret scan, and Phase 1 closure.
- The compact report must show every required check true.
- LiveKit/meeting/media pointers must be present in both the evidence chain and Issue evidence when their smokes ran.
- The same room thread must be used across replay, evidence packet, evidence chain, and Issue evidence.

Current Phase 3D gate:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\phase3_meeting_closure_smoke.py --skip-visual --out artifacts\phase3_meeting_closure_smoke.json --full-out artifacts\phase3_meeting_closure_smoke.full.json
```

The accepted report is `artifacts/phase3_meeting_closure_smoke.json`, with full child-step details in `artifacts/phase3_meeting_closure_smoke.full.json`. It starts one managed room, runs the room baseline, 3A local meeting automation, the default LiveKit provider through `meeting_provisioner_smoke.py --provider livekit`, 3B media route, 3C generic WebRTC, 3C Zoom Web discovery, replay, evidence packet, Phase 1 e2e, evidence chain, artifact secret scan, and pytest. The accepted run produced 34 replay-derived evidence events on one room thread and confirmed local meeting, LiveKit provisioner, media route, WebRTC, and Zoom discovery events all entered the packet. The LiveKit provider step has bounded retry because browser signal connection setup can fail transiently; the accepted run passed on attempt 1.

### Slice 3E: AI-Initiated Meeting Provisioning

- A provider-neutral meeting provisioner creates a meeting before the adapter joins it.
- The local/mock provider is the first accepted implementation and requires no external credentials.
- Real providers must read credentials only from env or a secret store.
- The report records a redacted `join_url`, provider name, non-secret meeting handle, expiration, and teardown status.
- Host/start URLs, meeting passwords, provider access tokens, cookies, raw HTML, screenshots, and local storage are not written to normal artifacts.

Current local gate:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\meeting_provisioner_smoke.py --provider mock --managed-room --out artifacts\meeting_provisioner_smoke.json
```

The accepted report is `artifacts/meeting_provisioner_smoke.json`. It uses the mock provisioner to create an AI-owned local meeting handle, records `meeting_created`, `meeting_join_started`, `meeting_joined`, and `meeting_left` on one room thread, stores only a redacted join URL and `secret_ref`, tears down the mock meeting, removes the browser profile, and passes replay, evidence packet, artifact secret scan, and the full pytest suite. A later real-provider gate may use `--provider zoom` or `--provider tencent`, but only when credentials and account permissions are supplied outside artifacts.

Current LiveKit-first gate:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\meeting_provisioner_smoke.py --provider livekit --managed-room --out artifacts\meeting_provisioner_livekit_smoke.json --timeout 45
```

The accepted report is `artifacts/meeting_provisioner_livekit_smoke.json`. It uses `LIVEKIT_URL`, `LIVEKIT_API_KEY`, and `LIVEKIT_API_SECRET` from the local environment to create a real LiveKit room named from the current room thread, records `meeting_created`, then opens the room browser with `auto_livekit=1` and verifies `livekit_connected` plus `audio_track_published`. The report stores only the non-secret `livekit://room/...` handle and `secret_ref`, deletes the LiveKit room during teardown, removes the browser profile, and keeps the raw browser token/API secret out of artifacts.

### Slice 4A: Browser TTS Defense Flow

- A dedicated `/voice-defense-test` page runs the first local TTS/interruption/resume loop.
- The browser calls Web Speech Synthesis for the opening, interruption answer, and resumed explanation.
- The page emits only structured timeline events, not transcripts or raw audio.
- Two `tts_word: next` anchors must advance slides twice.
- A deterministic Web Audio test burst must emit `speech_started` and `speech_interrupted`.
- The follow-up answer/resume speech must clear the active interruption state.

Current Phase 4A gate:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\phase4_voice_defense_smoke.py --managed-room --out artifacts\phase4_voice_defense_smoke.json --timeout 35
```

The accepted report is `artifacts/phase4_voice_defense_smoke.json`. It records seven new timeline events, advances from slide 1 to slide 3 through two TTS anchors, marks the interruption handled after the answer/resume path, removes the managed room cleanly, and keeps raw audio/transcript fields out of the report. Replay and evidence packet acceptance are stored in `artifacts/evidence_packet_phase4_voice_defense.json`.

### Slice 4B: LiveKit TTS Audio Track

- A dedicated `/livekit-tts-test` page publishes generated TTS audio into a provisioned LiveKit room.
- The room server returns SAPI-generated WAV bytes from `/api/tts-audio`; the response is not written to normal artifacts.
- The browser decodes the WAV with `decodeAudioData`, routes it through Web Audio, and publishes the resulting audio track to LiveKit.
- The smoke must verify `tts_audio_track_created` and `tts_audio_track_published`, plus a `tts_word: next` anchor.
- The report must keep raw audio/transcript fields out and teardown the LiveKit room.

Current Phase 4B gate:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\phase4_livekit_tts_smoke.py --managed-room --out artifacts\phase4_livekit_tts_smoke.json --timeout 75
```

The accepted report is `artifacts/phase4_livekit_tts_smoke.json`. It creates a LiveKit room, records six new timeline events, publishes the generated SAPI WAV media stream as a LiveKit audio track, advances one slide through the TTS anchor, deletes the LiveKit room during teardown, and keeps raw audio/transcript fields out of the report. Replay and evidence packet acceptance are stored in `artifacts/evidence_packet_phase4_livekit_tts.json`.

### Slice 4C: LiveKit Remote Audio Interruption

- A dedicated `/livekit-interruption-test` page connects detector and reviewer participants to the same LiveKit room.
- The reviewer participant publishes generated reviewer speech as a LiveKit audio track.
- The detector participant subscribes to the reviewer track and detects speech/interruption through Web Audio RMS.
- The page emits a timeline-driven `goto` baseline event for replay, then structured meeting/audio/interruption events.
- The report must keep raw audio/transcript fields out and teardown the LiveKit room.

Current Phase 4C gate:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\phase4_livekit_interruption_smoke.py --managed-room --out artifacts\phase4_livekit_interruption_smoke.json --timeout 90
```

The accepted report is `artifacts/phase4_livekit_interruption_smoke.json`. It records detector and reviewer LiveKit connections, reviewer audio-track publish, remote `speech_started`, remote `speech_interrupted`, active interruption state, clean LiveKit teardown, and no raw audio/transcript fields. Replay and evidence packet acceptance are stored in `artifacts/evidence_packet_phase4_livekit_interruption.json`.

## Product Direction: Project Briefing Room

The next product step is not another external meeting SaaS adapter. The product should package the accepted LiveKit meeting runtime as a lightweight, code-agent-friendly project briefing workflow.

Default product shape:

- A repo-versioned Codex skill named `project-briefing-room` is the user-facing entry point.
- The skill is a thin orchestrator, not the whole product runtime.
- The deterministic local runtime keeps ownership of repo scanning, graph/deck generation, LiveKit room provisioning, TTS publishing, remote interruption detection, evidence packets, replay, and secret scanning.
- Code agents integrate through structured briefing adapters instead of controlling meeting internals directly.
- LiveKit remains the default AI-initiated meeting path because the agent can create and tear down the room without a human scheduling a Zoom/Tencent meeting first.

The product skill should:

- Inspect the current repo/task state, recent changes, tests, artifacts, and design notes.
- Ask the active code agent adapter for a structured project briefing report.
- Translate code-level facts into non-technical stakeholder language: architecture sketch, progress, requirements coverage, experiments, risks, open decisions, and next asks.
- Request diagram/deck generation from the local runtime.
- Launch the LiveKit-backed room flow and preserve only structured evidence.
- Optionally call or install dependency skills when the user's environment supports them.

Structured code-agent briefing output should be JSON-shaped and provider-neutral:

```text
{
  audience_summary,
  architecture_diagrams,
  progress_status,
  requirements_coverage,
  experiment_results,
  risks_and_unknowns,
  stakeholder_questions,
  follow_up_tasks,
  evidence_pointers
}
```

Skill dependency policy:

- Required dependency: none beyond this repo runtime and the product skill itself.
- Optional install/call candidates: `speech` for speech provider setup, `transcribe` only if true recording transcription becomes an accepted requirement, `notion-meeting-intelligence` for meeting notes sync, `security-threat-model` and `security-ownership-map` for security-oriented briefings, plus installed local `pdf`, `playwright`, and `screenshot` skills for artifact and visual checks.
- Figma skills are deferred unless the product needs UI/design handoff output.
- Existing skills do not replace this product workflow; they are dependencies the product skill may orchestrate.

Planned Phase 4D gate:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\project_briefing_room_smoke.py --managed-room --agent-backend mock --out artifacts\project_briefing_room_smoke.json --timeout 120
```

Phase 4D acceptance should prove a one-command path from repo state to stakeholder briefing deck, LiveKit room creation, generated presenter audio, remote interruption handling, replay, evidence packet, and artifact secret scan. It must not require a human-created meeting link.

## Proposed Files

Prefer adding new files instead of enlarging `room.py` further:

- `skills/project-briefing-room/SKILL.md`: repo-versioned product skill entry point for install/call orchestration.
- `skills/project-briefing-room/dependencies.md`: optional skill dependency map and installer guidance.
- `src/devdefender_lab/briefing.py`: structured project briefing schema and code-agent adapter contract.
- `src/devdefender_lab/briefing_deck.py`: non-technical briefing script, Mermaid/Slidev deck, and diagram rendering helpers.
- `src/devdefender_lab/meeting.py`: provider-neutral contracts and redaction helpers.
- `src/devdefender_lab/meeting_provisioner.py`: provider-neutral meeting creation contracts.
- `src/devdefender_lab/media_router.py`: virtual audio/video route contracts.
- `src/devdefender_lab/orchestrator.py`: managed process lifecycle helpers if existing scripts start duplicating logic.
- `scripts/project_briefing_room_smoke.py`: Phase 4D one-command product briefing gate.
- `scripts/meeting_automation_smoke.py`: Slice 3A gate.
- `scripts/media_route_smoke.py`: Slice 3B gate.
- `scripts/phase3_meeting_closure_smoke.py`: final Phase 3 closure gate.
- `scripts/meeting_provisioner_smoke.py`: 3E AI-initiated meeting creation gate.
- `scripts/livekit_browser_smoke.py`: accepts a provisioned LiveKit room/identity for the LiveKit-first gate.
- `scripts/phase4_voice_defense_smoke.py`: first Phase 4 browser TTS/interruption/resume gate.
- `scripts/phase4_livekit_tts_smoke.py`: Phase 4B generated TTS audio LiveKit publish gate.
- `scripts/phase4_livekit_interruption_smoke.py`: Phase 4C LiveKit remote audio interruption gate.
- `scripts/webrtc_meeting_smoke.py`: first 3C generic WebRTC gate.
- `scripts/zoom_web_discovery_smoke.py`: 3C Zoom Web discovery gate.
- `tests/test_briefing.py`
- `tests/test_project_briefing_room_smoke.py`
- `tests/test_meeting.py`
- `tests/test_media_router.py`
- `tests/test_meeting_automation_smoke.py`
- `tests/test_phase3_meeting_closure_smoke.py`
- `tests/test_meeting_provisioner.py`
- `tests/test_meeting_provisioner_smoke.py`
- `tests/test_phase4_voice_defense_smoke.py`
- `tests/test_phase4_livekit_tts_smoke.py`
- `tests/test_phase4_livekit_interruption_smoke.py`
- `tests/test_zoom_web_discovery_smoke.py`

## Implementation Order

1. Add timeline kinds, redaction helpers, and tests.
2. Add provider-neutral meeting adapter contracts with a local test-page adapter.
3. Add managed browser lifecycle smoke and teardown checks.
4. Add virtual media router contracts and deterministic fake-media smoke.
5. Extend evidence pointer selection and chain checks for meeting/media events.
6. Add one real meeting provider adapter after the generic WebRTC lifecycle stays stable.
7. Add Phase 3 closure gate.
8. Add meeting provisioner contracts, mock/local provisioning, and a provisioning smoke.
9. Add LiveKit as the first real provider route after the mock/local provisioning gate is stable.
10. Defer Zoom/Tencent provisioners unless external SaaS integration becomes an explicit product requirement.
11. Add the repo-versioned `project-briefing-room` skill skeleton and dependency manifest.
12. Add structured briefing schemas and a mock code-agent adapter report.
13. Add a non-technical briefing deck/script generator with Mermaid/Slidev diagram slots.
14. Add the Phase 4D one-command Project Briefing Room smoke on the existing LiveKit path.
15. Add optional skill-installer checks after the deterministic local gate is stable.

## Open Decisions

- Product skill packaging: repo-local `skills/project-briefing-room` first, then `$CODEX_HOME/skills` install packaging.
- First real code-agent adapter beyond mock: Codex-native structured report, OpenClaude CLI, or Aider.
- Runtime base: native Windows, WSL/Linux, or Docker-first.
- Media stack: PulseAudio, PipeWire, or browser fake-device only for the first pass.
- Whether meeting screenshots are allowed as opt-in debug artifacts.
- Whether full transcripts are ever captured, and if so, which separate retention policy governs them.
- Secret backend for real meeting provisioners: env-only for local development, OS credential vault, or cloud secret manager.
