from __future__ import annotations

import argparse
import os
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
THIRD_PARTY = ROOT / "third_party"
SRC_DIR = THIRD_PARTY / "src"
REPORT_DIR = THIRD_PARTY / "reports"
MANIFEST = THIRD_PARTY / "manifest.yml"


@dataclass
class Result:
    name: str
    phase: int
    status: str
    repo: str
    path: str
    commit: str | None
    smoke: dict[str, Any]
    seconds: float
    output: str


def main() -> None:
    parser = argparse.ArgumentParser(description="Clone and smoke-test third-party libraries.")
    parser.add_argument("--phase", type=int, help="Run libraries in one phase.")
    parser.add_argument("--name", help="Run one library by name.")
    parser.add_argument("--list", action="store_true", help="List manifest entries.")
    parser.add_argument("--clone-only", action="store_true", help="Clone and record commit without running smoke commands.")
    args = parser.parse_args()

    libraries = load_manifest()
    selected = select_libraries(libraries, args.phase, args.name)

    if args.list:
        for item in selected:
            print(f"phase {item['phase']}: {item['name']} -> {item['repo']}")
        return

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    results = [bring_up(item, clone_only=args.clone_only) for item in selected]
    report_path = REPORT_DIR / f"third_party_smoke_{timestamp()}.json"
    report_path.write_text(
        json.dumps([result.__dict__ for result in results], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Wrote report: {report_path.relative_to(ROOT)}")
    for result in results:
        print(f"{result.status:8} phase {result.phase} {result.name} {result.commit or '-'}")

    if any(result.status == "FAIL" for result in results):
        sys.exit(1)


def load_manifest() -> list[dict[str, Any]]:
    raw = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    return raw["libraries"]


def select_libraries(libraries: list[dict[str, Any]], phase: int | None, name: str | None) -> list[dict[str, Any]]:
    selected = libraries
    if phase is not None:
        selected = [item for item in selected if item["phase"] == phase]
    if name:
        selected = [item for item in selected if item["name"] == name]
    if not selected:
        raise SystemExit("No libraries matched the selection.")
    return selected


def bring_up(item: dict[str, Any], clone_only: bool) -> Result:
    start = time.monotonic()
    name = item["name"]
    path = SRC_DIR / name
    output_parts: list[str] = []
    status = "PASS"
    commit = None

    try:
        clone_or_fetch(item["repo"], path, output_parts)
        commit = git_commit(path)
        smoke = item["smoke"]
        if clone_only:
            status = "CLONED"
        elif smoke["kind"] == "blocked":
            status = "BLOCKED"
            output_parts.append(smoke["reason"])
        else:
            run_smoke(smoke, path, output_parts)
    except Exception as exc:
        status = "FAIL"
        output_parts.append(str(exc))

    return Result(
        name=name,
        phase=int(item["phase"]),
        status=status,
        repo=item["repo"],
        path=str(path.relative_to(ROOT)),
        commit=commit,
        smoke=item["smoke"],
        seconds=round(time.monotonic() - start, 3),
        output="\n".join(output_parts).strip(),
    )


def clone_or_fetch(repo: str, path: Path, output_parts: list[str]) -> None:
    SRC_DIR.mkdir(parents=True, exist_ok=True)
    if path.exists():
        try:
            result = run(["git", "-C", str(path), "fetch", "--depth", "1", "origin"], cwd=ROOT)
            output_parts.append(result)
        except RuntimeError as exc:
            output_parts.append(f"Fetch failed; using existing clone.\n{exc}")
        return
    result = run(["git", "clone", "--depth", "1", repo, str(path)], cwd=ROOT)
    output_parts.append(result)


def git_commit(path: Path) -> str:
    return run(["git", "-C", str(path), "rev-parse", "HEAD"], cwd=ROOT).strip()


def run_smoke(smoke: dict[str, Any], path: Path, output_parts: list[str]) -> None:
    kind = smoke["kind"]
    if kind == "python_import":
        module = smoke["module"]
        command = [sys.executable, "-c", f"import {module}; print('{module} import ok')"]
        output_parts.append(run(command, cwd=ROOT))
        return
    if kind in {"command", "npm_exec"}:
        cwd = ROOT if smoke.get("cwd") == "root" else path
        output_parts.append(run_powershell(smoke["command"], cwd=cwd))
        return
    raise ValueError(f"Unsupported smoke kind: {kind}")


def run(command: list[str], cwd: Path) -> str:
    completed = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"Command failed ({completed.returncode}): {' '.join(command)}\n{completed.stdout}")
    return completed.stdout


def run_powershell(command: str, cwd: Path) -> str:
    env = os.environ.copy()
    scripts_dir = str(Path(sys.executable).resolve().parent)
    env["PATH"] = scripts_dir + os.pathsep + env.get("PATH", "")
    command = command.replace("python ", f'& "{sys.executable}" ')
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-Command", command],
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"Command failed ({completed.returncode}): {command}\n{completed.stdout}")
    return completed.stdout


def timestamp() -> str:
    return time.strftime("%Y%m%d_%H%M%S")


if __name__ == "__main__":
    main()
