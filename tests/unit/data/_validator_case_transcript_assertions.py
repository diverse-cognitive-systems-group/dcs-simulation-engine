"""Shared transcript contract assertions for validator case fixtures."""

import re

from dcs_simulation_engine.core.game import Game

OPENING_PREFIX = Game.OPENING_PREFIX
SIMULATOR_PREFIX = Game.SIMULATOR_PREFIX
PLAYER_PREFIX = Game.PLAYER_PREFIX
PLAYER_LINE_RE = re.compile(rf"^{re.escape(PLAYER_PREFIX)} \((?P<pc_hid>[^)]+)\): (?P<content>.*)$")


def _parse_transcript_lines(transcript: str, *, case_id: str, dataset_name: str) -> list[str]:
    """Split a transcript into non-empty newline-delimited lines."""
    assert isinstance(transcript, str), f"{dataset_name} case {case_id} transcript must be a string"
    assert transcript.strip(), f"{dataset_name} case {case_id} transcript must be non-empty"

    lines = transcript.splitlines()
    assert lines, f"{dataset_name} case {case_id} transcript must contain at least one line"
    assert all(line.strip() for line in lines), f"{dataset_name} case {case_id} transcript contains a blank line"
    return lines


def _assert_opening_line(line: str, *, case_id: str, dataset_name: str) -> None:
    assert line.startswith(OPENING_PREFIX), f"{dataset_name} case {case_id} transcript must start with '{OPENING_PREFIX}'"
    assert line[len(OPENING_PREFIX) :].strip(), f"{dataset_name} case {case_id} transcript opening scene must have content"


def _assert_player_line(line: str, *, expected_pc_hid: str, case_id: str, dataset_name: str) -> None:
    match = PLAYER_LINE_RE.match(line)
    assert match is not None, f"{dataset_name} case {case_id} transcript line must match 'Player (<pc_hid>): ...': {line!r}"
    actual_pc_hid = match.group("pc_hid").strip()
    assert actual_pc_hid == expected_pc_hid, (
        f"{dataset_name} case {case_id} transcript player HID {actual_pc_hid!r} does not match case pc_hid {expected_pc_hid!r}"
    )
    assert match.group("content").strip(), f"{dataset_name} case {case_id} transcript player line must have content"


def _assert_simulator_line(line: str, *, case_id: str, dataset_name: str) -> None:
    assert line.startswith(SIMULATOR_PREFIX), (
        f"{dataset_name} case {case_id} transcript simulator line must start with '{SIMULATOR_PREFIX}'"
    )
    assert line[len(SIMULATOR_PREFIX) :].strip(), f"{dataset_name} case {case_id} transcript simulator line must have content"


def assert_player_case_transcript_matches_game_contract(transcript: str, *, pc_hid: str, case_id: str, dataset_name: str) -> None:
    """Assert a player-case transcript ends with the simulator, ready for the next player action."""
    lines = _parse_transcript_lines(transcript, case_id=case_id, dataset_name=dataset_name)
    _assert_opening_line(lines[0], case_id=case_id, dataset_name=dataset_name)

    remaining_lines = lines[1:]
    assert len(remaining_lines) % 2 == 0, (
        f"{dataset_name} case {case_id} transcript must contain complete Player/Simulator pairs after the opening scene"
    )

    for index in range(0, len(remaining_lines), 2):
        _assert_player_line(
            remaining_lines[index],
            expected_pc_hid=pc_hid,
            case_id=case_id,
            dataset_name=dataset_name,
        )
        _assert_simulator_line(
            remaining_lines[index + 1],
            case_id=case_id,
            dataset_name=dataset_name,
        )


def assert_simulator_case_transcript_matches_game_contract(transcript: str, *, pc_hid: str, case_id: str, dataset_name: str) -> None:
    """Assert a simulator-case transcript ends with the player's pending action."""
    lines = _parse_transcript_lines(transcript, case_id=case_id, dataset_name=dataset_name)
    _assert_opening_line(lines[0], case_id=case_id, dataset_name=dataset_name)

    remaining_lines = lines[1:]
    assert remaining_lines, (
        f"{dataset_name} case {case_id} transcript must include newline-delimited turns after the opening scene: "
        "expected 'Opening scene: ...' followed by a newline, then alternating "
        "'Player (<pc_hid>): ...' and 'Simulator: ...' lines, ending with a trailing "
        "'Player (<pc_hid>): ...' line before simulator_response"
    )
    assert len(remaining_lines) % 2 == 1, (
        f"{dataset_name} case {case_id} transcript must use newline-delimited turns after the opening scene and end "
        "with a trailing 'Player (<pc_hid>): ...' line before simulator_response"
    )

    for index in range(0, len(remaining_lines) - 1, 2):
        _assert_player_line(
            remaining_lines[index],
            expected_pc_hid=pc_hid,
            case_id=case_id,
            dataset_name=dataset_name,
        )
        _assert_simulator_line(
            remaining_lines[index + 1],
            case_id=case_id,
            dataset_name=dataset_name,
        )

    _assert_player_line(
        remaining_lines[-1],
        expected_pc_hid=pc_hid,
        case_id=case_id,
        dataset_name=dataset_name,
    )
