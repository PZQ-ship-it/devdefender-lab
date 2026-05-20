from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from devdefender_lab.briefing_contract import (  # noqa: E402
    DEFAULT_AGENT_BRIEFING_INPUT,
    AgentKind,
    agent_input_from_context,
    write_agent_briefing_input,
)
from devdefender_lab.briefing_workspace import WorkspaceBriefingAdapter  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a provider-neutral agent briefing input JSON from repo facts.")
    parser.add_argument("--repo", type=Path, default=Path("."), help="Workspace repo path to inspect.")
    parser.add_argument("--out", type=Path, help="Output JSON path. Defaults to <repo>/artifacts/agent_briefing_input.json.")
    parser.add_argument(
        "--agent-kind",
        choices=["codex", "openclaude", "aider", "generic"],
        default="codex",
        help="Agent kind recorded in the generated contract.",
    )
    parser.add_argument("--no-overwrite", action="store_true", help="Fail if the output file already exists.")
    args = parser.parse_args()

    try:
        result = generate_agent_briefing_input(
            repo=args.repo,
            out=args.out,
            agent_kind=args.agent_kind,  # type: ignore[arg-type]
            overwrite=not args.no_overwrite,
        )
    except Exception as exc:
        result = {"ok": False, "error": _safe_error(exc)}
        print(json.dumps(result, indent=2, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ok"] else 1


def generate_agent_briefing_input(
    *,
    repo: Path,
    out: Path | None = None,
    agent_kind: AgentKind = "codex",
    overwrite: bool = True,
) -> dict[str, object]:
    repo_path = repo.resolve()
    output_path = (out or repo_path / DEFAULT_AGENT_BRIEFING_INPUT).resolve()
    adapter = WorkspaceBriefingAdapter(repo_path, agent_input_path=repo_path / ".devdefender-ignore-agent-input.json")
    context = adapter.build_context()
    agent_input = agent_input_from_context(context, agent_kind=agent_kind)
    write_agent_briefing_input(agent_input, output_path, overwrite=overwrite)
    return {
        "ok": True,
        "out": _display_path(output_path),
        "repo": _display_path(repo_path),
        "agent_kind": agent_input.agent_kind,
        "changed_file_count": len(agent_input.changed_files),
        "completed_work_count": len(agent_input.completed_work),
        "test_fact_count": len(agent_input.tests),
        "artifact_count": len(agent_input.artifacts),
        "evidence_pointer_count": len(agent_input.evidence_pointers),
    }


def _display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def _safe_error(exc: BaseException) -> str:
    text = " ".join(str(exc).split())
    replacements = {
        "LIVEKIT_API_SECRET": "LIVEKIT_SECRET_ENV",
        "LIVEKIT_API_KEY": "LIVEKIT_KEY_ENV",
        "OPENAI_API_KEY": "OPENAI_KEY_ENV",
    }
    for source, replacement in replacements.items():
        text = text.replace(source, replacement)
    return text[:500]


if __name__ == "__main__":
    raise SystemExit(main())
