from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

import networkx as nx

from devdefender_lab.models import CodeEdge, CodeGraphPayload, CodeNode


class GraphStore(Protocol):
    def save(self, payload: CodeGraphPayload) -> None:
        ...

    def load(self) -> CodeGraphPayload:
        ...

    def search(self, query: str) -> CodeGraphPayload:
        ...


class EmbeddedGraphStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.graph = nx.DiGraph()

    def save(self, payload: CodeGraphPayload) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.graph.clear()
        for node in payload.nodes:
            self.graph.add_node(node.id, **node.model_dump())
        for edge in payload.edges:
            self.graph.add_edge(edge.source, edge.target, kind=edge.kind)
        self.path.write_text(payload.model_dump_json(indent=2), encoding="utf-8")

    def load(self) -> CodeGraphPayload:
        if not self.path.exists():
            return CodeGraphPayload()
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        return CodeGraphPayload.model_validate(raw)

    def search(self, query: str) -> CodeGraphPayload:
        payload = self.load()
        needle = query.lower()
        nodes = [
            node
            for node in payload.nodes
            if needle in node.name.lower() or needle in node.file.lower() or needle in node.kind.lower()
        ]
        node_ids = {node.id for node in nodes}
        edges = [
            edge
            for edge in payload.edges
            if edge.source in node_ids or edge.target in node_ids or needle in edge.kind.lower()
        ]
        edge_node_ids = {edge.source for edge in edges} | {edge.target for edge in edges}
        expanded_nodes = [node for node in payload.nodes if node.id in node_ids | edge_node_ids]
        return CodeGraphPayload(nodes=expanded_nodes, edges=edges)


class MemgraphGraphStore:
    def __init__(self, uri: str) -> None:
        self.uri = uri

    def save(self, payload: CodeGraphPayload) -> None:
        raise RuntimeError("Memgraph backend is a Phase 2 adapter boundary; use DEVDEFENDER_GRAPH_BACKEND=embedded now.")

    def load(self) -> CodeGraphPayload:
        raise RuntimeError("Memgraph backend is a Phase 2 adapter boundary; use DEVDEFENDER_GRAPH_BACKEND=embedded now.")

    def search(self, query: str) -> CodeGraphPayload:
        raise RuntimeError("Memgraph backend is a Phase 2 adapter boundary; use DEVDEFENDER_GRAPH_BACKEND=embedded now.")


def create_graph_store(backend: str, artifact_dir: Path) -> GraphStore:
    if backend == "embedded":
        return EmbeddedGraphStore(artifact_dir / "graph.json")
    if backend == "memgraph":
        return MemgraphGraphStore("bolt://localhost:7687")
    raise ValueError(f"Unsupported graph backend: {backend}")
