# DevDefender Lab Cleanup Record

Cleanup executed for the product scope: keep the lightweight Project Briefing Room default path and remove old exploratory surfaces.

## Kept Default Product Core

- `src/devdefender_lab/briefing.py`
- `src/devdefender_lab/briefing_contract.py`
- `src/devdefender_lab/briefing_deck.py`
- `src/devdefender_lab/briefing_workspace.py`
- `src/devdefender_lab/briefing_feedback.py`
- `src/devdefender_lab/briefing_plan_update.py`
- `src/devdefender_lab/briefing_execution_gate.py`
- `src/devdefender_lab/evidence.py`
- `scripts/project_briefing_room.py`
- `scripts/project_briefing_room_smoke.py`
- `scripts/project_briefing_room_doctor.py`
- `scripts/agent_briefing_input.py`
- `scripts/briefing_feedback_plan.py`
- `scripts/apply_briefing_feedback_plan.py`
- `scripts/answer_briefing_clarification.py`
- `scripts/briefing_execution_gate.py`
- `scripts/install_project_briefing_room_skill.ps1`
- `skills/project-briefing-room/SKILL.md`
- `skills/project-briefing-room/templates/agent_briefing_input.json`

## Removed Surfaces

- Legacy Phase 1 defense-room runtime.
- Live room, TTS, interruption, replay, and room acceptance scripts.
- Zoom/WebRTC/SaaS meeting exploration.
- OpenClaude and Agent Gateway experiment chain.
- Advanced handoff/no-op proof chain.
- Slidev/Node build surface.
- Local third-party clone/research folders.
- Historical Phase 2/3 handoff/design documents.
- Generated artifacts, caches, and sample repo.

## Regression Command

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe -m pytest tests -q
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\project_briefing_room_doctor.py --out artifacts\project_briefing_room_doctor.json
```
