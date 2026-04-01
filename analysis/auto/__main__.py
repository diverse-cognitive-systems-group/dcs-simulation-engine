"""CLI entry point for dcs-analyze."""

from __future__ import annotations

import re
import webbrowser
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.theme import Theme

from analysis.auto import run_analysis
from analysis.common.loader import load_all

_cli_theme = Theme(
    {
        "success": "green",
        "warning": "bold bright_yellow",
        "error": "bold bright_red",
    }
)
_console = Console(theme=_cli_theme)

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
    _console.print(f"Report written to: {output_path}", style="success")

    if open_browser:
        webbrowser.open(output_path.as_uri())


def main() -> None:
    app()


if __name__ == "__main__":
    main()
