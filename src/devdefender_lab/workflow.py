from __future__ import annotations

import json
from pathlib import Path
from typing import TypedDict
from uuid import uuid4

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, StateGraph
from langgraph.types import Command, interrupt

from devdefender_lab.config import Settings
from devdefender_lab.graph_store import create_graph_store
from devdefender_lab.models import CodeGraphPayload, DefenseIssue, Phase1Interrupt, Phase1Status, RefinementReport
from devdefender_lab.openai_client import draft_defense, extract_issue
from devdefender_lab.parser import parse_python_repo
from devdefender_lab.refiner import run_tdad_refinement


class DefenseState(TypedDict, total=False):
    thread_id: str
    repo_path: str
    feedback: str
    graph: dict
    defense: str
    issue: DefenseIssue
    refinement: RefinementReport
    slidev_url: str
    deck_path: str
    status: str


def build_graph(settings: Settings, checkpointer: InMemorySaver | None = None):
    graph = StateGraph(DefenseState)

    def prepare(state: DefenseState) -> DefenseState:
        repo_path = Path(state["repo_path"])
        payload = parse_python_repo(repo_path)
        store = create_graph_store(settings.graph_backend, settings.artifact_dir)
        store.save(payload)
        deck_path = write_phase1_deck(settings, payload, repo_path)
        slidev_url = f"http://127.0.0.1:{settings.slidev_port}"
        return {
            **state,
            "graph": payload.model_dump(),
            "deck_path": str(deck_path),
            "slidev_url": slidev_url,
            "status": Phase1Status.WAITING_FOR_FEEDBACK.value,
        }

    def wait_for_feedback(state: DefenseState) -> DefenseState:
        graph_payload = CodeGraphPayload.model_validate(state["graph"])
        feedback = interrupt(
            Phase1Interrupt(
                thread_id=state["thread_id"],
                message="Review the Slidev deck, then submit typed reviewer feedback.",
                slidev_url=state["slidev_url"],
                graph_path=settings.artifact_dir / "graph.json",
                deck_path=Path(state["deck_path"]),
                node_count=len(graph_payload.nodes),
                edge_count=len(graph_payload.edges),
            ).model_dump(mode="json")
        )
        return {**state, "feedback": str(feedback), "status": Phase1Status.ANSWERING.value}

    def defend(state: DefenseState) -> DefenseState:
        graph_payload = CodeGraphPayload.model_validate(state["graph"])
        answer = draft_defense(settings, graph_payload, state["feedback"])
        return {**state, "defense": answer}

    def issue(state: DefenseState) -> DefenseState:
        extracted = extract_issue(settings, state["feedback"], state["defense"])
        return {**state, "issue": extracted, "status": Phase1Status.REFINING.value}

    def refine(state: DefenseState) -> DefenseState:
        report = run_tdad_refinement(Path(state["repo_path"]), state["issue"], settings.artifact_dir)
        return {**state, "refinement": report, "status": Phase1Status.COMPLETE.value}

    graph.add_node("prepare", prepare)
    graph.add_node("wait_for_feedback", wait_for_feedback)
    graph.add_node("defend", defend)
    graph.add_node("extract_issue", issue)
    graph.add_node("refine", refine)
    graph.set_entry_point("prepare")
    graph.add_edge("prepare", "wait_for_feedback")
    graph.add_edge("wait_for_feedback", "defend")
    graph.add_edge("defend", "extract_issue")
    graph.add_edge("extract_issue", "refine")
    graph.add_edge("refine", END)
    return graph.compile(checkpointer=checkpointer or InMemorySaver())


def run_phase1(settings: Settings, repo_path: Path, feedback: str) -> DefenseState:
    session = start_phase1(settings, repo_path)
    return resume_phase1(session["app"], settings, session["thread_id"], feedback)


def start_phase1(settings: Settings, repo_path: Path, thread_id: str | None = None) -> dict[str, object]:
    settings.artifact_dir.mkdir(parents=True, exist_ok=True)
    thread_id = thread_id or f"phase1-{uuid4().hex[:12]}"
    checkpointer = InMemorySaver()
    app = build_graph(settings, checkpointer)
    config = _thread_config(thread_id)
    first = app.invoke({"thread_id": thread_id, "repo_path": str(repo_path)}, config)
    interrupt_payload = _interrupt_payload(first)
    (settings.artifact_dir / "slidev-url.txt").write_text(interrupt_payload["slidev_url"], encoding="utf-8")
    _write_session(
        settings,
        {
            "thread_id": thread_id,
            "status": Phase1Status.WAITING_FOR_FEEDBACK.value,
            "interrupt": interrupt_payload,
        },
    )
    return {
        "app": app,
        "thread_id": thread_id,
        "config": config,
        "interrupt": Phase1Interrupt.model_validate(interrupt_payload),
    }


def resume_phase1(app, settings: Settings, thread_id: str, feedback: str) -> DefenseState:
    state = app.invoke(Command(resume=feedback), _thread_config(thread_id))
    _write_outputs(settings, state)
    return state


def write_phase1_deck(settings: Settings, graph: CodeGraphPayload, repo_path: Path) -> Path:
    deck_dir = settings.artifact_dir / "deck"
    deck_dir.mkdir(parents=True, exist_ok=True)
    deck_path = deck_dir / "slides.md"
    functions = [node for node in graph.nodes if node.kind == "function"]
    imports = [node for node in graph.nodes if node.kind == "import"]
    call_edges = [edge for edge in graph.edges if edge.kind == "CALLS"]
    deck_path.write_text(
        "\n".join(
            [
                "---",
                "theme: default",
                "title: DevDefender Phase 1",
                "---",
                "",
                "# DevDefender Phase 1",
                "",
                f"Repository: `{repo_path.as_posix()}`",
                "",
                "Pure async code defense room",
                "",
                "---",
                "",
                "## Blackboard Pointers",
                "",
                f"- Graph artifact: `{(settings.artifact_dir / 'graph.json').as_posix()}`",
                f"- Functions parsed: **{len(functions)}**",
                f"- Imports parsed: **{len(imports)}**",
                f"- Call edges parsed: **{len(call_edges)}**",
                "",
                "---",
                "",
                "## Function Map",
                "",
                *_function_lines(functions),
                "",
                "---",
                "",
                "## Call Evidence",
                "",
                *_edge_lines(call_edges),
                "",
                "---",
                "",
                "## Human Feedback Gate",
                "",
                "LangGraph is interrupted here. Submit typed feedback in the local defense room to resume the graph.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return deck_path


def _function_lines(functions: list) -> list[str]:
    if not functions:
        return ["- No functions found."]
    return [f"- `{node.name}` in `{node.file}:{node.line}`" for node in functions[:15]]


def _edge_lines(edges: list) -> list[str]:
    if not edges:
        return ["- No local call edges found."]
    lines = []
    for edge in edges[:15]:
        source = edge.source.split(":function:")[-1]
        target = edge.target.split(":function:")[-1]
        lines.append(f"- `{source}` calls `{target}`")
    return lines


def _thread_config(thread_id: str) -> dict[str, dict[str, str]]:
    return {"configurable": {"thread_id": thread_id}}


def _interrupt_payload(result: DefenseState) -> dict:
    interrupts = result.get("__interrupt__")
    if not interrupts:
        raise RuntimeError("Phase 1 graph did not pause for reviewer feedback.")
    return dict(interrupts[0].value)


def _write_outputs(settings: Settings, state: DefenseState) -> None:
    (settings.artifact_dir / "state.json").write_text(_state_to_json(state), encoding="utf-8")
    (settings.artifact_dir / "defense.md").write_text(state["defense"], encoding="utf-8")
    (settings.artifact_dir / "issue.json").write_text(
        state["issue"].model_dump_json(indent=2),
        encoding="utf-8",
    )
    (settings.artifact_dir / "refinement.json").write_text(
        state["refinement"].model_dump_json(indent=2),
        encoding="utf-8",
    )
    _write_session(
        settings,
        {
            "thread_id": state["thread_id"],
            "status": state["status"],
            "slidev_url": state["slidev_url"],
            "issue_path": str(settings.artifact_dir / "issue.json"),
            "defense_path": str(settings.artifact_dir / "defense.md"),
            "refinement_path": str(settings.artifact_dir / "refinement.json"),
        },
    )


def _write_session(settings: Settings, payload: dict) -> None:
    (settings.artifact_dir / "session.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _state_to_json(state: DefenseState) -> str:
    serializable = dict(state)
    serializable.pop("__interrupt__", None)
    if "issue" in serializable:
        serializable["issue"] = serializable["issue"].model_dump()
    if "refinement" in serializable:
        serializable["refinement"] = serializable["refinement"].model_dump(mode="json")
    return json.dumps(serializable, indent=2, ensure_ascii=False)
