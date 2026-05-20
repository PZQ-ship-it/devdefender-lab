# DevDefender Room Design Brief

## Audience

Local developers testing the DevDefender defense room during Phase 1 and Phase 2 integration. Phase 4D expands this into code agents that need a lightweight, repeatable way to brief non-technical stakeholders on current project status.

## Primary Workflow

1. Inspect the generated Slidev deck.
2. Control slides manually or through timeline-driven commands.
3. Connect LiveKit when credentials are available.
4. Submit reviewer feedback and inspect defense/refinement artifacts.
5. Verify replay logs without leaving the browser.
6. Run the `project-briefing-room` skill to generate a stakeholder briefing from the current repo/task state.
7. Present the briefing in an AI-created LiveKit room with generated speech and structured interruption handling.

## Non-goals

- Marketing or landing-page presentation.
- Full external SaaS meeting automation.
- Decorative visual language.
- Replacing the existing one-file local room implementation.
- Requiring a human-created Zoom/Tencent/Teams/Google meeting link for the default product path.
- Requiring every helper capability to be implemented inside this repo when an optional skill can provide it.

## Information Hierarchy

1. Header status and current thread.
2. Slide viewport.
3. Feedback form and final results.
4. Operational controls: slides, voice harness, LiveKit.
5. Replay logs.
6. Product briefing summary: architecture, progress, requirements coverage, experiments, risks, and open asks.

## Interaction States

- Waiting for feedback.
- Answering feedback.
- Complete with defense, issue, and TDAD report.
- LiveKit disconnected, connecting, connected, connected without microphone, error.
- Timeline event mapped to slide change or recorded without slide change.
- Interruption active after `speech_interrupted`, then handled after the next command or TTS anchor.
- Manual interruption trigger available in the control panel for local replay/UI validation.
- Project briefing generated, LiveKit briefing room created, presenter speech active, remote feedback/interruption handled, and structured evidence preserved.

## Visual Constraints

- Operational tool UI: dense but readable, no hero or marketing layout.
- Right panel should support repeated use without forcing all controls into the first viewport.
- Cards are allowed only for distinct tool panels; avoid nested cards.
- Buttons and log rows must not overflow in narrow viewports.
- Keep palette restrained and functional, with status color used sparingly.

## Acceptance Checks

- Desktop: slide viewport remains the dominant surface; right panel exposes status and feedback first.
- Narrow viewport: slide appears first, controls stack below without horizontal scroll.
- Logs remain readable after several events.
- LiveKit and voice controls are discoverable but not visually dominant.
- Interruption state is visible from replayed timeline events without exposing raw audio or transcript text.
- Browser interruption detection uses a local Web Audio RMS harness and emits only structured timeline events.
- Browser presenter cues emit structured `speech_started` and `tts_word` anchors to validate slide sync before a real TTS provider is attached.
- Phase 4 browser voice defense flow uses Web Speech Synthesis for opening, answer, and resumed explanation, but persists only structured timeline events and evidence pointers.
- Phase 4B publishes generated SAPI WAV speech into LiveKit as a browser Web Audio `MediaStreamTrack`, while keeping raw audio and transcript content out of normal artifacts.
- Phase 4C detects a remote LiveKit reviewer audio track through browser Web Audio RMS and emits only structured interruption events.
- Phase 4D product path is driven by a thin `project-briefing-room` skill that can be installed/called with minimal manual setup and delegates deterministic work to this repo runtime.
- Phase 4D translates code-agent/project facts into non-technical briefing material: architecture diagram, progress, requirements coverage, experiment results, risks, open questions, and next asks.
- Phase 4D uses LiveKit as the default AI-initiated meeting path and does not depend on a human-created external meeting link.
- Optional helper skills may be installed or called for speech setup, transcription, Notion meeting notes, security views, PDFs, screenshots, or browser validation; the core gate must still pass without making those optional skills mandatory.
- Tool tabs expose selected state to assistive technology and stay compact on narrow viewports.
- No raw token, secret, audio path, or full transcript appears in the UI.
- `scripts/slide_sync_smoke.py` passes repeatedly by comparing WebSocket snapshot, next broadcast, and replayed slide log relative to the current slide.
- `scripts/tts_anchor_smoke.py` passes repeatedly by posting a `tts_word` anchor, receiving the mapped WebSocket slide broadcast, and confirming both slide and timeline replay logs.
- `scripts/presenter_cue_smoke.py` passes by opening the room with `auto_presenter_cue=1`, replaying a browser cue, and confirming the cue's `tts_word` anchor advances the slide without audio or transcript fields.
- `scripts/phase4_voice_defense_smoke.py` passes by opening `/voice-defense-test?auto_voice_defense=1`, running browser TTS, deterministic interruption, answer, and resume flow, then confirming two TTS anchors advance two slides without audio or transcript artifacts.
- `scripts/phase4_livekit_tts_smoke.py` passes by creating a LiveKit room, opening `/livekit-tts-test?auto_livekit_tts=1`, decoding `/api/tts-audio` SAPI WAV bytes in the browser, publishing the generated TTS audio track to LiveKit, and confirming one TTS anchor advances a slide without audio or transcript artifacts.
- `scripts/phase4_livekit_interruption_smoke.py` passes by creating a LiveKit room, connecting detector and reviewer participants, publishing reviewer speech as remote audio, detecting `speech_started` and `speech_interrupted` from the subscribed remote track, and preserving only structured evidence.
- `scripts/audio_provider_smoke.py` passes only when replay contains a mapped slide event and active interruption state.
- `scripts/interruption_smoke.py` passes repeatedly by checking a new active manual interruption, then a handled state after a follow-up `next` command and baseline-relative slide advance.
- `scripts/browser_interruption_smoke.py` passes by opening the room with `auto_interruption=1`, triggering a deterministic browser test burst, and replaying `speech_started` plus `speech_interrupted` without raw audio artifact fields.
- `scripts/room_visual_smoke.py` passes against a running local room and writes desktop/narrow screenshots.
- `scripts/artifact_secret_smoke.py` passes only when generated text artifacts do not contain raw secret values loaded from `.env`.
- `scripts/room_replay_smoke.py` passes by reconstructing slide state, interruption state, timeline-to-slide action/source mappings, timeline event slide pointers, and the full slide event sequence from JSONL artifacts without a running room, filtered to the current `session.json` thread unless explicitly overridden.
- `scripts/evidence_packet_smoke.py` passes by converting replayed timeline slide pointers into structured `timeline://...` and `slide://...` evidence pointers without raw audio or transcript fields.
- `extract_issue()` and `run_tdad_refinement()` consume a valid `artifacts/evidence_packet.json` through the same fail-closed loader, adding only a budgeted high-value subset of structured evidence pointers to Issue evidence, Agent Task Envelope, and trace artifacts.
- `artifacts/evidence_selection.json` records the pointer budget, selected/omitted counts, and selected/omitted pointers; `scripts/evidence_chain_smoke.py` verifies it matches the shared loader output.
- Evidence pointers must pass strict grammar: `timeline://<thread>#event=<n>&kind=<known-kind>` or `slide://<thread>#page=<n>` with no extra parameters, paths, raw transcript/audio schemes, or unsafe thread identifiers.
- `scripts/evidence_chain_smoke.py` passes only after Issue/refinement artifacts contain the same replay-derived evidence pointers as `artifacts/evidence_packet.json`.
- `scripts/phase1_room_closure_smoke.py` passes only when managed room acceptance, Phase 1 e2e refinement, evidence-chain replay, and artifact secret scanning all pass in sequence.
- `scripts/phase1_room_closure_smoke.py` writes a compact primary report and a separate full report so routine acceptance output stays readable while detailed child payloads remain available.
- When the LiveKit browser smoke runs, closure cross-checks require `livekit_connected` and `audio_track_published` pointers in both the evidence-chain report and Issue evidence.
- Closure cross-checks require `room_replay`, `evidence_packet`, evidence-chain pointers, and Issue evidence to share the same room thread.
- Stateful room smokes are run serially when they target the same room.
- `scripts/room_acceptance_smoke.py` passes when the serial local Phase 2 room smoke sequence passes and writes a replayable JSON report.
- `scripts/room_acceptance_smoke.py --managed-room` starts a mock room, waits for `/api/session`, shuts it down through a temporary token, and fails if the managed room or Slidev ports remain listening.
- `scripts/room_acceptance_smoke.py --include-livekit-token` also passes when the room can mint a browser LiveKit token from configured credentials without exposing API key or secret values.
- `scripts/room_acceptance_smoke.py --include-livekit-browser` also passes when a headless browser can load the room, connect to LiveKit with fake media, publish an audio track, and replay `livekit_connected` plus `audio_track_published`.
- The strict LiveKit credential gate is `scripts/room_acceptance_smoke.py --managed-room --include-livekit-token --include-livekit-browser --out artifacts/room_acceptance_livekit_browser_gate.json`.

## Verified Closure

- The Phase 2 local room is closed by `artifacts/phase1_room_closure_livekit_openclaude_smoke.json`.
- The verified command is `scripts/phase1_room_closure_smoke.py --include-livekit-token --include-livekit-browser --agent-backend openclaude-cli --agent-timeout 240 --out artifacts\phase1_room_closure_livekit_openclaude_smoke.json --full-out artifacts\phase1_room_closure_livekit_openclaude_smoke.full.json --room-acceptance-out artifacts\room_acceptance_livekit_openclaude_gate.json`.
- The report must show `room_acceptance`, `phase1_e2e`, `evidence_chain`, and `artifact_secret` all true.
- The closure cross-checks must show LiveKit pointers in both evidence chain and Issue evidence, matching room/evidence thread IDs, clean managed shutdown, and clean secret scan.
- Phase 3 remains out of this closure: real microphone interruption models, meeting browser automation, Docker audio routing, and virtual camera publishing are not part of the current accepted surface.
