# Third-Party Bring-Up

This folder tracks upstream libraries before DevDefender stitches them together.

## Policy

- `third_party/src/` contains local clones and is gitignored.
- `third_party/manifest.yml` is the source of truth for repo URLs, phases, and smoke commands.
- `third_party/reports/` contains generated JSON run reports and is gitignored.
- Keep each smoke check minimal: prove the upstream package/CLI/example starts, do not run full upstream test suites unless needed.

## Usage

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\third_party_smoke.py --list
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\third_party_smoke.py --phase 1
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe .\scripts\third_party_smoke.py --name openclaude
```

Use `--name <library>` to run a single library.

See `PHASE1_STATUS.md` for the latest committed Phase 1 result summary.

## Optional Smoke Packages

Some upstream checks require their published runtime packages in the active conda env:

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe -m pip install "mcp[cli]" aider-chat
```

Mermaid CLI was verified from the local clone after installing clone-local npm dependencies:

```powershell
$env:PUPPETEER_SKIP_DOWNLOAD="true"
npm install --prefix .\third_party\src\mermaid-cli --ignore-scripts --cache .\third_party\.npm-cache
```

OpenClaude is cloned for source inspection, but its committed source tree needs Bun to build `dist/cli.mjs`. The Phase 1 smoke therefore verifies the published npm CLI from the repo root with `npx -y @gitlawb/openclaude --version`.
