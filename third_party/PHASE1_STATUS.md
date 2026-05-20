# Phase 1 Third-Party Status

Generated from `scripts/third_party_smoke.py --phase 1` on 2026-05-11. OpenClaude was added and smoke-tested on 2026-05-19.

| Library | Category | Commit | Smoke | Status |
| --- | --- | --- | --- | --- |
| LangGraph | orchestration | `2e5025ec1ac8d435840ed4a972097de87aaa2eab` | `import langgraph` | PASS |
| Tree-sitter | code-graph | `50bb81484d4c7868b14adf0d16d50e6494abdc85` | `node --version` | PASS |
| Tree-sitter Python | code-graph | `26855eabccb19c6abf499fbc5b8dc7cc9ab8bc64` | `import tree_sitter_python` | PASS |
| MCP Python SDK | tool-protocol | `161834d4aee2633c42d3976c8f8751b6c4d947d5` | `import mcp` | PASS |
| Slidev | presenter | `5e912cbc2d90bf406853b9c81243888dfc2842ea` | `npx slidev --version` | PASS |
| Mermaid CLI | diagram | `f0c215ad3297ebafad4261fe5d3259461157a37e` | `node src/cli.js --version` | PASS |
| Aider | refiner | `3ec8ec5a7d695b08a6c24fe6c0c235c8f87df9af` | `python -m aider.main --version` | PASS |
| OpenClaude | code-agent | `f71e7692373a61d28c82fc3fadff3feaa4071ede` | `npx -y @gitlawb/openclaude --version` | PASS |

## Notes

- Local clones live under `third_party/src/` and are not committed.
- Raw run reports live under `third_party/reports/` and are not committed.
- `Memgraph`, `LiveKit Agents`, `WhisperX`, `Puppeteer`, and `Xvfb` are tracked in `manifest.yml` for later phases.
- Mermaid CLI dependencies were installed inside its local clone with `PUPPETEER_SKIP_DOWNLOAD=true`; rendering diagrams with Chromium is still a later smoke.
- OpenClaude's source clone is tracked under `third_party/src/openclaude`; the smoke uses the published npm CLI from the repo root because the source checkout requires Bun to build `dist/cli.mjs`.
