#!/usr/bin/env python3
"""Manual smoke script for FastAPI DCS server.

Flow:
1. Register user
2. Authenticate with API key
3. Start a game session
4. Run 3 advance steps over websocket
5. Close the session
"""

import argparse
import json
from typing import Any
from urllib.parse import quote, urlparse

import httpx
from websockets.sync.client import connect


def _ws_url(base_url: str, session_id: str, api_key: str) -> str:
    parsed = urlparse(base_url)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    return f"{scheme}://{parsed.netloc}/api/play/game/{session_id}/ws?api_key={quote(api_key, safe='')}"


def _recv_json(ws: Any) -> dict[str, Any]:
    raw = ws.recv()
    if not isinstance(raw, str):
        raise RuntimeError("Expected text websocket frame")
    frame = json.loads(raw)
    if not isinstance(frame, dict):
        raise RuntimeError("Expected JSON object frame")
    return frame


def _recv_until_turn_end(ws: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    events: list[dict[str, Any]] = []
    while True:
        frame = _recv_json(ws)
        frame_type = frame.get("type")
        if frame_type == "error":
            raise RuntimeError(f"Server error: {frame.get('detail') or frame}")
        if frame_type == "event":
            events.append(frame)
            continue
        if frame_type == "turn_end":
            return events, frame
        if frame_type == "closed":
            return events, frame


def main() -> None:
    """Register a new player, authenticate, play three steps, then close the session."""
    parser = argparse.ArgumentParser(description="Register, auth, play 3 steps, close.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="FastAPI base URL")
    parser.add_argument("--game", default="explore", help="Game name")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")

    reg_payload = {
        "full_name": "API Smoke Tester",
        "email": "api-smoke@example.com",
        "phone_number": "+1 555 010 9999",
        "prior_experience": "none",
        "additional_comments": "automated smoke flow",
        "consent_to_followup": True,
        "consent_signature": "API Smoke Tester",
    }

    with httpx.Client(base_url=base_url, timeout=30.0) as client:
        print("1) Register user")
        reg = client.post("/api/user/registration", json=reg_payload)
        reg.raise_for_status()
        reg_json = reg.json()
        player_id = reg_json["player_id"]
        api_key = reg_json["api_key"]
        print(f"   player_id={player_id}")

        print("2) Authenticate")
        auth = client.post("/api/user/auth", json={"api_key": api_key})
        auth.raise_for_status()
        auth_json = auth.json()
        print(f"   authenticated={auth_json.get('authenticated')} player_id={auth_json.get('player_id')}")

        print("3) Start game")
        create_payload = {
            "api_key": api_key,
            "game": args.game,
            "pc_choice": None,
            "npc_choice": None,
            "source": "api-smoke-script",
        }
        created = client.post("/api/play/game", json=create_payload)
        created.raise_for_status()
        created_json = created.json()
        session_id = created_json["session_id"]
        print(f"   session_id={session_id}")

    print("4) Run 3 steps over WS")
    ws_url = _ws_url(base_url, session_id, api_key)
    with connect(ws_url) as ws:
        opening_events, opening_turn_end = _recv_until_turn_end(ws)
        if opening_events:
            print(f"   opening: {opening_events[-1].get('content')}")
        print(f"   opening_turn_end: turns={opening_turn_end.get('turns')} exited={opening_turn_end.get('exited')}")

        prompts = [
            "I look around.",
            "I take one careful step forward.",
            "I describe what I think is happening.",
        ]
        for idx, text in enumerate(prompts, start=1):
            ws.send(json.dumps({"type": "advance", "text": text}))
            events, turn_end = _recv_until_turn_end(ws)
            last_content = events[-1].get("content") if events else "<no event content>"
            print(f"   step {idx}: {last_content}")
            print(f"   turn_end: turns={turn_end.get('turns')} exited={turn_end.get('exited')}")

        print("5) Close session")
        ws.send(json.dumps({"type": "close"}))
        closed = _recv_json(ws)
        if closed.get("type") != "closed":
            raise RuntimeError(f"Expected closed frame, got: {closed}")
        print(f"   closed session_id={closed.get('session_id')}")


if __name__ == "__main__":
    main()
