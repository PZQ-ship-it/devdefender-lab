from __future__ import annotations

import json
import subprocess
from pathlib import Path

from devdefender_lab.briefing import (
    BriefingContext,
    BriefingDiagramRequest,
    BriefingEvidencePointer,
    BriefingExperimentResult,
    BriefingFollowUpTask,
    BriefingProgressItem,
    BriefingQuestion,
    BriefingRequirementCoverage,
    BriefingRisk,
    ProjectBriefingReport,
    contains_forbidden_briefing_artifact_fields,
)
from devdefender_lab.briefing_contract import DEFAULT_AGENT_BRIEFING_INPUT, load_agent_briefing_input, merge_agent_input
from devdefender_lab.evidence import dedupe_strings


DOC_CANDIDATES = ("README.md", "plan.md")
ARTIFACT_CANDIDATES = (
    "artifacts/project_briefing_room/session.json",
    "artifacts/project_briefing_room/briefing_deck/briefing_report.json",
    "artifacts/project_briefing_room/briefing_feedback_plan.json",
    "artifacts/project_briefing_room/briefing_execution_gate.json",
)
STALE_FACT_MARKERS = (
    "livekit",
    "openclaude",
    "phase1",
    "phase2",
    "phase3",
    "phase4",
    "room_acceptance",
    "audio_provider",
    "tts_",
    "webrtc",
    "zoom",
)
MOJIBAKE_MARKERS = (
    "\u00c3",
    "\u00c2",
    "\u00e2\u20ac",
    "\u951b",
    "\u9286",
    "\u9225",
    "\u7efe",
    "\u6d93",
    "\u8930",
    "\u9429",
    "\u9a9e",
)


class WorkspaceBriefingAdapter:
    backend = "workspace-briefing-adapter"

    def __init__(self, repo_path: Path | str = ".", agent_input_path: Path | str | None = None) -> None:
        self.repo_path = Path(repo_path).resolve()
        self.agent_input_path = Path(agent_input_path) if agent_input_path else self.repo_path / DEFAULT_AGENT_BRIEFING_INPUT

    def build_context(self) -> BriefingContext:
        changed_files = self._changed_files()
        docs = self._present_docs()
        artifacts = self._present_artifacts()
        accepted_lines = self._accepted_lines(docs)
        artifact_facts = self._artifact_facts(artifacts)
        task_goal = self._task_goal(docs)
        context = BriefingContext(
            project_name=self.repo_path.name or "Workspace Project",
            task_goal=task_goal,
            current_task=self._current_task(docs),
            repo_path=self._display_path(self.repo_path),
            changed_files=changed_files[:100],
            completed_work=self._completed_work_facts(accepted_lines, artifact_facts),
            in_progress_work=self._in_progress_work_facts(changed_files),
            blockers=[],
            next_steps=self._next_step_facts(docs),
            requirements=[
                "Report on the current VS Code workspace.",
                "Avoid private extension APIs.",
                "Keep the feedback-to-plan loop local and lightweight.",
            ],
            tests=self._test_facts(accepted_lines, artifact_facts),
            artifacts=artifacts,
            docs=docs,
            architecture_facts=self._architecture_facts(docs, artifact_facts),
            experiment_facts=self._experiment_facts(accepted_lines, artifact_facts),
            risks=self._risk_facts(changed_files, artifacts),
            open_questions=[],
            constraints=[
                "Do not read or report .env contents.",
                "Do not expose raw provider tokens, cookies, raw audio, or full transcripts.",
                "Use structured repo/docs/artifact evidence instead of private Codex chat history.",
            ],
            evidence_pointers=self._evidence_pointers(artifacts),
        )
        return merge_agent_input(context, load_agent_briefing_input(self.agent_input_path))

    def build_report(self, context: BriefingContext | None = None) -> ProjectBriefingReport:
        context = context or self.build_context()
        pointers = context.evidence_pointers or [
            "timeline://workspace#event=0&kind=briefing_generated",
            "slide://workspace#page=1",
        ]
        primary_pointer = pointers[0]
        slide_pointer = next((pointer for pointer in pointers if pointer.startswith("slide://")), pointers[-1])
        dirty_count = len(context.changed_files)
        artifact_count = len(context.artifacts)
        docs_count = len(context.docs)
        return ProjectBriefingReport(
            project_name=context.project_name,
            task_goal=context.task_goal,
            generated_by=self.backend,
            audience_summary=(
                f"{context.project_name} now has a workspace-based project briefing path. "
                f"The adapter found {dirty_count} changed file(s), {docs_count} planning/doc source(s), "
                f"and {artifact_count} recent product artifact(s). The briefing is grounded in repo-visible "
                f"facts rather than private chat history.{_agent_task_sentence(context.current_task)}"
            ),
            architecture_diagrams=[
                BriefingDiagramRequest(
                    diagram_id="workspace-briefing-flow",
                    title="Workspace Briefing Flow",
                    kind="architecture",
                    audience_goal=(
                        "Show how VS Code Codex triggers the product skill, the workspace adapter gathers repo facts, "
                        "and the existing runtime turns those facts into a briefing and updated execution plan."
                    ),
                    mermaid_hint=(
                        "flowchart LR\n"
                        "  Codex[VS Code Codex skill] --> Adapter[WorkspaceBriefingAdapter]\n"
                        "  Adapter --> Repo[git status docs artifacts]\n"
                        "  Adapter --> Report[ProjectBriefingReport]\n"
                        "  Report --> Deck[Markdown and Mermaid briefing deck]\n"
                        "  Deck --> Feedback[Stakeholder feedback plan]\n"
                        "  Feedback --> Gate[Execution gate]"
                    ),
                    evidence_pointers=[primary_pointer, slide_pointer],
                )
            ],
            progress_status=[
                BriefingProgressItem(
                    label="Workspace fact collection",
                    status="done",
                    plain_language_summary=(
                        f"The adapter collected visible repo state, including {dirty_count} changed file(s), "
                        f"{docs_count} docs, and {artifact_count} artifacts."
                    ),
                    evidence_pointers=[primary_pointer],
                ),
                BriefingProgressItem(
                    label="VS Code Codex skill path",
                    status="in_progress",
                    plain_language_summary=(
                        "The skill can be installed and invoked from Codex; this iteration switches the briefing "
                        "content from deterministic mock facts to current workspace facts."
                    ),
                    evidence_pointers=[slide_pointer],
                ),
                *self._agent_progress_items(context, primary_pointer),
                BriefingProgressItem(
                    label="Feedback closure runtime",
                    status="done" if artifact_count else "planned",
                    plain_language_summary=(
                        "Existing product artifacts show the briefing deck, feedback plan, plan update, and execution gate. "
                        "If artifacts are absent, the smoke can regenerate them."
                    ),
                    evidence_pointers=[primary_pointer],
                ),
            ],
            requirements_coverage=[
                BriefingRequirementCoverage(
                    requirement="Report on the current VS Code workspace",
                    status="met",
                    explanation="The workspace backend reads repo files, git state, docs, and artifacts from the selected repo path.",
                    evidence_pointers=[primary_pointer],
                ),
                BriefingRequirementCoverage(
                    requirement="Avoid private extension APIs",
                    status="met",
                    explanation="The adapter uses filesystem and git facts, so it does not depend on VS Code or Codex private APIs.",
                    evidence_pointers=[slide_pointer],
                ),
                BriefingRequirementCoverage(
                    requirement="Keep the feedback-to-plan loop local and lightweight",
                    status="met",
                    explanation="The backend only changes the briefing report source; the local feedback and execution gates remain reusable.",
                    evidence_pointers=[primary_pointer],
                ),
                *self._agent_requirement_coverage(context, primary_pointer),
            ],
            experiment_results=[
                BriefingExperimentResult(
                    name="Workspace briefing quick gate",
                    status="not_run",
                    summary=(
                        "Run the product smoke with --agent-backend workspace to validate workspace report, deck, "
                        "feedback plan, plan update, and execution gate without credentials."
                    ),
                    command=(
                        "scripts/project_briefing_room_smoke.py --agent-backend workspace --repo ."
                    ),
                    evidence_pointers=[slide_pointer],
                ),
                *self._artifact_experiment_results(context.experiment_facts, primary_pointer),
            ][:20],
            risks_and_unknowns=[
                *self._agent_risks(context),
                BriefingRisk(
                    risk="Workspace facts may be incomplete when important context only exists in chat history.",
                    severity="medium",
                    mitigation="State this limitation in the briefing and rely on docs/artifacts when available.",
                    decision_needed=False,
                ),
                BriefingRisk(
                    risk="Large dirty worktrees can make the briefing noisy.",
                    severity="low",
                    mitigation="Summarize only the first bounded set of changed files and ask for focus if needed.",
                    decision_needed=False,
                ),
            ],
            stakeholder_questions=[
                *self._agent_questions(context),
                BriefingQuestion(
                    question="Should the next adapter read an external agent trace such as Aider?",
                    why_it_matters="Workspace facts are useful, but external traces would explain agent intent and decisions.",
                    options=["Keep workspace-only for now", "Add Aider trace", "Use generic JSON input"],
                )
            ],
            follow_up_tasks=[
                *self._agent_follow_up_tasks(context, slide_pointer),
                BriefingFollowUpTask(
                    task="Run the workspace backend quick smoke from VS Code Codex.",
                    owner_hint="codex",
                    priority="high",
                    evidence_pointers=[slide_pointer],
                ),
                BriefingFollowUpTask(
                    task="Run the product doctor after workspace smoke passes.",
                    owner_hint="codex",
                    priority="medium",
                    evidence_pointers=[primary_pointer],
                ),
            ],
            evidence_pointers=[
                BriefingEvidencePointer(pointer=primary_pointer, label="Workspace timeline evidence pointer"),
                BriefingEvidencePointer(pointer=slide_pointer, label="Workspace slide evidence pointer"),
            ],
        )

    def _changed_files(self) -> list[str]:
        process = subprocess.run(
            ["git", "status", "--short"],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if process.returncode != 0:
            return []
        files: list[str] = []
        for raw in process.stdout.splitlines():
            line = raw.strip()
            if not line:
                continue
            path = line[3:] if len(line) > 3 else line
            files.append(path.strip())
        return dedupe_strings(files)

    def _present_docs(self) -> list[str]:
        return [name for name in DOC_CANDIDATES if (self.repo_path / name).exists()]

    def _present_artifacts(self) -> list[str]:
        return [name for name in ARTIFACT_CANDIDATES if (self.repo_path / name).exists()]

    def _accepted_lines(self, docs: list[str]) -> list[str]:
        lines: list[str] = []
        for doc in docs:
            text = self._safe_read(self.repo_path / doc)
            for raw in text.splitlines():
                if _looks_like_accepted_line(raw):
                    lines.append(f"{doc}: {raw.strip()}")
        return dedupe_strings(lines)[:30]

    def _artifact_facts(self, artifacts: list[str]) -> list[str]:
        facts: list[str] = []
        for artifact in artifacts:
            payload = self._safe_json(self.repo_path / artifact)
            if not payload:
                continue
            if payload.get("ok") is True:
                facts.append(f"{artifact}: ok true")
            checks = payload.get("checks")
            if isinstance(checks, dict):
                passed = [key for key, value in checks.items() if value is True]
                if passed:
                    facts.append(f"{artifact}: passed checks {', '.join(passed[:8])}")
            if isinstance(payload.get("evidence"), list):
                facts.append(f"{artifact}: evidence items {len(payload['evidence'])}")
            if isinstance(payload.get("findings"), list):
                facts.append(f"{artifact}: secret findings {len(payload['findings'])}")
        return dedupe_strings(facts)[:30]

    def _task_goal(self, docs: list[str]) -> str:
        for doc in ("README.md", "plan.md"):
            if doc not in docs:
                continue
            text = self._safe_read(self.repo_path / doc)
            for line in text.splitlines():
                stripped = line.strip("# ").strip()
                if _is_stale_fact(stripped):
                    continue
                if "workspace briefing adapter" in stripped.lower() or "project briefing room" in stripped.lower():
                    return _clip(stripped, 380)
        return "Brief the current workspace status using repo-visible project facts."

    def _current_task(self, docs: list[str]) -> str | None:
        for doc in ("README.md", "plan.md"):
            if doc not in docs:
                continue
            text = self._safe_read(self.repo_path / doc)
            for line in text.splitlines():
                stripped = line.strip("# -").strip()
                if _is_stale_fact(stripped):
                    continue
                if stripped.lower().startswith(("next implementation target", "next target", "remaining product gaps")):
                    return _clip(stripped, 380)
        return None

    def _completed_work_facts(self, accepted_lines: list[str], artifact_facts: list[str]) -> list[str]:
        facts = [line for line in accepted_lines if "accepted" in line.lower() or "ok: true" in line.lower()]
        facts.extend(fact for fact in artifact_facts if "ok true" in fact)
        return _bounded_facts(facts, max_items=20)

    def _in_progress_work_facts(self, changed_files: list[str]) -> list[str]:
        if not changed_files:
            return []
        return [f"Workspace has pending edits across {len(changed_files)} file(s)."]

    def _next_step_facts(self, docs: list[str]) -> list[str]:
        facts: list[str] = []
        for doc in docs:
            text = self._safe_read(self.repo_path / doc)
            for line in text.splitlines():
                stripped = line.strip()
                if stripped.lower().startswith(("next implementation target", "next target")):
                    if not _is_stale_fact(stripped):
                        facts.append(f"{doc}: {stripped}")
        return _bounded_facts(facts, max_items=10)

    def _test_facts(self, accepted_lines: list[str], artifact_facts: list[str]) -> list[str]:
        facts = [line for line in accepted_lines if "pytest" in line.lower() or "passed" in line.lower()]
        facts.extend(fact for fact in artifact_facts if "ok true" in fact or "passed checks" in fact)
        return _bounded_facts(facts, max_items=20) or ["No accepted test result was found in docs or artifacts."]

    def _architecture_facts(self, docs: list[str], artifact_facts: list[str]) -> list[str]:
        facts = []
        if "skills/project-briefing-room/SKILL.md" in self._changed_files():
            facts.append("The project includes a repo-versioned Codex skill for Project Briefing Room.")
        if "README.md" in docs:
            facts.append("README documents the Product Briefing Room direction and VS Code Codex install path.")
        facts.extend(fact for fact in artifact_facts if "artifacts/project_briefing_room/" in fact)
        return _bounded_facts(facts, max_items=20) or ["Workspace facts are gathered through docs, git status, and artifacts."]

    def _experiment_facts(self, accepted_lines: list[str], artifact_facts: list[str]) -> list[str]:
        facts = [line for line in accepted_lines if "accepted" in line.lower() or "observed result" in line.lower()]
        facts.extend(artifact_facts)
        return _bounded_facts(facts, max_items=30) or ["No recent experiment artifact was found."]

    def _risk_facts(self, changed_files: list[str], artifacts: list[str]) -> list[str]:
        risks = []
        if changed_files:
            risks.append(f"Workspace has {len(changed_files)} changed file(s); briefing should distinguish completed work from pending edits.")
        if not artifacts:
            risks.append("No prior product artifacts were found; product smoke should be run before continuing implementation.")
        risks.append("Workspace backend cannot read private Codex chat history by design.")
        return risks

    def _evidence_pointers(self, artifacts: list[str]) -> list[str]:
        if "artifacts/project_briefing_room/briefing_deck/briefing_report.json" in artifacts:
            payload = self._safe_json(self.repo_path / "artifacts/project_briefing_room/briefing_deck/briefing_report.json")
            evidence = payload.get("evidence_pointers")
            if isinstance(evidence, list):
                pointers: list[str] = []
                for item in evidence:
                    if isinstance(item, str):
                        pointers.append(item)
                    elif isinstance(item, dict) and isinstance(item.get("pointer"), str):
                        pointers.append(item["pointer"])
                if pointers:
                    return dedupe_strings(pointers)[:12]
        return ["timeline://workspace#event=0&kind=briefing_generated", "slide://workspace#page=1"]

    def _artifact_experiment_results(self, facts: list[str], pointer: str) -> list[BriefingExperimentResult]:
        results = []
        for fact in facts[:4]:
            status = "passed" if "ok true" in fact.lower() or "passed" in fact.lower() else "inconclusive"
            results.append(
                BriefingExperimentResult(
                    name=_clip(fact.split(":", 1)[0], 120),
                    status=status,
                    summary=_clip(fact, 450),
                    evidence_pointers=[pointer],
                )
            )
        return results

    def _agent_progress_items(self, context: BriefingContext, pointer: str) -> list[BriefingProgressItem]:
        items: list[BriefingProgressItem] = []
        for fact in context.completed_work[:4]:
            items.append(
                BriefingProgressItem(
                    label=_clip(fact.split(":", 1)[0], 120),
                    status="done",
                    plain_language_summary=_clip(fact, 500),
                    evidence_pointers=[pointer],
                )
            )
        for fact in context.in_progress_work[:4]:
            items.append(
                BriefingProgressItem(
                    label=_clip(fact.split(":", 1)[0], 120),
                    status="in_progress",
                    plain_language_summary=_clip(fact, 500),
                    evidence_pointers=[pointer],
                )
            )
        for fact in context.blockers[:4]:
            items.append(
                BriefingProgressItem(
                    label=_clip(fact.split(":", 1)[0], 120),
                    status="blocked",
                    plain_language_summary=_clip(fact, 500),
                    evidence_pointers=[pointer],
                )
            )
        return items[:8]

    def _agent_requirement_coverage(self, context: BriefingContext, pointer: str) -> list[BriefingRequirementCoverage]:
        return [
            BriefingRequirementCoverage(
                requirement=_clip(requirement, 160),
                status="unknown",
                explanation="This requirement was supplied by the code agent input contract and needs stakeholder confirmation or evidence-backed classification.",
                evidence_pointers=[pointer],
            )
            for requirement in context.requirements[:6]
        ]

    def _agent_risks(self, context: BriefingContext) -> list[BriefingRisk]:
        return [
            BriefingRisk(
                risk=_clip(risk, 240),
                severity="medium",
                mitigation="Review this risk during the briefing and decide whether it changes the next implementation step.",
                decision_needed=True,
            )
            for risk in context.blockers[:4]
        ]

    def _agent_questions(self, context: BriefingContext) -> list[BriefingQuestion]:
        return [
            BriefingQuestion(
                question=_clip(question, 240),
                why_it_matters="This was supplied by the code agent as a point where stakeholder input can change the next step.",
                options=[],
            )
            for question in context.open_questions[:4]
        ]

    def _agent_follow_up_tasks(self, context: BriefingContext, pointer: str) -> list[BriefingFollowUpTask]:
        return [
            BriefingFollowUpTask(
                task=_clip(task, 240),
                owner_hint="code-agent",
                priority="high" if index == 0 else "medium",
                evidence_pointers=[pointer],
            )
            for index, task in enumerate(context.next_steps[:6])
        ]

    def _safe_read(self, path: Path) -> str:
        if path.name == ".env" or ".env" in path.parts:
            return ""
        try:
            return path.read_text(encoding="utf-8", errors="ignore")[:20000]
        except OSError:
            return ""

    def _safe_json(self, path: Path) -> dict[str, object]:
        text = self._safe_read(path)
        if not text:
            return {}
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return {}
        if not isinstance(payload, dict):
            return {}
        if contains_forbidden_briefing_artifact_fields(payload):
            return {}
        return payload

    def _display_path(self, path: Path) -> str:
        try:
            return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
        except ValueError:
            return path.as_posix()


def _looks_like_accepted_line(line: str) -> bool:
    lowered = line.lower()
    if _is_stale_fact(line):
        return False
    if lowered.strip(": ").endswith(("accepted command", "accepted commands", "accepted result", "observed result")):
        return False
    return any(
        marker in lowered
        for marker in (
            "accepted command",
            "accepted result",
            "observed result",
            "passed",
            "ok: true",
            "pytest",
        )
    )


def _clip(value: str, max_length: int) -> str:
    text = " ".join(value.split())
    return text[: max(0, max_length - 3)] + "..." if len(text) > max_length else text


def _bounded_facts(values: list[str], *, max_items: int, max_length: int = 360) -> list[str]:
    return [_clip(value, max_length) for value in dedupe_strings(value for value in values if not _is_stale_fact(value))[:max_items]]


def _agent_task_sentence(current_task: str | None) -> str:
    if not current_task:
        return ""
    return f" Current task focus: {_clip(current_task, 280)}"


def _is_stale_fact(value: str) -> bool:
    lowered = value.lower()
    if any(marker in lowered for marker in STALE_FACT_MARKERS):
        return True
    if any(marker in value for marker in MOJIBAKE_MARKERS):
        return True
    replacement_like_count = value.count("?") + value.count("\ufffd")
    return replacement_like_count > 2
