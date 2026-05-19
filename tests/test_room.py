import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen

from devdefender_lab.config import Settings
from devdefender_lab.room import Phase1Room, RoomHandler


def test_room_http_api_submits_feedback(tmp_path: Path) -> None:
    room = Phase1Room(Settings(llm_mode="mock", artifact_dir=tmp_path), Path("sample_repo"))
    handler = type("TestRoomHandler", (RoomHandler,), {"room": room})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"

    try:
        with urlopen(f"{base_url}/api/session", timeout=5) as response:
            session = json.loads(response.read().decode("utf-8"))

        payload = json.dumps({"feedback": "Can invalid payment amounts be captured?"}).encode("utf-8")
        request = Request(
            f"{base_url}/api/feedback",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=5) as response:
            result = json.loads(response.read().decode("utf-8"))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert session["status"] == "waiting_for_feedback"
    assert result["ok"] is True
    assert result["state"]["status"] == "complete"
    assert "validate_payment" in result["state"]["defense"]
    assert result["state"]["refinement"]["status"] == "verified"
