# DevDefender Lab

DevDefender Lab is now scoped to a lightweight **Project Briefing Room** workflow for VS Code Codex and similar code agents.

The product goal is simple: let the current code agent translate repo/task state into a stakeholder-readable briefing, collect the user's feedback, ask clarifying questions when needed, update the execution plan, and continue only after the execution gate says the plan is actionable.

## Project Briefing Room Quick Start

Install the repo-versioned skill into the default Codex skill directory:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_project_briefing_room_skill.ps1
```

If the skill is installed on a machine that does not already have this repository or the `project-briefing-room` command, Codex can bootstrap the trusted runtime from GitHub:

```powershell
powershell -ExecutionPolicy Bypass -File "$HOME\.codex\skills\project-briefing-room\bootstrap_runtime.ps1"
```

The bootstrap script only trusts `https://github.com/PZQ-ship-it/devdefender-lab.git`, installs the runtime package with `python -m pip install -e`, and runs `project-briefing-room-doctor`.

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

After installing the package, the same entry points are available as commands:

```powershell
project-briefing-room --agent-backend workspace --repo . --feedback "The briefing should listen to my feedback, clarify my intent, and update the execution plan before continuing."
project-briefing-room-doctor --out artifacts\project_briefing_room_doctor.json
project-briefing-agent-input --repo . --out artifacts\agent_briefing_input.json --agent-kind codex
```

The session writes:

- `artifacts/project_briefing_room/session.md`
- `artifacts/project_briefing_room/session.json`
- `artifacts/project_briefing_room/briefing_deck/slides.md`
- `artifacts/project_briefing_room/briefing_deck/presenter_script.md`
- `artifacts/project_briefing_room/briefing_feedback_plan.json`
- `artifacts/project_briefing_room/briefing_plan_update.json`
- `artifacts/project_briefing_room/briefing_execution_gate.json`

For a real feedback run, leave off `--use-default-clarifications`. Codex should present `artifacts/project_briefing_room/session.md`, listen to the user's feedback, decide whether the feedback changes direction, requirements, risk, or acceptance, and ask any needed follow-up questions in the chat. Scripts are only for recording the accepted answers and checking whether the updated plan is safe to continue.

If `artifacts/project_briefing_room/session.json` has `can_continue: true`, the current Codex session can continue from the updated plan. If it has `can_continue: false`, Codex should read `pending_questions`, clarify them with the user, then use the deterministic helper scripts to record the accepted answers, regenerate the plan update, and evaluate the gate:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\answer_briefing_clarification.py --feedback-plan artifacts\project_briefing_room\briefing_feedback_plan.json --question 1 --answer "Pause after requirements and risks, then update the next implementation step."
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\apply_briefing_feedback_plan.py --feedback-plan artifacts\project_briefing_room\briefing_feedback_plan.json --plan plan.md --out artifacts\project_briefing_room\briefing_plan_update.json
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\briefing_execution_gate.py --plan-update artifacts\project_briefing_room\briefing_plan_update.json --out artifacts\project_briefing_room\briefing_execution_gate.json
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

## Release Scope

This repository currently publishes the lightweight Project Briefing Room path only: VS Code Codex skill orchestration, local workspace facts, stakeholder briefing artifacts, feedback-to-plan handling, and a local execution gate.

Out of scope for the default package: live meeting rooms, speech or video capture, Zoom, LiveKit, WebRTC, Node/Slidev presentation runtime, OpenAI credentials, external SaaS scheduling, and automated code-agent handoff chains.

Before sharing the package, follow `RELEASE_CHECKLIST.md`.

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
