from __future__ import annotations

import argparse
import base64
import json
import sys
import urllib.request
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Request a browser LiveKit token from the local DevDefender room.")
    parser.add_argument("--room-url", default="http://127.0.0.1:8765", help="Running DevDefender room URL.")
    parser.add_argument("--room", default="devdefender-phase2", help="LiveKit room name.")
    parser.add_argument("--identity", default="devdefender-browser-smoke", help="LiveKit participant identity.")
    args = parser.parse_args()

    payload = _post_json(
        f"{args.room_url.rstrip('/')}/api/livekit-token",
        {"room": args.room, "identity": args.identity},
    )
    if not payload.get("ok"):
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        raise SystemExit(1)

    claims = _decode_jwt_payload(str(payload["token"]))
    video_grants = claims.get("video", {})
    result = {
        "ok": True,
        "url": payload.get("url"),
        "room_name": payload.get("room_name"),
        "identity": payload.get("identity"),
        "token_length": payload.get("token_length"),
        "claim_identity": claims.get("sub"),
        "claim_room": video_grants.get("room"),
        "claim_room_join": video_grants.get("roomJoin"),
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if result["claim_identity"] != args.identity or result["claim_room"] != args.room or not result["claim_room_join"]:
        raise SystemExit(1)


def _post_json(url: str, payload: dict[str, object]) -> dict[str, object]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def _decode_jwt_payload(token: str) -> dict[str, object]:
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Expected JWT with three segments.")
    padded = parts[1] + "=" * (-len(parts[1]) % 4)
    return json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))


if __name__ == "__main__":
    main()
