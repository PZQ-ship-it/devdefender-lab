from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACT_DIR = ROOT / "artifacts"
DEFAULT_ENV_PATH = ROOT / ".env"
DEFAULT_SECRET_NAMES = (
    "OPENAI_API_KEY",
    "LIVEKIT_API_KEY",
    "LIVEKIT_API_SECRET",
    "GH_TOKEN",
)
SKIP_DIRS = {"workspaces", "input_repo", "node_modules", "__pycache__", ".pytest_cache"}
BINARY_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".zip", ".gz", ".tar", ".7z", ".exe", ".dll"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Scan generated artifacts for raw secret values from .env.")
    parser.add_argument("--artifact-dir", type=Path, default=DEFAULT_ARTIFACT_DIR, help="Artifact directory to scan.")
    parser.add_argument("--env", type=Path, default=DEFAULT_ENV_PATH, help=".env file used as the secret source.")
    parser.add_argument(
        "--secret-name",
        action="append",
        dest="secret_names",
        help="Environment variable name to scan. Can be repeated. Defaults to known secret names.",
    )
    args = parser.parse_args()

    secret_names = tuple(args.secret_names or DEFAULT_SECRET_NAMES)
    secrets = load_secret_values(args.env, secret_names)
    report = build_report(args.artifact_dir, args.env, secret_names, secrets)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if not report["ok"]:
        raise SystemExit(1)


def build_report(
    artifact_dir: Path,
    env_path: Path,
    secret_names: tuple[str, ...],
    secrets: dict[str, str],
) -> dict[str, object]:
    findings = scan_artifacts(artifact_dir, secrets)
    return {
        "ok": not findings,
        "artifact_dir": str(artifact_dir),
        "env_path": str(env_path),
        "checked_secret_names": list(secret_names),
        "loaded_secret_count": len(secrets),
        "scanned_file_count": len(list(iter_scannable_files(artifact_dir))),
        "findings": findings,
    }


def load_secret_values(env_path: Path, names: tuple[str, ...]) -> dict[str, str]:
    if not env_path.exists():
        return {}
    values: dict[str, str] = {}
    wanted = set(names)
    for raw_line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        if name not in wanted:
            continue
        cleaned = _clean_env_value(value)
        if is_scannable_secret(cleaned):
            values[name] = cleaned
    return values


def scan_artifacts(artifact_dir: Path, secrets: dict[str, str]) -> list[dict[str, object]]:
    if not artifact_dir.exists():
        return []
    findings: list[dict[str, object]] = []
    for path in iter_scannable_files(artifact_dir):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for name, value in secrets.items():
            if value in text:
                findings.append(
                    {
                        "secret_name": name,
                        "path": str(path),
                        "relative_path": str(path.relative_to(artifact_dir)),
                    }
                )
    return findings


def iter_scannable_files(artifact_dir: Path) -> list[Path]:
    if not artifact_dir.exists():
        return []
    files: list[Path] = []
    for path in artifact_dir.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() in BINARY_SUFFIXES:
            continue
        files.append(path)
    return files


def is_scannable_secret(value: str) -> bool:
    return len(value) >= 8 and not value.lower().startswith(("example", "changeme", "placeholder"))


def _clean_env_value(value: str) -> str:
    cleaned = value.strip()
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in {"'", '"'}:
        cleaned = cleaned[1:-1]
    return cleaned


if __name__ == "__main__":
    main()
