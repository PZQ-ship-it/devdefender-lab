from __future__ import annotations

import argparse
import json
from pathlib import Path

from devdefender_lab.config import load_settings
from devdefender_lab.graph_store import create_graph_store
from devdefender_lab.openai_client import draft_defense
from devdefender_lab.parser import parse_python_repo
from devdefender_lab.workflow import run_phase1


DEFAULT_FEEDBACK = "Payment capture looks risky. Explain why invalid amounts cannot be captured, then create an issue if evidence is weak."


def main() -> None:
    parser = argparse.ArgumentParser(description="DevDefender Phase 1 smoke runner")
    parser.add_argument("--mode", choices=["graph", "openai", "e2e"], default="e2e")
    parser.add_argument("--repo", default="sample_repo")
    parser.add_argument("--feedback", default=DEFAULT_FEEDBACK)
    args = parser.parse_args()

    settings = load_settings()
    repo_path = Path(args.repo)

    if args.mode == "graph":
        payload = parse_python_repo(repo_path)
        store = create_graph_store(settings.graph_backend, settings.artifact_dir)
        store.save(payload)
        print(json.dumps({"nodes": len(payload.nodes), "edges": len(payload.edges)}, indent=2))
        return

    if args.mode == "openai":
        graph = parse_python_repo(repo_path)
        answer = draft_defense(settings, graph, args.feedback)
        print(answer)
        return

    state = run_phase1(settings, repo_path, args.feedback)
    print(
        json.dumps(
            {
                "slidev_url": state["slidev_url"],
                "defense_preview": state["defense"][:240],
                "issue": state["issue"].model_dump(),
                "refinement": state["refinement"].model_dump(mode="json"),
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
