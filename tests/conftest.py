"""The main entry point for pytest fixtures.

This will run before any tests are executed when `import pytest` is called.
"""

import asyncio
import inspect
import logging
import os
import textwrap
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterator

import mongomock
import pytest
from dcs_simulation_engine.dal.mongo import AsyncMongoProvider
from dcs_simulation_engine.dal.mongo.util import (
    ensure_default_indexes,
)
from loguru import logger
from openai import OpenAI
from pymongo.database import Database

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
            logger.opt(depth=6, exception=record.exc_info, colors=False).log(level, record.getMessage())

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


@pytest.fixture(autouse=True)
def _isolate_db_state(monkeypatch: pytest.MonkeyPatch) -> Iterator[Database[Any]]:
    """Automatically isolate DB state for each test.

    - Creates a unique in-memory mongomock database per test.
    - Exposes a matching MONGO_URI value for any code paths that still read it.

    Args:
        monkeypatch: Pytest monkeypatch fixture for environment and attribute overrides.

    Yields:
        Database handle for the isolated test DB.
    """
    dbname = f"testdb_{uuid.uuid4().hex}"

    monkeypatch.setenv("MONGO_URI", f"mongodb://localhost:27017/{dbname}")
    monkeypatch.setenv("ACCESS_KEY_PEPPER", "")

    client = mongomock.MongoClient(tz_aware=True)
    db = client[dbname]
    ensure_default_indexes(db)

    try:
        yield db
    finally:
        client.close()


def _collection_name_from_stem(stem: str) -> str:
    """Map a file stem to a collection name."""
    return stem


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
        logger.debug(f"Seeding {len(docs)} docs into collection '{colname}' from {file.name} to run tests.")
        db[colname].insert_many(docs)


@pytest.fixture(autouse=True)
def _seed_db_from_json(_isolate_db_state: Database[Any]) -> None:
    """Auto-seed the mocked DB from JSON files after isolation.

    Looks for JSON files in:
      1) TEST_SEED_DIR env var, if set
      2) <repo_root>/tests/seeds/   (default)
    """
    db = _isolate_db_state
    default_dir = Path(__file__).resolve().parent.parent / "database_seeds" / "dev"
    seed_dir = Path(os.getenv("TEST_SEED_DIR", default_dir))
    _seed_from_dir(db, seed_dir)


class SyncAsyncProviderAdapter:
    """Sync adapter around AsyncMongoProvider for sync-style tests."""

    def __init__(self, provider: AsyncMongoProvider) -> None:
        """Store the wrapped async provider."""
        self._provider = provider

    def get_db(self) -> Database[Any]:
        """Return underlying DB handle."""
        return self._provider.get_db()

    def __getattr__(self, name: str) -> Any:
        """Run awaitable provider methods to completion for sync tests."""
        attr = getattr(self._provider, name)
        if not callable(attr):
            return attr

        def _wrapped(*args: Any, **kwargs: Any) -> Any:
            result = attr(*args, **kwargs)
            if inspect.isawaitable(result):
                try:
                    asyncio.get_running_loop()
                except RuntimeError:
                    return asyncio.run(result)
                return result
            return result

        return _wrapped


# ============================================================================
# DAL Provider Fixture
# ============================================================================


@pytest.fixture
def async_mongo_provider(_isolate_db_state: Database[Any]) -> AsyncMongoProvider:
    """Return AsyncMongoProvider wired to the isolated mongomock database."""
    return AsyncMongoProvider(db=_isolate_db_state)


@pytest.fixture
def sync_mongo_provider(async_mongo_provider: AsyncMongoProvider) -> SyncAsyncProviderAdapter:
    """Return sync adapter over AsyncMongoProvider for explicitly sync-only tests."""
    return SyncAsyncProviderAdapter(async_mongo_provider)


# ============================================================================
# Mock LLM Fixtures for E2E Testing
# ============================================================================

_MOCK_AI_RESPONSE = '{"type": "ai", "content": "The flatworm moves slowly across the surface."}'
_MOCK_VALIDATOR_RESPONSE = '{"type": "info", "content": "Action accepted."}'


@pytest.fixture
def patch_llm_client(monkeypatch):
    """Patch ai_client._call_openrouter with a deterministic mock.

    Returns a JSON string matching the updater prompt's expected format.
    The validator also returns a valid acceptance response.
    Scorer returns a fixed tier/score result.
    """
    import dcs_simulation_engine.games.ai_client as ai_client

    async def mock_call_openrouter(messages, model):
        # Scorer sends a single user message with the scoring prompt
        if len(messages) == 1 and messages[0].get("role") == "user":
            return '{"tier": 2, "score": 65, "reasoning": "Partial match."}'
        # Validator sends only a system message (no conversation history)
        if len(messages) == 1 and messages[0].get("role") == "system":
            return _MOCK_VALIDATOR_RESPONSE
        # AtomicValidator: system + user, system prompt contains JSON format instruction
        if (
            len(messages) == 2
            and messages[0].get("role") == "system"
            and messages[1].get("role") == "user"
            and '"pass":' in messages[0].get("content", "")
        ):
            return '{"pass": true}'
        
        # Updater sends system + conversation history (2+ messages)
        return _MOCK_AI_RESPONSE


    monkeypatch.setattr(ai_client, "_call_openrouter", mock_call_openrouter)
    yield
