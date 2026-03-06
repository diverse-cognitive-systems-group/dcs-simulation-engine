from openevolve import OpenEvolve
from openevolve.config import Config
from openevolve.database import Program


    start_time = time.time_ns() // 1_000_000
    best_program: Program | None = (
        await evolve.run()
    )  # Arg `iterations` (int): num of iternations during an evolution
    elapsed_time = (time.time_ns() // 1_000_000) - start_time
    logger.info(f"{'='* 20} Finished Evolution {'='* 20}")

    # Calculate OpenRouter API cost for the evolution run
    or_balance_end = get_openrouter_balance().total_usage
    run_cost = or_balance_end - or_balance_initial

    # Persist run statistics to a file for later analysis.
    if best_program is not None:
        save_run_metadata(
            experiment=TARGET_EXAMPLE,  # Name of the experiment
            output_dir=OUTPUT_DIR,
            elapsed_time=elapsed_time,  # Duration in milliseconds
            run_cost=run_cost,  # Cost in dollars spent on API calls
            metrics=best_program.metrics,  # fitness metrics dict
        )
        logger.info(f"Best Program Metrics: {best_program.metrics}")
    else:
        logger.warning("No best program found after evolution run.")
