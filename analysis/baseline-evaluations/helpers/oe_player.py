"""OpenEvolve run helper for executing and recording player evolution results."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from openevolve.database import Program


async def run_player_evolution(
    *,
    evolve: Any,
    logger: Any,
    get_openrouter_balance: Callable[[], Any],
    save_run_metadata: Callable[..., None],
    target_example: str,
    output_dir: str,
    or_balance_initial: float,
) -> Program | None:
    """Run evolution once and persist runtime/cost/metrics metadata.

    Args:
        evolve: Evolution engine with an async ``run()`` method.
        logger: Logger supporting ``info`` and ``warning`` methods.
        get_openrouter_balance: Callable returning a balance object with ``total_usage``.
        save_run_metadata: Callable used to persist experiment metadata.
        target_example: Experiment identifier.
        output_dir: Output directory for metadata artifacts.
        or_balance_initial: OpenRouter usage snapshot taken before evolution.
    """
    start_time = time.time_ns() // 1_000_000
    best_program: Program | None = await evolve.run()
    elapsed_time = (time.time_ns() // 1_000_000) - start_time
    logger.info(f"{'=' * 20} Finished Evolution {'=' * 20}")

    # Calculate OpenRouter API cost for the evolution run.
    or_balance_end = get_openrouter_balance().total_usage
    run_cost = or_balance_end - or_balance_initial

    # Persist run statistics to a file for later analysis.
    if best_program is not None:
        save_run_metadata(
            experiment=target_example,
            output_dir=output_dir,
            elapsed_time=elapsed_time,
            run_cost=run_cost,
            metrics=best_program.metrics,
        )
        logger.info(f"Best Program Metrics: {best_program.metrics}")
    else:
        logger.warning("No best program found after evolution run.")

    return best_program
