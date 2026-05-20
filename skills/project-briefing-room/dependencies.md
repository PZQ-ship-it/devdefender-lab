# Project Briefing Room Dependencies

This file records optional helper skills for `project-briefing-room`. The core product path should work through the DevDefender Lab runtime without requiring these dependencies.

## Default Runtime

Required runtime path:

- Repo: DevDefender Lab
- Meeting provider: LiveKit
- Planned gate: `scripts/project_briefing_room_smoke.py --managed-room --agent-backend mock`

Minimal expected setup:

- Python environment for this repo
- Node dependencies for Slidev/browser assets when needed
- `LIVEKIT_URL`, `LIVEKIT_API_KEY`, and `LIVEKIT_API_SECRET` for real LiveKit room mode

## Optional Skill Candidates

- `speech`: use when speech provider setup or voice generation guidance is needed beyond the built-in Windows SAPI route.
- `transcribe`: use only if true meeting recording transcription becomes accepted scope.
- `notion-meeting-intelligence`: use when the user wants meeting notes, decisions, or feedback synced to Notion.
- `security-threat-model`: use when the briefing needs a security threat-model view.
- `security-ownership-map`: use when the briefing needs ownership or responsibility mapping.
- `pdf`: use when briefing artifacts need PDF extraction, creation, or visual review.
- `playwright`: use when validating the briefing room, deck, or browser flow through a real browser.
- `screenshot`: use only when OS-level screenshots are explicitly needed.

## Deferred Skill Candidates

- `figma-*`: defer unless the product deliverable includes UI/design handoff.
- Deployment skills such as `vercel-deploy`, `netlify-deploy`, `render-deploy`, or `cloudflare-deploy`: defer unless the user asks to publish a hosted product.
- External meeting provider skills or scripts: defer until Zoom, Tencent Meeting, Teams, or Google Meet support is an explicit requirement.

## Installer Policy

When a helper skill is missing:

1. Prefer the deterministic repo runtime if it can complete the requested briefing without the helper.
2. If the helper is needed, use `skill-installer` to list or install only that specific skill.
3. Record which optional skill was used in the final response.
4. Do not block the core briefing flow on optional Notion, transcription, screenshot, or design tooling unless the user explicitly requested that output.
