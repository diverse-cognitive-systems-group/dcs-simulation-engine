"""CLI status command function."""

import os
from typing import Any, Dict

import typer
from rich.console import Console
from rich.table import Table

from dcs_simulation_engine.cli.common import step
from dcs_simulation_engine.helpers.run_helpers import load_runs, run_status, run_uptime
from dcs_simulation_engine.utils.misc import as_str, fmt_dt, parse_iso

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
    with step("Fetching run data"):
        runs = load_runs()

    table = Table(
        title="Simulation Engine Run Instances",
        show_header=True,
        header_style="bold white",
    )
    table.add_column("Name")
    table.add_column("Status")
    table.add_column("Uptime")
    table.add_column("Link")

    if not runs:
        table.add_row("—", "—", "No runs found", "—")
        console.print(table)
        typer.echo()
        return

    for name in runs:
        run = runs[name]
        status = run_status(name).value.capitalize()
        uptime = run_uptime(name, format=True)
        table.add_row(
            name,
            status,
            uptime,
            run.get("link") or "—",
        )

    typer.echo()
    console.print(table)

    typer.echo()
    console.print(
        "Tip: use `fly --help` for detailed troubleshooting of specific apps.",
        style="dim",
    )
