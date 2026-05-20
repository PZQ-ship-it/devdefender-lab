# DevDefender Lab

DevDefender Lab is now scoped to a lightweight **Project Briefing Room** workflow for VS Code Codex and similar code agents.

The product goal is simple: let the current code agent translate repo/task state into a stakeholder-readable briefing, collect the user's feedback, ask clarifying questions when needed, update the execution plan, and continue only after the execution gate says the plan is actionable.

## Project Briefing Room Quick Start

Install the repo-versioned skill into the default Codex skill directory:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_project_briefing_room_skill.ps1
```

Invoke it from Codex:

```text
Use $project-briefing-room to brief me and update the execution plan from my feedback.
```

Check the local install and end-to-end Codex-native path:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\project_briefing_room_doctor.py
```

Run the product smoke directly:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\project_briefing_room.py --agent-backend workspace --repo . --feedback "The briefing should listen to my feedback, clarify my intent, and update the execution plan before continuing."
```

The session writes:

- `artifacts/project_briefing_room/session.md`
- `artifacts/project_briefing_room/session.json`
- `artifacts/project_briefing_room/briefing_deck/slides.md`
- `artifacts/project_briefing_room/briefing_deck/presenter_script.md`
- `artifacts/project_briefing_room/briefing_feedback_plan.json`
- `artifacts/project_briefing_room/briefing_plan_update.json`
- `artifacts/project_briefing_room/briefing_execution_gate.json`

If `artifacts/project_briefing_room/session.json` has `can_continue: true`, the current Codex session can continue from the updated plan. If pending clarification questions remain, answer them first:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\answer_briefing_clarification.py --feedback-plan artifacts\briefing_feedback_plan.json --question 1 --answer "Pause after requirements and risks, then update the next implementation step."
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\apply_briefing_feedback_plan.py --feedback-plan artifacts\briefing_feedback_plan.json --plan plan.md --out artifacts\briefing_plan_update.json
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\briefing_execution_gate.py --plan-update artifacts\briefing_plan_update.json --out artifacts\briefing_execution_gate.json
```

## Agent Input

Code agents can steer the briefing with one provider-neutral JSON file:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\agent_briefing_input.py --repo . --out artifacts\agent_briefing_input.json --agent-kind codex
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\project_briefing_room.py --agent-backend workspace --repo . --agent-input artifacts\agent_briefing_input.json
```

The template lives at `skills/project-briefing-room/templates/agent_briefing_input.json`.

## Local Setup

```powershell
conda env create -f environment.yml
conda activate devdefender-lab
python -m pip install -e .[dev]
```

No LiveKit, Node, OpenAI, or external meeting provider is required for the retained default path.

## Verification

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe -m pytest tests -q
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\project_briefing_room_doctor.py --out artifacts\project_briefing_room_doctor.json
```

## Core Modules

- `src/devdefender_lab/briefing.py`: provider-neutral briefing models and mock adapter.
- `src/devdefender_lab/briefing_workspace.py`: workspace fact adapter for VS Code Codex.
- `src/devdefender_lab/briefing_deck.py`: Markdown/Mermaid deck and presenter script generation.
- `src/devdefender_lab/briefing_feedback.py`: stakeholder feedback interpretation.
- `src/devdefender_lab/briefing_plan_update.py`: controlled `plan.md` update block.
- `src/devdefender_lab/briefing_execution_gate.py`: continuation gate.
- `src/devdefender_lab/evidence.py`: bounded evidence pointer utilities and artifact safety helpers.
