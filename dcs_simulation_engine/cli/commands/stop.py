"""CLI stop command function."""

import os
from typing import Optional

import typer
from dcs_simulation_engine.cli.bootstrap import (
    create_provider,
    create_provider_admin,
    teardown_local_backend,
)
from dcs_simulation_engine.cli.common import (
    console,
    select_run,
    step,
)
from dcs_simulation_engine.core.constants import (
    OUTPUT_FPATH,
)
from dcs_simulation_engine.helpers.run_helpers import (
    STATUS,
    local_run_name,
    run_status,
    update_run,
)

IS_PROD = os.environ.get("DCS_ENV", "dev").lower() == "prod"


def stop(
    ctx: typer.Context,
    run_name: Optional[str] = typer.Option(
        None, "--run-name", "-r", help="Run name. If omitted, you will be prompted."
    ),
    destroy: bool = typer.Option(
        False,
        "--destroy",
        help="Permanently delete this run (remote + local). Destructive; cannot be restarted.",
    ),
) -> None:
    """Stop simulation engine (optionally save artifacts; optionally delete the run)."""
    selected_run = select_run(ctx, run_name)

    local_run = local_run_name()
    selected_run_status = run_status(selected_run)
    if not destroy:
        if selected_run_status == STATUS.STOPPED:
            console.print(
                f"Run '{selected_run}' is already stopped. Use --destroy to delete it.",
                style="warning",
            )
            raise typer.Exit()

        if selected_run == local_run:
            console.print(
                "A local run must be stopped manually using Ctrl+C in the terminal where its running.",
                style="error",
            )
            raise typer.Exit(code=1)
        else:  # remote deployment stop logic here (if applicable)
            console.print(f"Stopping run {selected_run}")
            console.print("Stopping remote deployments not implemented yet", style="error")
            raise typer.Exit(code=1)
    else:
        run_results_dir = OUTPUT_FPATH / selected_run
        console.print()
        console.print(
            "WARNING: This will permanently delete this run.\n",
            "It cannot be restarted, but run data will be saved.",
            style="error",
        )
        if not typer.confirm("Continue?", default=False):
            console.print("Cancelled.", style="warning")
            raise typer.Exit(code=1)
        console.print(f"Destroying run instance: '{selected_run}'")
        try:
            with step("Saving db"):
                create_provider_admin(create_provider()).backup_db(run_results_dir, append_ts=False)
            with step("Saving metadata"):
                update_run(selected_run, status=STATUS.DESTROYED)
        except Exception as e:
            console.print()
            console.print("Artifact save failed. Aborting delete.", style="error")
            console.print(str(e))
            raise typer.Exit(code=1)

        with step("Destroying run"):
            if selected_run == local_run:
                if selected_run_status == STATUS.RUNNING:
                    console.print(
                        "A local run must be stopped manually using Ctrl+C in the terminal "
                        "where its running before it can be destroyed.",
                        style="error",
                    )
                    raise typer.Exit(code=1)
                else:  # status is stopped
                    teardown_local_backend(wipe=True)
            else:  # remote run
                console.log("Destroying remote runs not implemented yet.", style="error")

        console.print(f"Deleted run: {selected_run}", style="success")
