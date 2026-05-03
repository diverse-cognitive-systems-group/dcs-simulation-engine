"""Run-specific provider tests."""

import pytest
from dcs_simulation_engine.dal.base import (
    AssignmentRecord,
    RunRecord,
)
from dcs_simulation_engine.dal.mongo.const import MongoColumns

pytestmark = [pytest.mark.unit, pytest.mark.anyio]


async def test_upsert_run_persists_snapshot(async_mongo_provider) -> None:
    """Run metadata and config snapshots should persist in the runs collection."""
    record = await async_mongo_provider.upsert_run(
        name="usability-ca",
        description="Usability study",
        config_snapshot={"name": "usability-ca", "games": ["Explore"]},
        progress={"total": 5, "completed": 0, "is_complete": False},
    )

    assert isinstance(record, RunRecord)
    assert record.name == "usability-ca"

    stored = await async_mongo_provider.get_run()
    assert stored is not None
    assert stored.data[MongoColumns.CONFIG_SNAPSHOT]["games"] == ["Explore"]


async def test_create_assignment_and_store_form_responses(async_mongo_provider) -> None:
    """Assignments should persist with lifecycle metadata and nested form responses."""
    assignment = await async_mongo_provider.create_assignment(
        assignment_doc={
            MongoColumns.PLAYER_ID: "player-1",
            MongoColumns.GAME_NAME: "Explore",
            MongoColumns.PC_HID: "test-pc",
            MongoColumns.NPC_HID: "test-npc",
            MongoColumns.FORM_RESPONSES: {},
        }
    )

    assert isinstance(assignment, AssignmentRecord)
    assert assignment.status == "assigned"

    updated = await async_mongo_provider.set_assignment_form_response(
        assignment_id=assignment.assignment_id,
        form_key="enter",
        response={"submitted_at": "2026-01-01T00:00:00Z", "answers": {"full_name": {"answer": "Ada"}}},
    )
    assert updated is not None
    assert updated.data[MongoColumns.FORM_RESPONSES]["enter"]["answers"]["full_name"]["answer"] == "Ada"


async def test_active_assignment_reuses_interrupted_and_clears_on_completion(async_mongo_provider) -> None:
    """Interrupted assignments remain active; completed ones do not."""
    assignment = await async_mongo_provider.create_assignment(
        assignment_doc={
            MongoColumns.PLAYER_ID: "player-2",
            MongoColumns.GAME_NAME: "Foresight",
            MongoColumns.PC_HID: "test-pc",
            MongoColumns.NPC_HID: "test-npc",
            MongoColumns.FORM_RESPONSES: {},
        }
    )

    in_progress = await async_mongo_provider.update_assignment_status(
        assignment_id=assignment.assignment_id,
        status="in_progress",
        active_session_id="session-1",
    )
    assert in_progress is not None
    assert in_progress.status == "in_progress"

    interrupted = await async_mongo_provider.update_assignment_status(
        assignment_id=assignment.assignment_id,
        status="interrupted",
    )
    assert interrupted is not None
    assert interrupted.status == "interrupted"

    active = await async_mongo_provider.get_active_assignment(
        player_id="player-2",
    )
    assert active is not None
    assert active.assignment_id == assignment.assignment_id

    completed = await async_mongo_provider.update_assignment_status(
        assignment_id=assignment.assignment_id,
        status="completed",
    )
    assert completed is not None
    assert completed.status == "completed"

    assert (
        await async_mongo_provider.get_active_assignment(
            player_id="player-2",
        )
        is None
    )
