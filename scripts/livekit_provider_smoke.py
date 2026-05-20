from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from devdefender_lab.audio_provider import LiveKitAudioProvider
from devdefender_lab.config import load_settings


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a minimal LiveKit provider credential/token smoke.")
    parser.add_argument("--room", default="devdefender-phase2", help="Room name for the generated join token.")
    parser.add_argument("--identity", default="devdefender-local", help="Participant identity for the join token.")
    parser.add_argument("--check-room", action="store_true", help="Call LiveKit room list API to verify connectivity.")
    args = parser.parse_args()

    provider = LiveKitAudioProvider(
        settings=load_settings(),
        room_name=args.room,
        identity=args.identity,
        check_room=args.check_room,
    )
    report = provider.smoke()
    print(report.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
