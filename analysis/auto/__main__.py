"""CLI entry point.

Usage:
    python -m dcs_utils.analysis.auto <results_dir> [options]

Options:
    --output-dir DIR    Directory to write the report (default: results_dir)
    --output-file FILE  Output filename (default: auto_analysis_report.html)
    --title TEXT        Report title (default: experiment name or generic title)
    --open              Open the report in the default browser after generation
"""

from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path

from dcs_utils.analysis.auto import run_analysis
from dcs_utils.analysis.common.loader import load_all


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m dcs_utils.analysis.auto",
        description="Generate a self-contained HTML analysis report from DCS results.",
    )
    parser.add_argument(
        "results_dir",
        type=Path,
        help="Path to the results directory (contains sessions.json, players.json, etc.).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory to write the HTML report (default: results_dir).",
    )
    parser.add_argument(
        "--output-file",
        type=str,
        default="auto_analysis_report.html",
        help="Output filename (default: auto_analysis_report.html).",
    )
    parser.add_argument(
        "--title",
        type=str,
        default=None,
        help="Report title (default: experiment name from experiments.json).",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        default=False,
        help="Open the report in the default browser after generation.",
    )
    args = parser.parse_args()

    results_dir = args.results_dir.resolve()
    if not results_dir.is_dir():
        print(f"ERROR: not a directory: {results_dir}", file=sys.stderr)
        sys.exit(1)

    output_dir = (args.output_dir or results_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / args.output_file

    print(f"Loading results from: {results_dir}")
    data = load_all(results_dir)

    title = args.title or data.experiment.get("name") or "DCS Analysis Report"
    print(f"Generating report: {title!r}")

    html = run_analysis(data, title=title)
    output_path.write_text(html, encoding="utf-8")
    print(f"Report written to:  {output_path}")

    if args.open:
        webbrowser.open(output_path.as_uri())


if __name__ == "__main__":
    main()
