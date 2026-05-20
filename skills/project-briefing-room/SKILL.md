---
name: project-briefing-room
description: Use when a code agent should brief a human stakeholder on the current repo or task status, translate code facts into architecture/progress/requirements/experiment language, collect feedback, ask clarifying questions, update the execution plan, and continue only after a local execution gate passes.
---

# Project Briefing Room

Turn the current code-agent task state into a stakeholder briefing and feedback-to-plan loop.

## Goal

Produce a human-readable project briefing from the current repo/task state:

- architecture and system shape
- progress and open work
- requirements coverage
- experiment or test results
- risks, unknowns, and decisions needed from the user
- follow-up tasks with evidence pointers
- stakeholder feedback interpreted into clarification questions and an updated execution plan

The default path is Codex-native and local. It does not require a live meeting room, external SaaS scheduling, Node, OpenAI credentials, raw audio, full transcripts, or a separate code-agent handoff chain.

## Default User Entry

When the user asks to brief the project or update the plan from feedback, prefer this lightweight VS Code Codex path:

```text
Use $project-briefing-room to brief me and update the execution plan from my feedback.
```

Default behavior:

- Use the current VS Code workspace as the project source.
- Generate stakeholder-readable briefing artifacts.
- Treat stakeholder feedback as the primary output and write `artifacts/project_briefing_room/briefing_feedback_plan.json`.
- Write `artifacts/project_briefing_room/briefing_plan_update.json` and `artifacts/project_briefing_room/briefing_execution_gate.json`.
- When the gate allows continuation, keep working in the same Codex session from the updated plan.

## Workflow

1. Ground in the repo.
   - Read `plan.md`, `README.md`, and any current design/handoff notes when present.
   - Inspect recent git status, changed files, tests, artifacts, and task-specific docs.
   - Prefer repo facts over asking the user.

2. Build a structured briefing request.
   - Capture project goal, current task, changed files, tests, architecture facts, experiment facts, risks, open questions, and known constraints.
   - Prefer the provider-neutral agent input contract at `artifacts/agent_briefing_input.json`.
   - Generate a starter input when useful:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\agent_briefing_input.py --repo . --out artifacts\agent_briefing_input.json --agent-kind codex
```

   - If no agent input file exists, create a deterministic local briefing from discovered repo facts.
   - Never put raw secrets, raw audio, full transcripts, cookies, local storage, or meeting start URLs in the input file.

3. Translate for stakeholders.
   - Avoid code-heavy narration unless the audience asks for it.
   - Explain architecture using domain language, simple components, data/control flow, and responsibility boundaries.
   - Include Mermaid diagram hints when they help the user understand the project.

4. Listen for stakeholder feedback and update the plan.
   - Treat stakeholder feedback as the main output of the briefing, not as a side note after a one-way report.
   - Convert feedback into `artifacts/project_briefing_room/briefing_feedback_plan.json`.
   - The feedback plan must include interpreted concerns, clarification questions, decisions, plan changes, and an updated execution plan.
   - If feedback is ambiguous, ask concise clarification questions before claiming the execution plan is final.
   - Do not store raw audio, full transcripts, provider secrets, cookies, local storage, or unredacted meeting start URLs.

5. Run the lightest available gate.
   - On a fresh install, run:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\project_briefing_room_doctor.py
```

   - For normal use, run:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\project_briefing_room.py --agent-backend workspace --repo . --feedback "The briefing should listen to my feedback, clarify my intent, and update the execution plan before continuing."
```

   - If the current code agent wrote an input file somewhere else, pass it explicitly:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\project_briefing_room.py --agent-backend workspace --repo . --agent-input artifacts\agent_briefing_input.json --feedback "The briefing should listen to my feedback, clarify my intent, and update the execution plan before continuing."
```

6. Report outcome.
   - Start with the user-facing output: `artifacts/project_briefing_room/session.md`.
   - Also mention machine-readable outputs: `artifacts/project_briefing_room/session.json`, `artifacts/project_briefing_room/briefing_feedback_plan.json`, `artifacts/project_briefing_room/briefing_plan_update.json`, and `artifacts/project_briefing_room/briefing_execution_gate.json`.
   - If `briefing_feedback_plan.json` has pending clarification questions, ask those questions before continuing implementation.
   - Record each stakeholder answer with:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\answer_briefing_clarification.py --feedback-plan artifacts\briefing_feedback_plan.json --question 1 --answer "Pause after requirements and risks, then update the next implementation step."
```

   - Apply the updated feedback plan back to `plan.md`:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\apply_briefing_feedback_plan.py --feedback-plan artifacts\briefing_feedback_plan.json --plan plan.md --out artifacts\briefing_plan_update.json
```

   - Before continuing implementation, evaluate the execution gate and proceed only when `can_continue` is true:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\briefing_execution_gate.py --plan-update artifacts\briefing_plan_update.json --out artifacts\briefing_execution_gate.json
```

   - Continue implementation directly in the current Codex session after the gate is accepted.
   - Mention any optional skills used.
   - Do not expose raw tokens, provider secrets, raw audio, full transcripts, cookies, local storage, or unredacted meeting URLs.

## Output Contract

Use this shape for briefing data passed between adapters and runtime:

```json
{
  "schema_version": "1",
  "agent_kind": "codex",
  "project_name": "",
  "task_goal": "",
  "current_task": "",
  "changed_files": [],
  "completed_work": [],
  "in_progress_work": [],
  "blockers": [],
  "next_steps": [],
  "requirements": [],
  "tests": [],
  "artifacts": [],
  "architecture_facts": [],
  "experiment_facts": [],
  "risks": [],
  "open_questions": [],
  "constraints": [],
  "evidence_pointers": []
}
```

Supported `agent_kind` values: `codex`, `aider`, `generic`.

## Feedback Plan Contract

The feedback loop writes `artifacts/project_briefing_room/briefing_feedback_plan.json`:

```json
{
  "schema_version": "1",
  "project_name": "",
  "feedback_summary": "",
  "interpreted_concerns": [],
  "clarification_questions": [],
  "decisions": [],
  "plan_changes": [],
  "updated_execution_plan": {
    "summary": "",
    "next_steps": [],
    "acceptance_criteria": [],
    "out_of_scope": []
  },
  "needs_follow_up": true,
  "evidence_pointers": []
}
```

## Non-Goals

- Do not make external SaaS meeting automation the default path.
- Do not capture or retain raw meeting recordings or full transcripts.
- Do not turn the skill into a large application runtime.
- Do not invent unverifiable project status; use evidence from repo files, tests, artifacts, and current agent input.
