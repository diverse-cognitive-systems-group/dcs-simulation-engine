import pytest
from loguru import logger

from dcs_simulation_engine.dal.mongo.const import MongoColumns
from dcs_simulation_engine.observability import PersistentLogCapture

pytestmark = pytest.mark.anyio


async def test_persistent_log_capture_writes_bound_warning(async_mongo_provider) -> None:
    db = async_mongo_provider.get_db()
    capture = PersistentLogCapture(db=db, source="test-suite", throttle_seconds=60)
    await capture.start()
    capture.install()

    logger.bind(
        session_id="session-1",
        player_id="player-1",
        game_name="Explore",
        detail={"safe": "value", "api_key": "secret"},
    ).warning("Captured warning for persistence")

    await capture.close()

    docs = list(db[MongoColumns.LOGS].find({"message": "Captured warning for persistence"}))
    assert len(docs) == 1
    doc = docs[0]
    assert doc["source"] == "test-suite"
    assert doc["level"] == "WARNING"
    assert doc["session_id"] == "session-1"
    assert doc["player_id"] == "player-1"
    assert doc["game_name"] == "Explore"
    assert doc["detail"]["safe"] == "value"
    assert doc["detail"]["api_key"] == "[redacted]"


async def test_persistent_log_capture_throttles_repeated_messages(async_mongo_provider) -> None:
    db = async_mongo_provider.get_db()
    capture = PersistentLogCapture(db=db, source="test-suite", throttle_seconds=60)
    await capture.start()
    capture.install()

    for _ in range(3):
        logger.warning("Repeated warning for throttling")

    await capture.close()

    docs = list(db[MongoColumns.LOGS].find({"message": "Repeated warning for throttling"}).sort("event_ts", 1))
    assert len(docs) == 2
    assert docs[0]["throttled"] is False
    assert docs[0]["suppressed_count"] == 0
    assert docs[1]["throttled"] is True
    assert docs[1]["suppressed_count"] == 2


async def test_persistent_log_capture_can_persist_info_when_requested(async_mongo_provider) -> None:
    db = async_mongo_provider.get_db()
    capture = PersistentLogCapture(db=db, source="test-suite", throttle_seconds=60)
    await capture.start()
    capture.install()

    logger.bind(persist_log=True).info("Important info below warning")

    await capture.close()

    docs = list(db[MongoColumns.LOGS].find({"message": "Important info below warning"}))
    assert len(docs) == 1
    assert docs[0]["level"] == "INFO"
