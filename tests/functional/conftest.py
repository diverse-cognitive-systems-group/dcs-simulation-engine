"""Shared fixtures for functional tests."""

import pytest
from dcs_simulation_engine.dal.mongo import MongoProvider
from pymongo.database import Database


@pytest.fixture
def mongo_provider(_isolate_db_state: Database):
    """Return a MongoProvider wired to the mongomock DB for this test."""
    return MongoProvider(db=_isolate_db_state)
