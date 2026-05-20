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


class AgentAcceptance(BaseModel):
    must_write_test_first: bool = True
    must_pass_existing_tests: bool = True
    must_return_patch_only: bool = True


class AgentTaskEnvelope(BaseModel):
    issue: DefenseIssue
    repo_commit_hash: str
    graph_path: Path
    allowed_paths: list[str]
    required_tests: list[str]
    evidence_pointers: list[str] = Field(default_factory=list)
    acceptance: AgentAcceptance = Field(default_factory=AgentAcceptance)
    agent_backend: str = "mock"


class AgentRunReport(BaseModel):
    backend: str
    status: str
    summary: str
    changed_files: list[str] = Field(default_factory=list)
    command: list[str] = Field(default_factory=list)
    return_code: int | None = None
    output: str = ""
    violations: list[str] = Field(default_factory=list)
    plan_path: Path | None = None
    patch_path: Path | None = None
    test_report_path: Path | None = None
    trace_path: Path | None = None
    workspace: Path | None = None
    commit_hash: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


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
    agent_backend: str = "mock"
    agent_task_path: Path | None = None
    agent_patch_path: Path | None = None
    agent_test_report_path: Path | None = None
    agent_trace_path: Path | None = None
    violations: list[str] = Field(default_factory=list)


class LabArtifacts(BaseModel):
    graph_path: Path
    state_path: Path
    issue_path: Path
    slidev_url_path: Path
    deck_path: Path
    defense_path: Path
    session_path: Path
    refinement_path: Path
