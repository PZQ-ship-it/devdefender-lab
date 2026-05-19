from __future__ import annotations

from enum import StrEnum
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


class Phase1Status(StrEnum):
    WAITING_FOR_FEEDBACK = "waiting_for_feedback"
    ANSWERING = "answering"
    REFINING = "refining"
    COMPLETE = "complete"


class Phase1Interrupt(BaseModel):
    thread_id: str
    message: str
    slidev_url: str
    graph_path: Path
    deck_path: Path
    node_count: int
    edge_count: int


class RefinementReport(BaseModel):
    status: str
    summary: str
    issue_title: str
    test_path: Path | None = None
    command: list[str] = Field(default_factory=list)
    return_code: int | None = None
    output: str = ""
    changed_files: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)


class LabArtifacts(BaseModel):
    graph_path: Path
    state_path: Path
    issue_path: Path
    slidev_url_path: Path
    deck_path: Path
    defense_path: Path
    session_path: Path
    refinement_path: Path
