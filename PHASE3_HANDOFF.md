# Phase 3 Handoff

## Status

Phase 3 slices 3A and 3B are accepted for the current workspace.
The first low-risk 3C target, a generic WebRTC meeting page on native Windows/Edge, is also accepted.
The next low-risk 3C step, Zoom Web adapter discovery on native Windows/Edge, is also accepted.
Phase 3D end-to-end meeting closure is accepted for the current workspace.
Phase 3E mock/local meeting provisioning is accepted for the current workspace.

Accepted reports:

- 3A automation shell: `artifacts/meeting_automation_smoke.json`
- 3B media route smoke: `artifacts/media_route_smoke.json`
- 3B replay-derived evidence packet: `artifacts/evidence_packet_phase3b.json`
- 3C generic WebRTC meeting smoke: `artifacts/webrtc_meeting_smoke.json`
- 3C replay-derived evidence packet: `artifacts/evidence_packet_phase3c.json`
- 3C Zoom Web discovery smoke: `artifacts/zoom_web_discovery_smoke.json`
- 3C Zoom discovery replay-derived evidence packet: `artifacts/evidence_packet_zoom_discovery.json`
- 3D meeting closure compact report: `artifacts/phase3_meeting_closure_smoke.json`
- 3D meeting closure full report: `artifacts/phase3_meeting_closure_smoke.full.json`
- 3D replay-derived evidence packet: `artifacts/evidence_packet_phase3d.json`
- 3E mock/local meeting provisioner smoke: `artifacts/meeting_provisioner_smoke.json`
- 3E replay-derived evidence packet: `artifacts/evidence_packet_phase3e.json`

## Accepted Gates

3A local automation shell:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\meeting_automation_smoke.py --managed-room --out artifacts\meeting_automation_smoke.json
```

Expected report:

- `ok: true`
- `meeting_join_started`, `meeting_joined`, and `meeting_left` recorded.
- Seeded meeting URL is redacted in the report and timeline command.
- Temporary browser profile is removed.
- Managed room shutdown is clean: no forced kill and no lingering room/Slidev ports.

3B deterministic media route smoke:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\media_route_smoke.py --managed-room --out artifacts\media_route_smoke.json
```

Expected report:

- `ok: true`
- `virtual_audio_ready`, `virtual_video_ready`, and `media_published` recorded.
- No raw audio/video fields appear in the report.
- Managed room shutdown is clean: no forced kill and no lingering room/Slidev ports.

Shared follow-up checks:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\room_replay_smoke.py
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\evidence_packet_smoke.py --out artifacts\evidence_packet_phase3b.json
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\artifact_secret_smoke.py
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe -m pytest tests -q
```

Observed result:

- Replay passed against the latest 3B run.
- Evidence packet passed with four replay-derived pointers.
- Artifact secret scan passed with no findings.
- Full test suite passed after 3B: `154 passed`, with one LangGraph deprecation warning.

3C generic WebRTC meeting:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\webrtc_meeting_smoke.py --managed-room --out artifacts\webrtc_meeting_smoke.json
```

Expected report:

- `ok: true`
- `meeting_join_started`, `virtual_audio_ready`, `virtual_video_ready`, `meeting_joined`, `media_published`, and `meeting_left` recorded.
- Seeded WebRTC meeting URL is redacted.
- Temporary browser profile is removed.
- Managed room shutdown is clean: no forced kill and no lingering room/Slidev ports.

3C follow-up checks:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\room_replay_smoke.py
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\evidence_packet_smoke.py --out artifacts\evidence_packet_phase3c.json
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\artifact_secret_smoke.py
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe -m pytest tests -q
```

Observed 3C result:

- Replay passed against the latest 3C run.
- Evidence packet passed with seven replay-derived pointers.
- Artifact secret scan passed with no findings.
- Full test suite passed: `159 passed`, with one LangGraph deprecation warning.

3C Zoom Web discovery:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\zoom_web_discovery_smoke.py --managed-room --out artifacts\zoom_web_discovery_smoke.json
```

Expected report:

- `ok: true`
- `meeting_join_started`, `meeting_joined`, and `meeting_left` recorded from `zoom-web-discovery`.
- Zoom-like prejoin controls detected through a local fixture.
- Seeded Zoom URL is redacted in the report and timeline command, including the numeric meeting id path segment.
- No cookies, screenshots, page HTML, local storage, credentials, raw media, or transcripts are stored.
- Temporary browser profile is removed.
- Managed room shutdown is clean: no forced kill and no lingering room/Slidev ports.

3C Zoom discovery follow-up checks:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\room_replay_smoke.py
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\evidence_packet_smoke.py --out artifacts\evidence_packet_zoom_discovery.json
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\artifact_secret_smoke.py
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe -m pytest tests -q
```

Observed Zoom discovery result:

- Zoom discovery smoke passed with `ok: true`.
- Replay passed against the latest Zoom discovery run.
- Evidence packet passed with four replay-derived pointers.
- Artifact secret scan passed with no findings across 124 scanned files.
- Full test suite passed: `165 passed`, with one LangGraph deprecation warning.

3D meeting closure:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\phase3_meeting_closure_smoke.py --skip-visual --out artifacts\phase3_meeting_closure_smoke.json --full-out artifacts\phase3_meeting_closure_smoke.full.json
```

Expected report:

- `ok: true`
- One managed room thread is used across room baseline, 3A, 3B, generic WebRTC 3C, Zoom discovery 3C, replay, and evidence packet.
- Local meeting lifecycle, media-route events, generic WebRTC events, and Zoom discovery events are all present in the replay-derived evidence packet.
- Phase 1 e2e consumes the latest default `artifacts/evidence_packet.json`.
- Evidence chain confirms selected packet pointers reached `issue.json`, `agent_task.json`, `agent_trace.json`, and `refinement.json`.
- Artifact secret scan is clean.
- Pytest passes.

Observed 3D result:

- Phase 3D closure passed with `ok: true`.
- Managed room shutdown was clean: no terminate, no kill, no lingering room/Slidev ports.
- Replay saw 30 timeline events and 9 slide events on `phase1-b3850846432d`.
- Evidence packet contained 30 replay-derived evidence events, including local meeting, mock media router, generic WebRTC, and Zoom discovery sources.
- Evidence selection used budget 24, selected 24 pointers, and omitted 12 lower-priority pointers.
- Phase 1 e2e produced verified mock-agent refinement and 26 Issue evidence pointers.
- Evidence chain passed with all selected packet pointers propagated.
- Artifact secret scan passed with no findings across 133 scanned files.
- Pytest passed: `172 passed`, with one LangGraph deprecation warning.

## In Scope

- Provider-neutral meeting event contract and URL redaction.
- Provider-neutral meeting provisioner contract for AI-created meetings.
- Mock/local meeting provisioner smoke for AI-created meeting handles.
- Local `/meeting-test` page and `auto_meeting` hook.
- Managed browser lifecycle smoke for local join/leave events.
- Deterministic mock media router event contract.
- Managed room media-route smoke.
- Generic WebRTC meeting page using browser fake media and local peer connection.
- Zoom Web discovery fixture and smoke gate for prejoin control discovery/redaction.
- Phase 3D closure gate that runs the accepted Phase 3 slices against one managed room thread and verifies downstream evidence consumption.
- Timeline and evidence pointer support for meeting/media event kinds.
- Replay, evidence packet, and artifact secret validation for 3A/3B/3C events.

## Out of Scope

These remain Phase 3C or later:

- Real Zoom, Tencent Meeting, or other provider-specific full join adapter.
- Real Zoom, Tencent Meeting, Teams, or Google provider provisioning with production credentials.
- Real meeting URL login, waiting room, permission prompt, mute/camera control, and leave flows.
- Docker, Xvfb, PulseAudio, PipeWire, or virtual camera routing.
- Real generated speech routed into a meeting.
- Real meeting audio interruption detection.
- Full transcript capture or raw meeting recording retention.

## Main Paths

- Design source: `PHASE3_DESIGN.md`
- Meeting contract: `src/devdefender_lab/meeting.py`
- Media router contract: `src/devdefender_lab/media_router.py`
- Room hook and local test page: `src/devdefender_lab/room.py`
- 3A gate: `scripts/meeting_automation_smoke.py`
- 3B gate: `scripts/media_route_smoke.py`
- 3C generic WebRTC gate: `scripts/webrtc_meeting_smoke.py`
- 3C Zoom Web discovery gate: `scripts/zoom_web_discovery_smoke.py`
- 3D meeting closure gate: `scripts/phase3_meeting_closure_smoke.py`
- 3E provisioner gate: `scripts/meeting_provisioner_smoke.py`
- Tests: `tests/test_meeting.py`, `tests/test_meeting_automation_smoke.py`, `tests/test_media_router.py`, `tests/test_media_route_smoke.py`, `tests/test_webrtc_meeting_smoke.py`, `tests/test_zoom_web_discovery_smoke.py`, `tests/test_phase3_meeting_closure_smoke.py`, `tests/test_meeting_provisioner.py`, `tests/test_meeting_provisioner_smoke.py`

## Delivery Notes

- Keep 3A and 3B as local deterministic gates. They are not proof that a real meeting provider can be automated.
- 3A and 3B intentionally reuse Phase 2 room APIs, timeline logs, replay, evidence packet, and secret scan.
- Generated artifacts are verification evidence and should not be treated as source code.
- The current working tree is large. Commit Phase 3 as separate slices after Phase 2 is frozen.

Suggested Phase 3 commit slices:

1. Phase 3 design and handoff docs.
2. Meeting contract, local `/meeting-test`, 3A smoke, and tests.
3. Media router contract, 3B smoke, and tests.
4. Generic WebRTC page, 3C smoke, and tests.
5. Zoom Web discovery fixture, 3C smoke, and tests.
6. Shared timeline/evidence event-kind support.
7. Phase 3D meeting closure gate and tests.
8. Meeting provisioner contract, mock/local provider, 3E smoke, and tests.
9. Real provider provisioner adapter after credentials and account permissions are available.

## Phase 3C Entry Decision

The first 3C target has been chosen and accepted:

- Generic WebRTC meeting test page.
- Native Windows browser automation.

The second 3C target has also been chosen and accepted:

- Zoom Web adapter discovery.
- Native Windows browser automation.
- Local Zoom-like fixture by default, with `--zoom-url` accepted only as redaction/discovery input.

Before starting a provider-specific full join step, create the meeting provisioner layer so the system no longer depends on a human-prepared meeting link. Then choose exactly one real-provider path:

- Zoom provisioner plus guarded Zoom Web full join.
- Tencent Meeting provisioner plus Tencent Web discovery/full join.
- Self-hosted LiveKit-first provisioning for fully AI-owned meetings. This route is now implemented and accepted locally.

Also choose whether to keep the current runtime or change it:

- Native Windows browser automation.
- WSL/Linux host.
- Docker-first Linux container.

The lowest-risk implementation path is now mock/local Meeting Provisioner first, LiveKit room provisioning second, and a guarded Zoom or Tencent provisioner only when credentials and account permissions are supplied outside artifacts.

## Phase 3D Entry Decision

Phase 3D is accepted as the default local closure gate. Use it before attempting real provider automation, because it proves the meeting/media layer feeds the same replay, evidence packet, Issue, Agent Task Envelope, agent trace, refinement, secret scan, and regression-test chain.

## Phase 3E Entry Decision

Phase 3E solves the local version of the human scheduling dependency. The new component is a provider-neutral Meeting Provisioner:

- Input: provider, topic, duration, current room thread, and optional attendee metadata.
- Output: provider, non-secret meeting id/handle, redacted join URL, expiration, and a `secret_ref` for host/start credentials.
- Normal artifacts must not contain host start URLs, meeting passwords, provider OAuth tokens, cookies, raw HTML, screenshots, local storage, raw media, or transcripts.
- The accepted first gate uses `provider=mock`, requiring no external credentials.
- LiveKit is the first real-provider route: AI creates a LiveKit room, browser joins it with `/api/livekit-token`, and teardown deletes the room.
- External SaaS adapters can follow for Zoom, Tencent Meeting, Teams, or Google Meet, depending on available account permissions.

3E accepted gate:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\meeting_provisioner_smoke.py --provider mock --managed-room --out artifacts\meeting_provisioner_smoke.json
```

Observed 3E result:

- Mock provisioner smoke passed with `ok: true`.
- Timeline recorded `meeting_created`, `meeting_join_started`, `meeting_joined`, and `meeting_left` on `phase1-732e5f87bf3b`.
- The report stored a redacted join URL and `secret_ref`, but no host/start URL, mock host token, mock join token, password, cookies, local storage, screenshots, raw media, or transcript.
- Mock meeting teardown passed.
- Browser process exited, profile was removed, and managed room shutdown was clean.
- Replay passed with five timeline events and one slide event.
- Evidence packet passed with five replay-derived pointers in `artifacts/evidence_packet_phase3e.json`.
- Artifact secret scan passed with no findings across 135 scanned files.
- Full test suite passed: `182 passed`, with one LangGraph deprecation warning.

3E LiveKit-first accepted gate:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\meeting_provisioner_smoke.py --provider livekit --managed-room --out artifacts\meeting_provisioner_livekit_smoke.json --timeout 45
```

Observed LiveKit result:

- LiveKit provisioner smoke passed with `ok: true`.
- Timeline recorded `meeting_created`, `livekit_connected`, and `audio_track_published` on `phase1-903798063b8f`.
- The report stored `livekit://room/devdefender-c164989cf104` and `env:LIVEKIT_API_SECRET:devdefender-c164989cf104`, but no browser token, API key, API secret, host/start URL, password, cookies, local storage, screenshots, raw media, or transcript.
- LiveKit room teardown returned `livekit-room-deleted`.
- Browser profile was removed, browser was not killed, and managed room shutdown was clean.

Next external-provider step:

- Add a Zoom/Tencent SaaS provisioner adapter only after credentials and account permissions are available.
- Keep the same safety contract: real `host_start_url`, provider token, meeting password, and OAuth credentials must stay behind `secret_ref`.
