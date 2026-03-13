"""Helpers for working with possibly-awaitable values."""

import inspect
from typing import Any


async def maybe_await(value: Any) -> Any:
    """Await value when awaitable; otherwise return as-is."""
    if inspect.isawaitable(value):
        return await value
    return value
