"""CLI entry point for dcs-utils."""



import re
import webbrowser
from pathlib import Path
from typing import List, Optional

import typer
import typer.rich_utils as ru
from analysis.auto import _find_repo_root, run_analysis, run_coverage_report, USABILITY_SECTIONS
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

publish_app = typer.Typer(help="Publish characters and reports to production.")
publish_report_app = typer.Typer(help="Publish a report's evaluation results.")
publish_app.add_typer(publish_report_app, name="report")
app.add_typer(publish_app, name="publish")


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

    sections = USABILITY_SECTIONS if template == "usability" else None
    with _console.status(f"Generating report: {title!r}...", spinner="dots"):
        html = run_analysis(data, title=title, with_todos=with_todos, sections=sections)
    _console.print(f"[green]✔[/green] Generating report: {title!r}", style="dim")

    # ------------------------------------------------------------------
    # simulation_quality: default output path derived from NPC HIDs
    # ------------------------------------------------------------------
    if template == "simulation_quality" and report_path is None:
        try:
            from analysis.auto.publish import parse_sim_quality_table
            npc_rows = parse_sim_quality_table(html)
            if npc_rows:
                sorted_hids = "_".join(sorted(r["npc_hid"] for r in npc_rows))
                out_dir = (cwd / "results").resolve()
                out_dir.mkdir(parents=True, exist_ok=True)
                output_path = out_dir / f"{sorted_hids}.html"
            else:
                output_path = None
        except Exception:
            output_path = None

    if report_path is not None:
        output_path = report_path.resolve()
    elif template != "simulation_quality" or output_path is None:
        out_dir = (cwd / "results").resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        output_path = out_dir / f"{_slugify(title)}.html"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    _console.print(f"Report written to: {output_path}", style="dim")

    if open_browser:
        webbrowser.open(output_path.as_uri())


# ---------------------------------------------------------------------------
# publish report simulation_quality
# ---------------------------------------------------------------------------

@publish_report_app.command("simulation_quality")
def _publish_sim_quality_cmd(
    report_path: Path = typer.Argument(
        ...,
        help="Path to the simulation quality HTML report to publish from.",
    ),
    hids: Optional[str] = typer.Option(
        None,
        "--hids",
        help="Comma-separated list of NPC HIDs to publish (default: prompt to select).",
    ),
    evaluator_id: Optional[str] = typer.Option(
        None,
        "--evaluator_id",
        help="Your evaluator ID to record in the evaluation entry.",
    ),
    expertise: Optional[str] = typer.Option(
        None,
        "--evaluator_expertise",
        help="Your expertise type to record in the evaluation entry.",
    ),
) -> None:
    """Publish character evaluation results from a simulation quality report.

    Reads per-NPC ICF/DMS scores from the report, then:
    \b
    1. Appends evaluation entries to database_seeds/dev/character_evaluations.json
    2. Adds missing characters to database_seeds/prod/characters.json
    3. Recomputes database_seeds/prod/release_manifest.json via character-release-policy.yml
    """
    from analysis.auto.publish import (
        build_char_record_from_doc,
        load_json_file,
        parse_sim_quality_table,
        save_json_file,
    )
    from dcs_simulation_engine.utils.fingerprint import compute_character_evaluation_fingerprint
    from dcs_simulation_engine.utils.release_policy import (
        compute_approved_characters,
        load_policy,
        write_manifest,
    )

    # ------------------------------------------------------------------
    # 1. Read and parse report
    # ------------------------------------------------------------------
    report_path = report_path.resolve()
    if not report_path.is_file():
        _console.print(f"ERROR: report not found: {report_path}", style="error")
        raise typer.Exit(1)

    html = report_path.read_text(encoding="utf-8")
    try:
        npc_rows = parse_sim_quality_table(html)
    except ValueError as exc:
        _console.print(f"ERROR: {exc}", style="error")
        raise typer.Exit(1)

    if not npc_rows:
        _console.print("ERROR: no NPC rows found in simulation quality table.", style="error")
        raise typer.Exit(1)

    # ------------------------------------------------------------------
    # 2. Resolve which HIDs to publish
    # ------------------------------------------------------------------
    all_hids = [r["npc_hid"] for r in npc_rows]
    rows_by_hid = {r["npc_hid"]: r for r in npc_rows}

    if hids is not None:
        requested = [h.strip() for h in hids.split(",") if h.strip()]
        unknown = [h for h in requested if h not in rows_by_hid]
        if unknown:
            _console.print(
                f"ERROR: HIDs not found in report: {', '.join(unknown)}. "
                f"Available: {', '.join(all_hids)}",
                style="error",
            )
            raise typer.Exit(1)
        selected_hids = requested
    elif len(all_hids) == 1:
        selected_hids = all_hids
    else:
        _console.print("\nNPCs found in report:")
        for row in npc_rows:
            _console.print(
                f"  [{row['npc_hid']}]  ICF={row['icf']:.1%}  NCo={row['dms']:.1%}  turns={row['turns']}",
                style="dim",
            )
        _console.print("")
        raw = ""
        while not raw:
            raw = typer.prompt(
                f"HIDs to publish (comma-separated) [{', '.join(all_hids)}]",
            ).strip()
            if not raw:
                _console.print("ERROR: you must enter at least one HID.", style="error")
        selected_hids = [h.strip() for h in raw.split(",") if h.strip()]
        unknown = [h for h in selected_hids if h not in rows_by_hid]
        if unknown:
            _console.print(f"ERROR: unknown HIDs: {', '.join(unknown)}", style="error")
            raise typer.Exit(1)

    selected_rows = [rows_by_hid[h] for h in selected_hids]

    # ------------------------------------------------------------------
    # 3. Locate repo files
    # ------------------------------------------------------------------
    repo_root = _find_repo_root()
    evals_path       = repo_root / "database_seeds" / "dev" / "character_evaluations.json"
    prod_chars_path  = repo_root / "database_seeds" / "prod" / "characters.json"
    dev_chars_path   = repo_root / "database_seeds" / "dev" / "characters.json"
    manifest_path    = repo_root / "database_seeds" / "prod" / "release_manifest.json"
    policy_path      = repo_root / "character-release-policy.yml"

    prod_chars: list[dict] = load_json_file(prod_chars_path) if prod_chars_path.exists() else []
    dev_chars:  list[dict] = load_json_file(dev_chars_path)  if dev_chars_path.exists()  else []
    evaluations: list[dict] = load_json_file(evals_path)     if evals_path.exists()       else []

    prod_hids = {c["hid"] for c in prod_chars}
    dev_by_hid = {c["hid"]: c for c in dev_chars}

    # ------------------------------------------------------------------
    # 4. Pre-compute what will change
    # ------------------------------------------------------------------
    report_id = "_".join(sorted(selected_hids))

    if not evaluator_id:
        evaluator_id = typer.prompt("evaluator_id").strip()
    if not expertise:
        expertise = typer.prompt("expertise").strip()
    eval_id = evaluator_id

    new_eval_entries: list[dict] = []
    chars_to_add: list[dict] = []
    chars_missing_from_dev: list[str] = []

    for row in selected_rows:
        hid = row["npc_hid"]
        # Find character doc (prod first, then dev)
        char_doc = next((c for c in prod_chars if c["hid"] == hid), None)
        if char_doc is None:
            char_doc = dev_by_hid.get(hid)
        if char_doc is None:
            chars_missing_from_dev.append(hid)
            continue

        record = build_char_record_from_doc(char_doc)
        fp = compute_character_evaluation_fingerprint(record)

        new_eval_entries.append({
            "fingerprint":    fp,
            "evaluator_id":   eval_id,
            "expertise":      expertise,
            "character_hid":  hid,
            "report_id":      report_id,
            "scores": {
                "icf": row["icf"],
                "rf":  0.0,
                "dms": row["dms"],
            },
        })

        if hid not in prod_hids:
            chars_to_add.append(char_doc)

    if chars_missing_from_dev:
        _console.print(
            f"ERROR: HIDs not found in prod or dev characters.json: "
            f"{', '.join(chars_missing_from_dev)}",
            style="error",
        )
        raise typer.Exit(1)

    # ------------------------------------------------------------------
    # 5. Print change summary
    # ------------------------------------------------------------------
    _console.print(f"\nPublishing [bold]{len(selected_hids)}[/bold] character(s) from:")
    _console.print(f"  {report_path}", style="dim")
    _console.print("")

    for row in selected_rows:
        _console.print(
            f"  {row['npc_hid']}  ICF=[bold]{row['icf']:.1%}[/bold]  "
            f"NCo={row['dms']:.1%}  turns={row['turns']}",
            style="dim",
        )

    _console.print("\n[bold]Changes:[/bold]")

    # [1] evaluations
    _console.print(f"  [1] {evals_path.relative_to(repo_root)}")
    for entry in new_eval_entries:
        _console.print(
            f"      + append evaluation for {entry['character_hid']}  "
            f"(ICF={entry['scores']['icf']:.1%})",
            style="dim",
        )

    # [2] prod characters
    _console.print(f"  [2] {prod_chars_path.relative_to(repo_root)}")
    if chars_to_add:
        for doc in chars_to_add:
            _console.print(f"      + add {doc['hid']}", style="dim")
    else:
        skipped = ", ".join(selected_hids)
        _console.print(f"      (no changes — {skipped} already present)", style="dim")

    # [3] manifest
    _console.print(f"  [3] {manifest_path.relative_to(repo_root)}")
    _console.print(
        f"      + recompute approved_characters  "
        f"(policy: {policy_path.name})",
        style="dim",
    )

    _console.print(f"\n  [dim]To revert: git checkout -- {repo_root / 'database_seeds'}[/dim]")

    # ------------------------------------------------------------------
    # 6. Confirm
    # ------------------------------------------------------------------
    _console.print("")
    confirmed = typer.confirm("Proceed?")
    if not confirmed:
        _console.print("Aborted.", style="warning")
        raise typer.Exit(0)

    # ------------------------------------------------------------------
    # 7. Execute step 1 — append evaluation entries
    # ------------------------------------------------------------------
    evaluations.extend(new_eval_entries)
    save_json_file(evals_path, evaluations)
    _console.print(
        f"[green]✔[/green] Appended {len(new_eval_entries)} evaluation(s) to "
        f"{evals_path.relative_to(repo_root)}",
        style="dim",
    )

    # ------------------------------------------------------------------
    # 8. Execute step 2 — add missing characters to prod
    # ------------------------------------------------------------------
    if chars_to_add:
        prod_chars.extend(chars_to_add)
        save_json_file(prod_chars_path, prod_chars)
        added_hids = ", ".join(d["hid"] for d in chars_to_add)
        _console.print(
            f"[green]✔[/green] Added {len(chars_to_add)} character(s) to "
            f"{prod_chars_path.relative_to(repo_root)}: {added_hids}",
            style="dim",
        )
    else:
        _console.print(
            f"[green]✔[/green] {prod_chars_path.relative_to(repo_root)} unchanged "
            f"(all characters already present)",
            style="dim",
        )

    # ------------------------------------------------------------------
    # 9. Execute step 3 — recompute release manifest
    # ------------------------------------------------------------------
    policy = load_policy(policy_path)
    updated_prod_chars: list[dict] = load_json_file(prod_chars_path)
    prod_chars_by_hid = {c["hid"]: c for c in updated_prod_chars}
    updated_evals: list[dict] = load_json_file(evals_path)

    approved = compute_approved_characters(policy, updated_evals, prod_chars_by_hid)
    policy_version: str = policy.get("policy_version", "unknown")
    write_manifest(manifest_path, approved, policy_version)

    _console.print(
        f"[green]✔[/green] Manifest updated: {len(approved)} approved character(s) "
        f"→ {manifest_path.relative_to(repo_root)}",
        style="dim",
    )
    _console.print("\n[success]Done.[/success]")


def main() -> None:
    """Entrypoint for the dcs-utils CLI."""
    app()


if __name__ == "__main__":
    main()
