from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field


class CodeNode(BaseModel):
    id: str
    kind: str
    name: str
    file: str
    line: int


class CodeEdge(BaseModel):
    source: str
    target: str
    kind: str


class CodeGraphPayload(BaseModel):
    nodes: list[CodeNode] = Field(default_factory=list)
    edges: list[CodeEdge] = Field(default_factory=list)


class DefenseIssue(BaseModel):
    title: str
    body: str
    labels: list[str]
    evidence: list[str]


class LabArtifacts(BaseModel):
    graph_path: Path
    state_path: Path
    issue_path: Path
    slidev_url_path: Path
