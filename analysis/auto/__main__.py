"""CLI entry point for dcs-utils."""



import re
import webbrowser
from pathlib import Path
from typing import List, Optional

import typer
import typer.rich_utils as ru
from analysis.auto import run_analysis, run_coverage_report
from analysis.common.loader import load_all
from rich.console import Console
from rich.theme import Theme

_cli_theme = Theme(
    {
        "success": "green",
        "warning": "bold bright_yellow",
        "error": "bold bright_red",
    }
)
_console = Console(theme=_cli_theme)

ru.STYLE_OPTION = "bold white"
ru.STYLE_SWITCH = "bold white"
ru.STYLE_NEGATIVE_OPTION = "bold white"
ru.STYLE_NEGATIVE_SWITCH = "bold white"
ru.STYLE_METAVAR = "bold white"
ru.STYLE_METAVAR_SEPARATOR = "dim"
ru.STYLE_USAGE = "white"
ru.STYLE_USAGE_COMMAND = "bold"
ru.STYLE_DEPRECATED = "white"
ru.STYLE_DEPRECATED_COMMAND = "dim"
ru.STYLE_HELPTEXT_FIRST_LINE = ""
ru.STYLE_HELPTEXT = "dim"
ru.STYLE_OPTION_HELP = ""
ru.STYLE_OPTION_DEFAULT = "dim"
ru.STYLE_OPTION_ENVVAR = "dim white"
ru.STYLE_REQUIRED_SHORT = "white"
ru.STYLE_REQUIRED_LONG = "dim white"
ru.STYLE_OPTIONS_PANEL_BORDER = "dim"
ru.STYLE_COMMANDS_PANEL_BORDER = "dim"
ru.STYLE_COMMANDS_TABLE_FIRST_COLUMN = "bold white"
ru.STYLE_ERRORS_PANEL_BORDER = "white"
ru.STYLE_ERRORS_SUGGESTION = "dim"
ru.STYLE_ABORTED = "white"

app = typer.Typer(help="DCS utility commands.")
generate_app = typer.Typer(help="Generate artifacts (reports, etc.).")
app.add_typer(generate_app, name="generate")


def _find_latest_run(runs_dir: Path) -> Path:
    candidates = sorted(
        (p for p in runs_dir.iterdir() if p.is_dir()),
        key=lambda p: p.name,
    )
    if not candidates:
        raise typer.BadParameter(f"No run directories found in {runs_dir}")
    return candidates[-1]


def _slugify(text: str) -> str:
    """Convert a title to a safe filename stem."""
    slug = text.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_-]+", "_", slug)
    return slug.strip("_") or "report"


_VALID_TEMPLATES = {"default", "usability", "simulation_quality", "character_coverage"}
_TEMPLATE_TITLES = {
    "usability": "Usability Report",
    "simulation_quality": "Simulation Quality Report",
    "character_coverage": "Character Coverage Report",
}


@generate_app.command("report")
def _generate_report_cmd(
    results_dir: Optional[Path] = typer.Argument(
        default=None,
        help=(
            "Path to the results directory. "
            "Defaults to the latest run in ./runs/. "
            "Ignored for --template character_coverage."
        ),
    ),
    template: str = typer.Option(
        "default",
        "--template",
        help="Report template: default | usability | simulation_quality | character_coverage.",
    ),
    report_path: Optional[Path] = typer.Option(
        None,
        "--report_path",
        help="Output path for the HTML file. Defaults to ./results/<title>.html.",
    ),
    character_hids: Optional[List[str]] = typer.Option(
        None,
        "--character_hids",
        help="(character_coverage only) Limit analysis to these character HIDs.",
    ),
    title: Optional[str] = typer.Option(
        None,
        "--title",
        help="Override the report title.",
    ),
    open_browser: bool = typer.Option(
        False,
        "--open",
        help="Open the report in the default browser after generation.",
    ),
) -> None:
    cwd = Path.cwd()

    if template not in _VALID_TEMPLATES:
        valid = " | ".join(sorted(_VALID_TEMPLATES))
        _console.print(f"ERROR: unknown template {template!r}. Valid options: {valid}", style="error")
        raise typer.Exit(1)

    # ------------------------------------------------------------------
    # character_coverage: standalone path — no results dir needed
    # ------------------------------------------------------------------
    if template == "character_coverage":
        final_title = title or _TEMPLATE_TITLES["character_coverage"]
        if report_path is not None:
            output_path = report_path.resolve()
        else:
            out_dir = (cwd / "results").resolve()
            out_dir.mkdir(parents=True, exist_ok=True)
            output_path = out_dir / "character_coverage_report.html"

        output_path.parent.mkdir(parents=True, exist_ok=True)

        with _console.status("Generating character coverage report...", spinner="dots"):
            html = run_coverage_report(hids_filter=character_hids or None)
        _console.print("[green]✔[/green] Generated character coverage report", style="dim")
        output_path.write_text(html, encoding="utf-8")
        _console.print(f"Report written to: {output_path}", style="dim")
        if open_browser:
            webbrowser.open(output_path.as_uri())
        return

    # ------------------------------------------------------------------
    # All other templates require a results directory
    # ------------------------------------------------------------------
    if results_dir is None:
        runs_dir = cwd / "runs"
        if not runs_dir.is_dir():
            _console.print("ERROR: no results_dir given and ./runs/ not found", style="error")
            raise typer.Exit(1)
        results_dir = _find_latest_run(runs_dir)
        _console.print(f"Using latest run: {results_dir}", style="dim")

    results_dir = results_dir.resolve()
    if not results_dir.is_dir():
        _console.print(f"ERROR: not a directory: {results_dir}", style="error")
        raise typer.Exit(1)

    with _console.status("Loading results...", spinner="dots"):
        data = load_all(results_dir)
    _console.print(f"[green]✔[/green] Loaded results from: {results_dir}", style="dim")

    with_todos = template in ("usability", "simulation_quality")

    if title is None:
        title = _TEMPLATE_TITLES.get(template)
        if title is None:  # "default"
            run_config = data.experiment.get("run_config") or {}
            title = (
                (run_config.get("name") if isinstance(run_config, dict) else None)
                or data.experiment.get("name")
                or "Results Report"
            )

    if report_path is not None:
        output_path = report_path.resolve()
    else:
        out_dir = (cwd / "results").resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        output_path = out_dir / f"{_slugify(title)}.html"

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with _console.status(f"Generating report: {title!r}...", spinner="dots"):
        html = run_analysis(data, title=title, with_todos=with_todos)
    _console.print(f"[green]✔[/green] Generating report: {title!r}", style="dim")

    output_path.write_text(html, encoding="utf-8")
    _console.print(f"Report written to: {output_path}", style="dim")

    if open_browser:
        webbrowser.open(output_path.as_uri())


def main() -> None:
    """Entrypoint for the dcs-utils CLI."""
    app()


if __name__ == "__main__":
    main()
