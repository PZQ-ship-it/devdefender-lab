# DevDefender Lab

Phase 1 integration lab for an AI code defense workflow. This repo intentionally keeps the surface small: parse a sample repo, persist a local code graph, generate a Slidev deck, call OpenAI for a defense answer, and extract a GitHub-Issue-shaped JSON payload from typed feedback.

## Local Setup

```powershell
conda env create -f environment.yml
conda activate devdefender-lab
npm install
Copy-Item .env.example .env
```

Set `OPENAI_API_KEY` in `.env` or in your shell. `OPENAI_MODEL` defaults to `gpt-5.5`.

## Smoke Tests

```powershell
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe --version
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe -m devdefender_lab.smoke --mode graph
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe -m devdefender_lab.smoke --mode openai
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe -m devdefender_lab.smoke --mode e2e
npm run slides
```

If you want to verify the local harness without an API key first:

```powershell
$env:DEVDEFENDER_LLM_MODE="mock"
C:\ProgramData\Anaconda3\envs\devdefender-lab\python.exe -m devdefender_lab.smoke --mode e2e
```

The end-to-end smoke writes artifacts into `artifacts/`:

- `graph.json`
- `state.json`
- `issue.json`
- `slidev-url.txt`

On newer conda installations, the same Python checks can also be run with:

```powershell
conda run -n devdefender-lab python -m devdefender_lab.smoke --mode graph
```

## Architecture Notes

- `embedded` graph backend is the default because Docker/Memgraph is intentionally out of scope for this first local run.
- `MemgraphGraphStore` exists as a boundary and raises a clear runtime error until Phase 2/production infrastructure is introduced.
- The code path uses OpenAI's Responses API through the official Python SDK.
