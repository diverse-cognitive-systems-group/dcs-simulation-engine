"""CLI commands for stopping resources."""

from pathlib import Path
from typing import Optional

import typer

from dcs_simulation_engine.cli.common import echo
from dcs_simulation_engine.infra.deploy import stop_deployment as stop_deployment_op
from dcs_simulation_engine.infra.fly import (
    FlyError,
)

stop_app = typer.Typer(help="Stop resources.")


@stop_app.command("deployment")
def stop_deployment(
    ctx: typer.Context,
    deployment: Optional[str] = typer.Argument(
        None, help="Deployment name (Fly app name). If omitted, you will be prompted."
    ),
    logs_out: Optional[Path] = typer.Option(
        None,
        "--logs-out",
        help="Write recent logs to this file (JSON lines).",
        dir_okay=False,
        file_okay=True,
    ),
    logs_no_tail: bool = typer.Option(
        True, "--no-tail/--tail", help="Fetch buffered logs only."
    ),
    db_remote: Optional[str] = typer.Option(
        None, "--db-remote", help="Remote DB file path on the VM to download."
    ),
    db_out: Optional[Path] = typer.Option(
        None,
        "--db-out",
        help="Local path to save the downloaded DB file.",
        dir_okay=False,
        file_okay=True,
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Do not prompt for confirmation."
    ),
) -> None:
    """Stop a deployment and optionally download logs + DB file before stopping."""
    if not deployment:
        deployment = typer.prompt("Deployment name")

    auto_yes = bool(getattr(ctx.obj, "yes", False))
    if not force and not auto_yes:
        ok = typer.confirm(
            f"Stop deployment '{deployment}'? This will stop its Machines.",
            default=False,
        )
        if not ok:
            echo(ctx, "Cancelled.", style="warning")
            raise typer.Exit(code=0)

    try:
        stopped_ids = stop_deployment_op(
            deployment=deployment,
            logs_out=logs_out,
            logs_no_tail=logs_no_tail,
            db_remote=db_remote,
            db_out=db_out,
        )
    except FlyError as e:
        echo(ctx, f"Failed to stop deployment '{deployment}': {e}", style="error")
        raise typer.Exit(code=1)

    if stopped_ids:
        echo(
            ctx,
            f"Stopped deployment: {deployment} ({len(stopped_ids)} machine(s))",
            style="success",
        )
    else:
        echo(ctx, f"No running machines found for: {deployment}", style="info")

    echo(
        ctx,
        "Cost note: stopped Machines are cheaper than running, but billing is best"
        " verified in Fly invoices/dashboard.",
        style="info",
    )
