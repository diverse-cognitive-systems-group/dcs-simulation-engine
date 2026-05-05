"""Mongo-backed writer for persisted engine log events."""

import asyncio
import sys
from typing import Any

from dcs_simulation_engine.dal.mongo.const import MongoColumns
from dcs_simulation_engine.utils.async_utils import maybe_await
from dcs_simulation_engine.utils.time import utc_now


class MongoLogEventWriter:
    """Buffer persisted log events and write them to Mongo in small batches."""

    def __init__(
        self,
        *,
        db: Any,
        batch_size: int = 20,
        flush_interval_ms: int = 200,
        max_queue_size: int = 1000,
    ) -> None:
        if batch_size <= 0:
            raise ValueError("batch_size must be > 0")
        if flush_interval_ms <= 0:
            raise ValueError("flush_interval_ms must be > 0")
        if max_queue_size <= 0:
            raise ValueError("max_queue_size must be > 0")

        self._collection = db[MongoColumns.LOGS]
        self._batch_size = batch_size
        self._flush_interval_s = flush_interval_ms / 1000.0
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=max_queue_size)
        self._flush_requested = asyncio.Event()
        self._closed = False
        self._started = False
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start the background batch writer."""
        if self._started:
            return
        self._started = True
        self._task = asyncio.create_task(self._worker_loop())

    def enqueue_nowait(self, doc: dict[str, Any]) -> bool:
        """Queue a log event without blocking application logging."""
        if self._closed or not self._started:
            return False
        try:
            self._queue.put_nowait(doc)
        except asyncio.QueueFull:
            return False
        if self._queue.qsize() >= self._batch_size:
            self._flush_requested.set()
        return True

    async def flush(self) -> None:
        """Flush all queued log events."""
        if not self._started:
            return
        self._flush_requested.set()
        await self._queue.join()

    async def close(self) -> None:
        """Flush and stop the background writer."""
        if self._closed:
            return
        self._closed = True
        self._flush_requested.set()
        if self._task is not None:
            await self._task
            self._task = None

    async def _worker_loop(self) -> None:
        while not self._closed or not self._queue.empty():
            try:
                await asyncio.wait_for(self._flush_requested.wait(), timeout=self._flush_interval_s)
            except asyncio.TimeoutError:
                pass
            self._flush_requested.clear()

            batch = self._drain_batch()
            if batch:
                await self._write_batch(batch)

    def _drain_batch(self) -> list[dict[str, Any]]:
        batch: list[dict[str, Any]] = []
        while len(batch) < self._batch_size:
            try:
                batch.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return batch

    async def _write_batch(self, batch: list[dict[str, Any]]) -> None:
        persisted_at = utc_now()
        for doc in batch:
            doc.setdefault(MongoColumns.PERSISTED_AT, persisted_at)

        try:
            await maybe_await(self._collection.insert_many(batch, ordered=False))
        except Exception as exc:
            sys.stderr.write(f"Failed to persist {len(batch)} log event(s): {exc}\n")
        finally:
            for _ in batch:
                self._queue.task_done()
