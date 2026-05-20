---
name: project-briefing-room
description: Use when a code agent should brief a human stakeholder on the current repo or task status in a meeting-like flow, with non-technical architecture/progress/requirements/experiment explanations, diagrams, generated presenter speech, LiveKit room orchestration, interruption handling, and evidence closure through the DevDefender Lab runtime.
---

# Project Briefing Room

Turn the current code-agent task state into a stakeholder briefing meeting.

## Goal

Produce and present a human-readable project briefing from the current repo/task state:

- architecture and system shape
- progress and open work
- requirements coverage
- experiment or test results
- risks, unknowns, and decisions needed from the user
- follow-up tasks with evidence pointers

Default meeting path: an AI-created LiveKit room through the DevDefender Lab runtime. Do not require a human-created Zoom, Tencent Meeting, Teams, or Google Meet link unless the user explicitly asks for that provider.

## Workflow

1. Ground in the repo.
   - Read `plan.md`, `README.md`, `DESIGN.md`, `PHASE3_DESIGN.md`, and `PHASE3_HANDOFF.md` when present.
   - Inspect recent git status, changed files, tests, artifacts, and task-specific docs.
   - Prefer repo facts over asking the user.

2. Build a structured briefing request.
   - Capture project goal, current task, changed files, tests, architecture facts, experiment facts, risks, open questions, and known constraints.
   - Ask the active code-agent adapter for structured briefing data if an adapter exists.
   - If no adapter exists, create a deterministic mock/local briefing from discovered repo facts.

3. Translate for stakeholders.
   - Avoid code-heavy narration unless the audience asks for it.
   - Explain architecture using domain language, simple components, data/control flow, and responsibility boundaries.
   - Include diagram requests that can be rendered by the local runtime as Mermaid/Slidev assets.

4. Delegate deterministic work to the repo runtime.
   - The runtime owns deck generation, LiveKit provisioning, TTS audio publishing, remote interruption detection, replay, evidence packets, and artifact secret scanning.
   - The skill should orchestrate these steps; it should not duplicate runtime logic in the prompt.

5. Run the lightest available gate.
   - Before Phase 4D implementation exists, stop with a clear handoff and planned command.
   - After Phase 4D exists, prefer:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\project_briefing_room_smoke.py --managed-room --agent-backend mock --out artifacts\project_briefing_room_smoke.json --timeout 120
```

6. Report outcome.
   - Summarize the briefing artifacts, room/evidence status, interruptions handled, and any missing configuration.
   - Mention any optional skills used.
   - Do not expose raw tokens, provider secrets, raw audio, full transcripts, cookies, local storage, or unredacted meeting URLs.

## Output Contract

Use this shape for briefing data passed between adapters and runtime:

```json
{
  "audience_summary": "",
  "architecture_diagrams": [],
  "progress_status": [],
  "requirements_coverage": [],
  "experiment_results": [],
  "risks_and_unknowns": [],
  "stakeholder_questions": [],
  "follow_up_tasks": [],
  "evidence_pointers": []
}
```

## Optional Skills

Read `dependencies.md` only when deciding whether to install or invoke helper skills. Optional helper skills can improve speech setup, transcription, Notion capture, security views, PDFs, screenshots, or browser validation, but the core briefing path should remain usable without them.

## Non-Goals

- Do not make external SaaS meeting automation the default path.
- Do not capture or retain raw meeting recordings or full transcripts by default.
- Do not turn the skill into a large application runtime.
- Do not invent unverifiable project status; use evidence from repo files, tests, artifacts, and agent traces.
