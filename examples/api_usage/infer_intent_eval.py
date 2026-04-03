#!/usr/bin/env python3
"""Manual smoke script for Infer Intent evaluation through the HTTP API."""

import argparse
import json
from typing import Any, Iterable
from urllib.parse import urlparse

from dcs_simulation_engine.api.client import APIClient
from dcs_simulation_engine.api.models import (
    CreateGameRequest,
    ServerMode,
    WSEventFrame,
)
from websockets.sync.client import connect


def _print_events(events: Iterable[WSEventFrame]) -> None:
    for event in events:
        print(f"   [{event.event_type}] {event.content}")


def _choose_hid(options, preferred_hid: str) -> str:
    for option in options:
        if option.hid == preferred_hid:
            return option.hid
    if not options:
        raise RuntimeError("No valid character choices were returned by setup.")
    return options[0].hid


def _api_key_for_mode(server_mode: ServerMode, api_key: str | None) -> str | None:
    """Require an API key only when the server is running in standard mode."""
    if server_mode == "free_play":
        return None
    if api_key:
        return api_key
    raise RuntimeError("--api-key is required when the server is running in standard mode.")


def _ws_url(base_url: str, session_id: str) -> str:
    parsed = urlparse(base_url)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    return f"{scheme}://{parsed.netloc}/api/play/game/{session_id}/ws"


def _recv_frame(ws: Any) -> dict[str, Any]:
    raw = ws.recv()
    if not isinstance(raw, str):
        raise RuntimeError("Expected text websocket frame")
    frame = json.loads(raw)
    if not isinstance(frame, dict):
        raise RuntimeError("Expected JSON object websocket frame")
    if frame.get("type") == "error":
        raise RuntimeError(str(frame.get("detail") or frame.get("message") or "Unknown websocket error"))
    return frame


def _recv_until_turn_end(ws: Any) -> tuple[list[WSEventFrame], dict[str, Any]]:
    events: list[WSEventFrame] = []
    while True:
        frame = _recv_frame(ws)
        frame_type = frame.get("type")
        if frame_type == "event":
            events.append(WSEventFrame.model_validate(frame))
            continue
        if frame_type in {"turn_end", "closed"}:
            return events, frame
        raise RuntimeError(f"Unexpected websocket frame: {frame}")


def _send_advance(ws: Any, text: str) -> tuple[list[WSEventFrame], dict[str, Any]]:
    ws.send(json.dumps({"type": "advance", "text": text}))
    return _recv_until_turn_end(ws)


def main() -> None:
    """Play Infer Intent, then request the cached evaluation twice when supported."""
    parser = argparse.ArgumentParser(description="Run Infer Intent and request the post-game evaluation.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="FastAPI base URL")
    parser.add_argument(
        "--api-key",
        default=None,
        help="Player API key for standard-mode servers. Omit this in free-play mode.",
    )
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    turns = [
        "I crouch down and look closely at the creature on the ground.",
        "I place a small piece of food near it and step back to watch.",
        "I gently prod the ground beside it with my finger.",
    ]
    guess_text = "The creature is trying to find food while minimizing exposure to danger."
    feedback_text = "No additional feedback."

    with APIClient(url=base_url, timeout=60.0) as api:
        print("1) Fetch server config")
        config = api.server_config()
        api_key = _api_key_for_mode(config.mode, args.api_key)
        print(f"   mode={config.mode}")
        print(f"   authentication_required={config.authentication_required}")

        if api_key is not None:
            print("2) Authenticate")
            auth = api.auth(api_key=api_key)
            print(f"   authenticated={auth.authenticated} player_id={auth.player_id}")
        else:
            print("2) Authenticate")
            print("   skipped (free play mode)")

        print("3) Fetch setup options")
        setup = api.setup_options(game_name="Infer Intent", api_key=api_key)
        if not setup.can_start:
            raise RuntimeError(f"Infer Intent cannot be started: {setup.message or setup.denial_reason}")
        pc_choice = _choose_hid(setup.pcs, "human-normative")
        npc_choice = _choose_hid(setup.npcs, "flatworm")
        print(f"   pc_choice={pc_choice}")
        print(f"   npc_choice={npc_choice}")

        print("4) Start session")
        run = api.start_game(
            CreateGameRequest(
                api_key=api_key,
                game="Infer Intent",
                pc_choice=pc_choice,
                npc_choice=npc_choice,
                source="api-manual-infer-intent-eval",
            )
        )
        print(f"   session_id={run.session_id}")

        print("5) Play through completion")
        ws_url = _ws_url(base_url, run.session_id)
        connect_kwargs: dict[str, Any] = {}
        if api_key:
            connect_kwargs["additional_headers"] = {"Authorization": f"Bearer {api_key}"}

        with connect(ws_url, **connect_kwargs) as ws:
            opening_events, opening_frame = _recv_until_turn_end(ws)
            _print_events(opening_events)
            print(f"   opening: turns={opening_frame.get('turns')} exited={opening_frame.get('exited', False)}")

            for idx, turn in enumerate(turns, start=1):
                print(f"   turn {idx}: {turn}")
                step_events, step_frame = _send_advance(ws, turn)
                _print_events(step_events)
                print(f"   turn_end: turns={step_frame.get('turns')} exited={step_frame.get('exited', False)}")

            print("   command: /predict-intent")
            guess_events, guess_frame = _send_advance(ws, "/predict-intent")
            _print_events(guess_events)
            print(f"   turn_end: turns={guess_frame.get('turns')} exited={guess_frame.get('exited', False)}")

            print(f"   guess: {guess_text}")
            answer_events, answer_frame = _send_advance(ws, guess_text)
            _print_events(answer_events)
            print(f"   turn_end: turns={answer_frame.get('turns')} exited={answer_frame.get('exited', False)}")

            print(f"   feedback: {feedback_text}")
            feedback_events, feedback_frame = _send_advance(ws, feedback_text)
            _print_events(feedback_events)
            completed = bool(feedback_frame.get("exited", False))
            turns_completed = int(feedback_frame.get("turns", 0))
            print(f"   completed={completed} turns={turns_completed}")

            if feedback_frame.get("type") != "closed":
                ws.send(json.dumps({"type": "close"}))
                closed_frame = _recv_frame(ws)
                if closed_frame.get("type") != "closed":
                    raise RuntimeError(f"Expected closed frame, got: {closed_frame}")

        print("6) Request evaluation (first call)")
        first = api.request_infer_intent_evaluation(run.session_id, api_key=api_key)
        print(json.dumps(first.model_dump(mode="json"), indent=2))

        print("7) Request evaluation again (cached)")
        second = api.request_infer_intent_evaluation(run.session_id, api_key=api_key)
        print(json.dumps(second.model_dump(mode="json"), indent=2))


if __name__ == "__main__":
    main()
