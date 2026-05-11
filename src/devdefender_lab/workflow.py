from __future__ import annotations

from pathlib import Path
from typing import TypedDict

from langgraph.graph import END, StateGraph

from devdefender_lab.config import Settings
from devdefender_lab.graph_store import create_graph_store
from devdefender_lab.models import CodeGraphPayload, DefenseIssue
from devdefender_lab.openai_client import draft_defense, extract_issue
from devdefender_lab.parser import parse_python_repo


class DefenseState(TypedDict, total=False):
    repo_path: str
    feedback: str
    graph: CodeGraphPayload
    defense: str
    issue: DefenseIssue
    slidev_url: str


def build_graph(settings: Settings):
    graph = StateGraph(DefenseState)

    def ingest(state: DefenseState) -> DefenseState:
        repo_path = Path(state["repo_path"])
        payload = parse_python_repo(repo_path)
        store = create_graph_store(settings.graph_backend, settings.artifact_dir)
        store.save(payload)
        return {**state, "graph": payload}

    def defend(state: DefenseState) -> DefenseState:
        answer = draft_defense(settings, state["graph"], state["feedback"])
        return {**state, "defense": answer}

    def issue(state: DefenseState) -> DefenseState:
        extracted = extract_issue(settings, state["feedback"], state["defense"])
        return {**state, "issue": extracted}

    def slides(state: DefenseState) -> DefenseState:
        slidev_url = f"http://127.0.0.1:{settings.slidev_port}"
        return {**state, "slidev_url": slidev_url}

    graph.add_node("ingest", ingest)
    graph.add_node("defend", defend)
    graph.add_node("extract_issue", issue)
    graph.add_node("slides", slides)
    graph.set_entry_point("ingest")
    graph.add_edge("ingest", "defend")
    graph.add_edge("defend", "extract_issue")
    graph.add_edge("extract_issue", "slides")
    graph.add_edge("slides", END)
    return graph.compile()


def run_phase1(settings: Settings, repo_path: Path, feedback: str) -> DefenseState:
    settings.artifact_dir.mkdir(parents=True, exist_ok=True)
    app = build_graph(settings)
    state = app.invoke({"repo_path": str(repo_path), "feedback": feedback})
    (settings.artifact_dir / "state.json").write_text(
        _state_to_json(state),
        encoding="utf-8",
    )
    (settings.artifact_dir / "issue.json").write_text(
        state["issue"].model_dump_json(indent=2),
        encoding="utf-8",
    )
    (settings.artifact_dir / "slidev-url.txt").write_text(state["slidev_url"], encoding="utf-8")
    return state


def _state_to_json(state: DefenseState) -> str:
    import json

    serializable = dict(state)
    if "graph" in serializable:
        serializable["graph"] = serializable["graph"].model_dump()
    if "issue" in serializable:
        serializable["issue"] = serializable["issue"].model_dump()
    return json.dumps(serializable, indent=2, ensure_ascii=False)
