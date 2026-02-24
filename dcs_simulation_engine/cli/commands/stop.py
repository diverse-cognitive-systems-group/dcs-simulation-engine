"""CLI stop command function."""

import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from dcs_simulation_engine.cli.common import done, select_deployment, step
from dcs_simulation_engine.infra import deploy
from dcs_simulation_engine.infra.fly import FlyError, download_logs_jsonl

console = Console()

IS_PROD = os.environ.get("DCS_ENV", "dev").lower() == "prod"


def _default_paths(app: str) -> tuple[Path, Path, str]:
    """Default save locations."""
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = Path("results") / app / run_id

    db_out = base / "database" / "db.sqlite3"
    logs_out = base / "logs" / "logs.jsonl"

    db_out.parent.mkdir(parents=True, exist_ok=True)
    logs_out.parent.mkdir(parents=True, exist_ok=True)

    return db_out, logs_out, run_id


def stop(
    ctx: typer.Context,
    deployment: Optional[str] = typer.Argument(
        None, help="Deployment name (Fly app name). If omitted, you will be prompted."
    ),
    logs_out: Optional[Path] = typer.Option(
        None,
        "--logs-out",
        help="Write recent logs to this file (JSON lines). Defaults to results/<deployment>/<run_id>/logs/logs.jsonl",
        dir_okay=False,
        file_okay=True,
    ),
    logs_no_tail: bool = typer.Option(
        True, "--no-tail/--tail", help="Fetch buffered logs only."
    ),
    db_remote: Optional[str] = typer.Option(
        None,
        "--db-remote",
        help="Remote DB file path on the VM to download. If omitted, DB download is skipped.",
    ),
    db_out: Optional[Path] = typer.Option(
        None,
        "--db-out",
        help="Local path to save the downloaded DB file. Defaults to results/<deployment>/<run_id>/database/db.sqlite3",
        dir_okay=False,
        file_okay=True,
    ),
    no_save: bool = typer.Option(
        False, "--no-save", help="Skip downloading DB and logs before stopping."
    ),
    destroy: bool = typer.Option(
        False,
        "--destroy",
        help="Destroy the Fly app (deletes deployment). Destructive.",
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Do not prompt for confirmation."
    ),
) -> None:
    """Stop simulation engine (optionally save artifacts; optionally destroy deployment)."""
    # 1) Pick deployment (prompt if omitted)
    app, local_is_running = select_deployment(ctx, deployment, include_local=True)

    # 2) Default save locations (unless --no-save)
    # We create ONE run_id folder and put both artifacts under it.
    run_id: Optional[str] = None
    if not no_save:
        default_db_out, default_logs_out, run_id = _default_paths(app)

        # logs should default-save unless user explicitly disables saving
        if logs_out is None:
            logs_out = default_logs_out

        # DB only defaults if user indicated they want a DB download (db_remote provided)
        if db_remote and db_out is None:
            db_out = default_db_out

    # 3) Validate DB args
    missing_db_out = bool(db_remote) and (db_out is None)
    missing_db_remote = bool(db_out) and (db_remote is None)

    if missing_db_out or missing_db_remote:
        typer.secho(
            "DB download requires both --db-remote and --db-out.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=2)

    # 4) Destroy warning if nothing will be saved
    # "Anything being saved" means: logs_out set OR db_remote+db_out set.
    has_any_targets = (logs_out is not None) or bool(db_remote and db_out)
    if destroy and (no_save or not has_any_targets):
        warn = (
            "You are about to DESTROY the deployment. This can permanently delete data "
            "stored on the VM (including any unsaved DB/logs)."
        )
        typer.secho(warn, fg=typer.colors.YELLOW, bold=True)
        if not force:
            ok = typer.confirm(
                "Continue without saving artifacts?",
                default=False,
            )
            if not ok:
                typer.secho("Aborted.", fg=typer.colors.YELLOW)
                raise typer.Exit(code=1)

    # 5) Confirmation prompt (for stop and especially destroy)
    if destroy:
        typer.secho(
            f"DESTRUCTIVE: This will delete the Fly app '{app}' without saving anything!",
            fg=typer.colors.RED,
            bold=True,
        )
        if not force:
            ok = typer.confirm(
                f"Type yes to destroy '{app}'",
                default=False,
            )
            if not ok:
                typer.secho("Aborted.", fg=typer.colors.YELLOW)
                raise typer.Exit(code=1)
    else:
        if not force:
            ok = typer.confirm(f"Stop '{app}' (scale to 0)?", default=True)
            if not ok:
                typer.secho("Aborted.", fg=typer.colors.YELLOW)
                raise typer.Exit(code=1)

    # 6) Save step (unless --no-save)
    # Make saves BEFORE stopping/destroying.
    if not no_save:
        if run_id:
            typer.secho(
                f"Saving artifacts under results/{app}/{run_id}/",
                fg=typer.colors.BLUE,
            )

        if logs_out is not None:
            try:
                step(f"Saving logs to {logs_out}...")
                download_logs_jsonl(
                    app_name=app, no_tail=logs_no_tail, out_path=logs_out
                )
                done()
            except Exception as e:
                done()
                typer.secho(f"Failed to save logs: {e}", fg=typer.colors.RED, err=True)
                if destroy and not force:
                    if not typer.confirm("Continue anyway?", default=False):
                        raise typer.Exit(code=1)

        if db_remote and db_out:
            try:
                step(f"Downloading DB to {db_out}...")
                # FIXME: STOPPED HERE
                done()
            except Exception as e:
                done()
                typer.secho(
                    f"Failed to download DB: {e}", fg=typer.colors.RED, err=True
                )
                if destroy and not force:
                    if not typer.confirm("Continue anyway?", default=False):
                        raise typer.Exit(code=1)

    # 7) Stop or destroy
    if destroy:
        try:
            step(f"Destroying deployment {app}...")
            deploy.destroy_deployment(app)
            done()
        except FlyError as e:
            done()
            typer.secho(
                f"Failed to destroy '{app}': {e}", fg=typer.colors.RED, err=True
            )
            raise typer.Exit(code=1)
    else:
        try:
            step(f"Stopping {app}...")
            deploy.stop_deployment(deployment=app)
            done()
        except FlyError as e:
            done()
            typer.secho(f"Failed to stop '{app}': {e}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)
