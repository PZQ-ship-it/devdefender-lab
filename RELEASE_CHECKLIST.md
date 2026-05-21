# Project Briefing Room Release Checklist

Use this checklist before sharing the lightweight Project Briefing Room package.

## Scope

- Default product: VS Code Codex skill plus local Project Briefing Room artifacts.
- Included: stakeholder briefing, feedback interpretation, clarification questions, plan update, execution gate, doctor.
- Not included by default: live meeting rooms, speech or video capture, Zoom, LiveKit, WebRTC, Node/Slidev runtime, OpenAI credentials, external SaaS scheduling, or automated code-agent handoff chains.

## Required Checks

1. Install the skill:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_project_briefing_room_skill.ps1
```

2. Confirm the portable runtime bootstrap path:

```powershell
powershell -ExecutionPolicy Bypass -File "$HOME\.codex\skills\project-briefing-room\bootstrap_runtime.ps1" -SkipDoctor
```

The bootstrap script must trust only `https://github.com/PZQ-ship-it/devdefender-lab.git`.

3. Run the product doctor:

```powershell
project-briefing-room-doctor --out artifacts\project_briefing_room_doctor.json
```

4. Run the full regression suite:

```powershell
python -m pytest tests -q
```

5. Run one real feedback session without sample clarification answers:

```powershell
project-briefing-room --agent-backend workspace --repo . --feedback "Summarize the project and ask me what should change before continuing."
```

6. Confirm release artifacts:

- `artifacts/project_briefing_room/session.md`
- `artifacts/project_briefing_room/session.json`
- `artifacts/project_briefing_room/briefing_feedback_plan.json`
- `artifacts/project_briefing_room/briefing_plan_update.json`
- `artifacts/project_briefing_room/briefing_execution_gate.json`

7. Confirm safety boundaries:

- No `.env` content, provider secret, raw audio, full transcript, cookie, local storage, or meeting start URL appears in generated artifacts.
- README and skill paths use `artifacts/project_briefing_room/...`.
- Codex owns stakeholder interpretation and follow-up questions; scripts only record accepted answers and run deterministic checks.

8. Confirm packaging:

- `project-briefing-room`
- `project-briefing-room-doctor`
- `project-briefing-agent-input`
