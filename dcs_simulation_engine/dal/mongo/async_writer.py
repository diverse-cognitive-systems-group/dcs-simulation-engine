"""Generic async buffered writer for Mongo collections."""
# ruff: noqa: D105,D107

import asyncio
from typing import Any, Generic, TypeVar

from dcs_simulation_engine.utils.time import utc_now
from loguru import logger
from pymongo.errors import BulkWriteError

# TDoc represents a dictionary type. We use this TypeVar so the IDE knows
# that whatever dictionary type goes in, comes out. Mongo documents are dicts.
TDoc = TypeVar("TDoc", bound=dict)


class AsyncMongoWriter(Generic[TDoc]):
    """Buffer writes and periodically flush batched inserts to Mongo."""

    def __init__(
        self,
        *,
        collection: Any,
        batch_size: int = 20,
        flush_interval_ms: int = 200,
        max_queue_size: int = 1000,
        persisted_at_field: str | None = "persisted_at",
        ignore_duplicate_key_errors: bool = True,
    ) -> None:
        # Fail early if configured incorrectly. This prevents silent bugs later.
        if batch_size <= 0:
            raise ValueError("batch_size must be > 0")
        if flush_interval_ms <= 0:
            raise ValueError("flush_interval_ms must be > 0")
        if max_queue_size <= 0:
            raise ValueError("max_queue_size must be > 0")

        self._collection = collection
        self._batch_size = batch_size
        self._flush_interval_s = flush_interval_ms / 1000.0
        self._persisted_at_field = persisted_at_field
        self._ignore_duplicate_key_errors = ignore_duplicate_key_errors

        # The actual in-memory list where we store documents before writing them.
        self._buffer: list[TDoc] = []

        # A Lock ensures only one async task can modify `self._buffer` at a time.
        # This prevents race conditions (e.g., two tasks appending exactly at the same time).
        self._buffer_lock = asyncio.Lock()

        # A Lock to ensure we don't have multiple network calls writing to Mongo simultaneously.
        self._flush_lock = asyncio.Lock()

        # A Semaphore is like a bouncer at a club with a strict capacity limit.
        # It creates "backpressure". If we have 1000 items in the queue, `enqueue`
        # will pause (await) until some items are saved to the DB and slots open up.
        self._slots = asyncio.Semaphore(max_queue_size)

        # This holds the background task that continuously checks if we need to flush.
        self._ticker_task: asyncio.Task[None] | None = None

        # State flags so we know if the writer is currently active or shut down.
        self._closed = False
        self._started = False

        # Events act like traffic lights for async tasks.
        # _stop_event tells the background loop "time to shut down".
        self._stop_event = asyncio.Event()

        # _flush_requested is a signal that says "Hey, the buffer reached batch_size, flush now!"
        self._flush_requested = asyncio.Event()

    # __aenter__ and __aexit__ allow this class to be used as an "async context manager".
    # e.g., `async with AsyncMongoWriter(...) as writer:`
    async def __aenter__(self) -> "AsyncMongoWriter[TDoc]":
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        # Automatically clean up and flush remaining items when exiting the `async with` block.
        await self.close()

    async def start(self) -> None:
        """Start periodic background flushing."""
        if self._started:
            return  # Prevent starting multiple background tasks if called twice

        self._started = True
        self._stop_event.clear()

        # Kick off the infinite background loop without pausing the current code execution.
        self._ticker_task = asyncio.create_task(self._ticker_loop())

    async def enqueue(self, doc: TDoc) -> None:
        """Queue one document. Backpressure applies when queue is full.

        This method never performs inline DB writes.
        """
        if self._closed:
            raise RuntimeError("writer is closed")
        if not self._started:
            raise RuntimeError("writer not started")

        # Claim 1 spot in the queue. If the queue is at max_queue_size,
        # this line will yield control back to the event loop until a spot frees up.
        await self._slots.acquire()

        should_request_flush = False

        # We use the buffer lock because we are modifying the shared `self._buffer` list.
        async with self._buffer_lock:
            self._buffer.append(doc)
            # If our buffer has reached the target batch size, flag that we need to flush.
            if len(self._buffer) >= self._batch_size:
                should_request_flush = True

        # If we hit the limit, flip the event "traffic light" to green.
        # The background _ticker_loop will see this and immediately trigger a flush.
        if should_request_flush:
            self._flush_requested.set()

    async def flush(self) -> None:
        """Flush all currently buffered writes."""
        batch: list[TDoc]

        # Safely grab all the items currently in the buffer and empty the buffer.
        async with self._buffer_lock:
            batch = self._drain_locked()

        # If there's actually anything to write, send it to Mongo.
        if batch:
            await self._flush_batch(batch)

    async def close(self) -> None:
        """Flush pending docs and stop background flushing."""
        if self._closed:
            return

        self._closed = True
        # Tell the background loop to stop running.
        self._stop_event.set()
        # Wake up the background loop in case it's currently sleeping.
        self._flush_requested.set()

        # Wait gracefully for the background task to finish its current loop.
        if self._ticker_task is not None:
            await self._ticker_task
            self._ticker_task = None

        # One final flush to make sure any stragglers in the buffer are written to the DB.
        await self.flush()

    def _drain_locked(self) -> list[TDoc]:
        """Helper to empty the buffer. MUST be called with _buffer_lock acquired."""
        batch = self._buffer
        self._buffer = []  # Reset the buffer to a fresh empty list
        return batch

    async def _ticker_loop(self) -> None:
        """The background worker that sleeps and wakes up to flush data."""
        # Keep running until someone calls close() and sets the stop event.
        while not self._stop_event.is_set():
            try:
                # Wait for EITHER the event to be set (buffer got full)
                # OR for the timeout to pass (flush interval time elapsed).
                await asyncio.wait_for(self._flush_requested.wait(), timeout=self._flush_interval_s)
            except asyncio.TimeoutError:
                # The timeout passed before the buffer filled up. That's fine!
                # We catch the error and move on to flush whatever is in there anyway.
                pass

            # Reset the flush event light back to "red" for the next cycle.
            self._flush_requested.clear()

            # Execute the database write.
            await self.flush()

    async def _flush_batch(self, batch: list[TDoc]) -> None:
        """The actual logic to interact with the database."""
        # Ensure we only have one active database write going on from this writer.
        async with self._flush_lock:
            # Inject a timestamp into every document right before saving it.
            if self._persisted_at_field:
                ts = utc_now()
                for doc in batch:
                    # setdefault ensures we don't overwrite if the doc already has this field
                    doc.setdefault(self._persisted_at_field, ts)

            try:
                # Attempt to write the whole chunk to MongoDB efficiently in one network roundtrip.
                await self._collection.insert_many(batch, ordered=True)
            except BulkWriteError as exc:
                # If a Mongo error happens, check if it's just a duplicate key error (which we might want to ignore).
                if not self._ignore_duplicate_key_errors or not _all_duplicate_key_errors(exc):
                    raise  # It's a real error, crash loudly!
                logger.debug("Ignored duplicate key write errors while flushing {} docs", len(batch))
            finally:
                # REGARDLESS of success or failure, we MUST release the semaphore slots.
                # If we don't, the queue will permanently shrink and eventually freeze the app.
                for _ in batch:
                    self._slots.release()


def _all_duplicate_key_errors(exc: BulkWriteError) -> bool:
    """Check if all errors in a BulkWriteError are duplicate key collisions (Mongo code 11000)."""
    # Safely extract the list of individual errors from the BulkWriteError object.
    errors = exc.details.get("writeErrors", []) if isinstance(exc.details, dict) else []

    # Return True if we have at least one error, AND every single error is code 11000.
    return bool(errors) and all(err.get("code") == 11000 for err in errors)
