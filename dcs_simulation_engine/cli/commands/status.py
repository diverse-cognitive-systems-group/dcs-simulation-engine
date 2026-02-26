"""CLI status command function."""

import os
from typing import Any, Dict

import typer
from rich.console import Console
from rich.table import Table

from dcs_simulation_engine.cli.common import check_localhost_http, done, step
from dcs_simulation_engine.infra import deploy
from dcs_simulation_engine.infra.fly import (
    FlyError,
    list_machines,
)
from dcs_simulation_engine.utils.misc import as_str, fmt_dt, fmt_uptime, parse_iso

IS_PROD = os.environ.get("DCS_ENV", "dev").lower() == "prod"
console = Console()


def _app_access_link(app_name: str) -> str:
    return f"https://{app_name}.fly.dev"


def _summarize_machines(
    machines: list,
):
    """Summarize machines."""
    if not machines:
        return ("No machines", "0", "—")

    def norm_state(m: Dict[str, Any]) -> str:
        return as_str(m, "state", "State", "status", "Status", default="").lower()

    states = [norm_state(m) for m in machines]
    total = len(machines)

    running = sum(1 for s in states if s in {"started", "running"})
    stoppedish = sum(
        1 for s in states if s in {"stopped", "stopping", "destroyed", "suspended"}
    )
    other = total - running - stoppedish

    if running == total:
        status = "Running"
    elif running > 0:
        status = "Degraded"
    else:
        # no running machines -> treat as stopped/suspended-ish for CLI purposes
        status = "Stopped"

    created_times = [
        parse_iso(as_str(m, "created_at", "CreatedAt", "created")) for m in machines
    ]
    created_times = [t for t in created_times if t]
    created = min(created_times) if created_times else None

    counts = (
        f"{total} (running {running})"
        if other == 0
        else f"{total} (running {running}, other {other})"
    )

    return (status, counts, fmt_dt(created))


def status() -> None:
    """Check status of simulation engine."""
    step("Checking local deployment on localhost:8080...")
    local_status, local_detail = check_localhost_http(port=8080, path="/")
    done()

    step("Fetching deployments...")
    try:
        apps = deploy.list_deployments()
    except FlyError as e:
        done()
        msg = str(e)
        if "flyctl not found" in msg.lower() or "not found on path" in msg.lower():
            typer.secho(
                "flyctl not found. Install Fly CLI to check status.",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(code=1)
        typer.secho(f"Failed to fetch deployments: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    done()

    table = Table(
        title="Simulation Engine Run Status",
        show_header=True,
    )
    table.add_column("Location")
    table.add_column("Deployment")
    table.add_column("Status")
    table.add_column("Uptime")
    table.add_column("Machines")
    table.add_column("Players")
    table.add_column("Runs")
    table.add_column("Widget link")

    any_rows = False

    if local_status == "Live":
        table.add_row(
            "local",
            "default",
            "Running",
            "-",
            "—",
            f"http://localhost:8080 ({local_detail})",
        )
        any_rows = True

    if not apps and not any_rows:
        table.add_row("—", "—", "No deployments found", "—", "—", "—", "—", "—")
        console.print(table)
        typer.echo()
        return

    for app in apps:
        app_name = as_str(app, "Name", "name")
        access = _app_access_link(app_name) if app_name != "—" else "—"

        try:
            step(f"Fetching machines for {app_name}...")
            machines = list_machines(app_name)
            done()
        except FlyError as e:
            table.add_row(
                "fly.io", app_name, f"Failed: {e}", "—", "—", "—", "—", access
            )
            any_rows = True
            continue

        step(f"Summarizing machines for {app_name}...")
        status_summary, machine_counts, created = _summarize_machines(machines)
        done()

        created_dt = parse_iso(created) if created != "—" else None
        uptime = fmt_uptime(created_dt)

        # TODO: implement this!
        # players = get_players_count(app_name)
        # runs = get_runs_count(app_name)
        players = "—"
        runs = "—"

        table.add_row(
            "fly.io",
            app_name,
            status_summary,
            uptime,
            machine_counts,
            str(players),
            str(runs),
            access,
        )
        any_rows = True

    if not any_rows:
        table.add_row("—", "—", "No runs found", "—", "—", "—", "—", "—")

    typer.echo()
    console.print(table)

    typer.echo()
    typer.secho(
        "Tip: use `fly --help` for detailed troubleshooting of specific apps.",
        fg=typer.colors.YELLOW,
    )
