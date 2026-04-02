"""CLI entry point for dcs-analyze."""



import re
import webbrowser
from pathlib import Path
from typing import Optional

import typer
import typer.rich_utils as ru
from analysis.auto import run_analysis
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

app = typer.Typer(help="Generate a self-contained HTML analysis report from DCS results.")


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


@app.command()
def _cmd(
    results_dir: Optional[Path] = typer.Argument(
        default=None,
        help="Path to the results directory. Defaults to the latest run in ./runs/.",
    ),
    output_dir: Optional[Path] = typer.Option(
        None,
        "--output-dir",
        help="Directory to write the HTML report. Defaults to <cwd>/results/.",
    ),
    output_file: Optional[str] = typer.Option(
        None,
        "--output-file",
        help="Output filename. Defaults to <title>.html (auto-incremented to avoid overwrites).",
    ),
    title: Optional[str] = typer.Option(
        None,
        "--title",
        help="Report title. Defaults to the run_config name from the experiment record.",
    ),
    open_browser: bool = typer.Option(
        False,
        "--open",
        help="Open the report in the default browser after generation.",
    ),
) -> None:
    cwd = Path.cwd()

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

    out_dir = (output_dir or cwd / "results").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    with _console.status("Loading results...", spinner="dots"):
        data = load_all(results_dir)
    _console.print(f"[green]✔[/green] Loaded results from: {results_dir}", style="dim")

    if title is None:
        run_config = data.experiment.get("run_config") or {}
        title = (
            (run_config.get("name") if isinstance(run_config, dict) else None)
            or data.experiment.get("name")
            or "Results Report"
        )

    if output_file is not None:
        output_path = out_dir / output_file
    else:
        output_path = out_dir / f"{_slugify(title)}.html"

    with _console.status(f"Generating report: {title!r}...", spinner="dots"):
        html = run_analysis(data, title=title)
    _console.print(f"[green]✔[/green] Generating report: {title!r}", style="dim")

    output_path.write_text(html, encoding="utf-8")
    _console.print(f"Report written to: {output_path}", style="dim")

    if open_browser:
        webbrowser.open(output_path.as_uri())


def main() -> None:
    """Entrypoint for the dcs-analyze CLI."""
    app()


if __name__ == "__main__":
    main()
