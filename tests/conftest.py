"""The main entry point for pytest fixtures.

This will run before any tests are executed when `import pytest` is called.
"""

from __future__ import annotations

import logging
import os
import textwrap
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterator
from unittest.mock import MagicMock

import mongomock
import pytest
from loguru import logger
from openai import OpenAI
from pymongo.database import Database

import dcs_simulation_engine.helpers.database_helpers as dbh

LOG_FORMAT = "{time:YYYY-MM-DD HH:mm:ss} | {level:^7} | {file.name}:{line} | {message}"

# TODO: clean up this file (AND ALL TESTS)


def _setup_logging() -> None:
    """Add a file sink to the default pytest console logging."""
    # logs/pytest_YYYYMMDD.log
    logs_dir = Path(__file__).resolve().parent.parent / "logs"
    logs_dir.mkdir(exist_ok=True)
    logfile = logs_dir / f"pytest_{datetime.now():%Y%m%d}.log"

    # Add file sink to existing pytest console handler
    logger.add(
        logfile,
        level="DEBUG",
        format=LOG_FORMAT,
        rotation="00:00",
        retention="7 days",
        compression="zip",
    )

    # Intercept stdlib logging so everything funnels through Loguru
    class InterceptHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            try:
                level = logger.level(record.levelname).name
            except ValueError:
                level = logging.getLevelName(record.levelno)
            logger.opt(depth=6, exception=record.exc_info, colors=False).log(
                level, record.getMessage()
            )

    # Force stdlib logging to go through our intercept handler
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)



def pytest_configure(config: pytest.Config) -> None:
    """Pytest configuration hook to add a file sink to default pytest logging."""

    # Ensure import-time logging is set up
    _setup_logging()

    # Ensure imports that call get_db() during collection don't fail
    os.environ.setdefault("MONGO_URI", "mongodb://localhost:27017/testdb_placeholder")


def _write_yaml(path: Path, body: str) -> None:
    path.write_text(textwrap.dedent(body).strip() + "\n", encoding="utf-8")


@pytest.fixture
def write_yaml(tmp_path: Path) -> Callable[[str, str], Path]:
    """Create a YAML file inside tmp_path and gives you a path to it.

    Returns:
      a function you can call with (filename, body)
    """

    def _write(filename: str, body: str) -> Path:
        file_path = tmp_path / filename
        _write_yaml(file_path, body)
        return file_path

    return _write


@pytest.fixture(scope="module")
def client() -> OpenAI:
    """Returns an OpenAI client plus actor/evaluator model IDs from env vars."""
    api_key = os.getenv("OPENROUTER_API_KEY")
    base_url = os.getenv("OPENROUTER_BASE_URL")

    missing = []
    if not api_key:
        missing.append("OPENROUTER_API_KEY")
    if not base_url:
        missing.append("OPENROUTER_BASE_URL")

    if missing:
        pytest.fail(f"Missing required environment variables: {', '.join(missing)}")

    client = OpenAI(api_key=api_key, base_url=base_url)
    return client


@pytest.fixture(scope="module")
def mock_client() -> MagicMock:
    """Mocked OpenAI client for testing without real API calls."""
    mock = MagicMock()

    # Example: mock a completion endpoint call
    mock.chat.completions.create.return_value = {
        "choices": [{"message": {"type": "assistant", "content": "Mocked response"}}]
    }

    return mock


@pytest.fixture(autouse=True)
def _isolate_db_state(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Automatically isolate DB state for each test.

    - Forces the helpers module to use `mongomock.MongoClient` instead of a real MongoDB.
    - Creates a unique database name per test by setting MONGODB_URI.
    - Clears the helpers' module-level singletons before and after each test.

    Args:
        monkeypatch: Pytest monkeypatch fixture for environment and attribute overrides.

    Yields:
        None. The fixture simply prepares and cleans up per-test DB state.
    """
    dbname = f"testdb_{uuid.uuid4().hex}"

    # Route helpers to a throwaway DB for this test
    monkeypatch.setenv("MONGO_URI", f"mongodb://localhost:27017/{dbname}")
    # Optional: set pepper if you want to test HMAC mode
    monkeypatch.setenv("ACCESS_KEY_PEPPER", "")

    # Make the helpers use mongomock instead of the real PyMongo client
    monkeypatch.setattr(dbh, "MongoClient", mongomock.MongoClient, raising=True)

    # Reset cached singletons
    dbh._client = None
    dbh._db = None

    try:
        yield
    finally:
        # Ensure isolation on teardown as well
        dbh._client = None
        dbh._db = None


def _collection_name_from_stem(stem: str) -> str:
    """Map a file stem.

    Eg. 'runs' to a collection name.
    If dbh exposes a constant like RUNS_COL, prefer that.
    """
    const = f"{stem.upper()}_COL"
    return getattr(dbh, const, stem)


def _load_json_file(path: Path) -> list[dict]:
    """Load JSON or NDJSON into a list of dicts."""
    import json

    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []

    # Try standard JSON first
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return [data]
        if isinstance(data, list):
            # filter only dict-like items
            return [d for d in data if isinstance(d, dict)]
    except json.JSONDecodeError:
        # Fallback: NDJSON (one JSON object per line)
        objs: list[dict] = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if isinstance(obj, dict):
                objs.append(obj)
        return objs

    return []


def _seed_from_dir(db: Database[Any], seed_dir: Path) -> None:
    """Insert documents from all JSON files in seed_dir."""
    if not seed_dir.exists():
        logger.warning(f"Seed directory not found: {seed_dir}")
        return

    # Deterministic order
    files = sorted([p for p in seed_dir.glob("*.json") if p.is_file()])
    for file in files:
        docs = _load_json_file(file)
        if not docs:
            logger.debug(f"No documents found in {file.name}; skipping.")
            continue

        colname = _collection_name_from_stem(file.stem)
        logger.debug(
            f"Seeding {len(docs)} docs into collection '{colname}' from {file.name} to run tests."
        )
        db[colname].insert_many(docs)


@pytest.fixture(autouse=True)
def _seed_db_from_json(_isolate_db_state: None) -> None:
    """Auto-seed the mocked DB from JSON files after isolation.

    Looks for JSON files in:
      1) TEST_SEED_DIR env var, if set
      2) <repo_root>/tests/seeds/   (default)
    """
    db = dbh.get_db()
    default_dir = Path(__file__).resolve().parent.parent / "database_seeds" / "dev"
    seed_dir = Path(os.getenv("TEST_SEED_DIR", default_dir))
    _seed_from_dir(db, seed_dir)


@pytest.fixture
def seed_runs_from_json() -> Callable[[str], None]:
    """Seeds the mocked runs collection with data from a JSON file."""
    db = dbh.get_db()

    def _load(path: str) -> None:
        docs = _load_json_file(Path(path))
        if not docs:
            return
        colname = getattr(dbh, "RUNS_COL", "runs")
        db[colname].insert_many(docs)

    return _load


# ============================================================================
# Mock LLM Fixtures for E2E Testing
# ============================================================================


@pytest.fixture
def mock_llm_client():
    """Mock LLM client with default responses.

    Returns a MockChatModel that replaces ChatOpenRouter calls with
    deterministic responses. Useful for testing without real API calls.
    """
    from tests.mocks.mock_llm import MockChatModel

    return MockChatModel()



@pytest.fixture
def patch_llm_client(mock_llm_client, monkeypatch):
    """Patch ChatOpenRouter to use mock client.

    This fixture automatically replaces all ChatOpenRouter instances with
    the mock client, allowing E2E tests to run without real LLM API calls.

    Note: We patch where ChatOpenRouter is imported/used, not where it's defined.
    """

    # Patch the ChatOpenRouter class to return our mock
    def mock_chat_open_router(*args, **kwargs):
        return mock_llm_client

    # Patch where ChatOpenRouter is imported (used), not where it's defined
    monkeypatch.setattr(
        "dcs_simulation_engine.core.run_manager.ChatOpenRouter", mock_chat_open_router
    )
    monkeypatch.setattr(
        "dcs_simulation_engine.core.simulation_graph.subgraph.ChatOpenRouter", mock_chat_open_router
    )
    yield mock_llm_client
