from __future__ import annotations

import json

from openai import OpenAI

from devdefender_lab.config import Settings
from devdefender_lab.evidence import dedupe_strings
from devdefender_lab.models import CodeGraphPayload, DefenseIssue


def require_openai_client(settings: Settings) -> OpenAI:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is required for real OpenAI smoke tests.")
    kwargs = {"api_key": settings.openai_api_key}
    if settings.openai_base_url:
        kwargs["base_url"] = settings.openai_base_url.rstrip("/")
    return OpenAI(**kwargs)


def draft_defense(settings: Settings, graph: CodeGraphPayload, feedback: str) -> str:
    if settings.llm_mode == "mock":
        functions = ", ".join(node.name for node in graph.nodes if node.kind == "function")
        return (
            "Mock defense: invalid payment amounts are blocked by validate_payment before "
            f"capture_payment returns a captured status. Graph functions: {functions}. "
            f"Reviewer feedback was: {feedback}"
        )
    client = require_openai_client(settings)
    graph_summary = {
        "nodes": [node.model_dump() for node in graph.nodes[:20]],
        "edges": [edge.model_dump() for edge in graph.edges[:20]],
    }
    messages = [
        {
            "role": "system",
            "content": "You are DevDefender. Ground every answer in the supplied code graph. Be concise.",
        },
        {
            "role": "user",
            "content": (
                "Code graph JSON:\n"
                f"{json.dumps(graph_summary, ensure_ascii=False)}\n\n"
                f"Reviewer challenge: {feedback}\n\n"
                "Return a short defense answer and cite function names when possible."
            ),
        },
    ]
    return _create_text(settings, client, messages)


def extract_issue(settings: Settings, feedback: str, defense: str, evidence_pointers: list[str] | None = None) -> DefenseIssue:
    pointers = dedupe_strings(evidence_pointers or [])
    if settings.llm_mode == "mock":
        return DefenseIssue(
            title="Add evidence for payment validation defense",
            body=(
                "The typed feedback questioned whether invalid payments can be captured. "
                "Add or strengthen tests around validate_payment and capture_payment."
            ),
            labels=["devdefender", "phase-1", "test-coverage"],
            evidence=dedupe_strings([feedback, defense[:160], *pointers]),
        )
    client = require_openai_client(settings)
    messages = [
        {
            "role": "system",
            "content": "Extract one actionable GitHub issue as strict JSON only.",
        },
        {
            "role": "user",
            "content": (
                "Typed reviewer feedback:\n"
                f"{feedback}\n\n"
                "Defense answer:\n"
                f"{defense}\n\n"
                "Validated evidence pointers:\n"
                f"{json.dumps(pointers, ensure_ascii=False)}\n\n"
                "JSON schema: {\"title\": str, \"body\": str, \"labels\": [str], \"evidence\": [str]}"
            ),
        },
    ]
    raw = _create_text(settings, client, messages).strip()
    if raw.startswith("```"):
        raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    issue = DefenseIssue.model_validate_json(raw)
    return issue.model_copy(update={"evidence": dedupe_strings([*issue.evidence, *pointers])})


def _create_text(settings: Settings, client: OpenAI, messages: list[dict[str, str]]) -> str:
    if settings.openai_base_url:
        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=messages,
        )
        content = response.choices[0].message.content
        if not content:
            raise RuntimeError("Chat completions response did not include message content.")
        return content.strip()

    response = client.responses.create(
        model=settings.openai_model,
        input=messages,
    )
    return response.output_text.strip()
