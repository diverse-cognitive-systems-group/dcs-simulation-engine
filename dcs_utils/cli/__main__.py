"""CLI entry point for dcs-utils."""

import re
import webbrowser
from pathlib import Path
from typing import List, Optional

import typer
import typer.rich_utils as ru
from dcs_utils.auto import _find_repo_root, run_analysis, run_coverage_report, resolve_sections, VALID_SECTION_SLUGS
from dcs_utils.common.loader import load_all
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

# ---------------------------------------------------------------------------
# App tree
#
#   dcs-utils
#   ├── hitl            human-in-the-loop scenario testing
#   │   ├── create      scaffold a new scenarios file for a character
#   │   ├── update      generate engine responses and/or collect feedback
#   │   └── export      convert completed scenarios → results dir
#   ├── report          report generation
#   │   ├── coverage    character coverage report
#   │   └── results     HTML report from a results directory
#   └── admin           database / publishing operations
#       └── publish
#           └── characters  publish evaluation results
# ---------------------------------------------------------------------------

app = typer.Typer(help="DCS utility commands.")

# -- hitl --
hitl_app = typer.Typer(help="Human-in-the-loop scenario testing pipeline.")
app.add_typer(hitl_app, name="hitl")

# -- report --
report_app = typer.Typer(help="Generate HTML reports.")
app.add_typer(report_app, name="report")

# -- admin --
admin_app = typer.Typer(help="Database and publishing operations.")
admin_publish_app = typer.Typer(help="Publish evaluation results to production.")
admin_app.add_typer(admin_publish_app, name="publish")
app.add_typer(admin_app, name="admin")


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_VALID_DB = {"dev", "prod"}


def _slugify(text: str) -> str:
    """Convert a title to a safe filename stem."""
    slug = text.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_-]+", "_", slug)
    return slug.strip("_") or "report"


# ---------------------------------------------------------------------------
# dcs-utils report coverage
# ---------------------------------------------------------------------------


@report_app.command("coverage")
def _report_coverage_cmd(
    db: str = typer.Option(
        ...,
        "--db",
        help="Character database to use: dev or prod.",
    ),
    title: Optional[str] = typer.Option(
        None,
        "--title",
        help="Override the report title.",
    ),
) -> None:
    """Generate the character coverage report from the full database."""
    if db not in _VALID_DB:
        _console.print(f"ERROR: --db must be 'dev' or 'prod', got {db!r}.", style="error")
        raise typer.Exit(1)

    out_dir = (Path.cwd() / "results").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    output_path = out_dir / f"character_coverage_{db}.html"

    with _console.status(f"Generating character coverage report ({db})...", spinner="dots"):
        html = run_coverage_report(db=db)
    _console.print("[green]✔[/green] Generated character coverage report", style="dim")
    output_path.write_text(html, encoding="utf-8")
    _console.print(f"Report written to: {output_path}", style="dim")


# ---------------------------------------------------------------------------
# dcs-utils report results
# ---------------------------------------------------------------------------


@report_app.command("results")
def _report_results_cmd(
    results_dir: Path = typer.Argument(
        ...,
        help="Path to the results directory.",
    ),
    only: Optional[List[str]] = typer.Option(
        None,
        "--only",
        help=(
            "Render ONLY these section(s). Repeatable. "
            f"Valid slugs: {', '.join(sorted(VALID_SECTION_SLUGS))}."
        ),
    ),
    include: Optional[List[str]] = typer.Option(
        None,
        "--include",
        help=(
            "Add section(s) to the default set. Repeatable. "
            f"Valid slugs: {', '.join(sorted(VALID_SECTION_SLUGS))}."
        ),
    ),
    exclude: Optional[List[str]] = typer.Option(
        None,
        "--exclude",
        help=(
            "Remove section(s) from the default set. Repeatable. "
            f"Valid slugs: {', '.join(sorted(VALID_SECTION_SLUGS))}."
        ),
    ),
    report_path: Optional[Path] = typer.Option(
        None,
        "--report-path",
        help="Output path for the HTML file. Defaults to ./results/<title>.html.",
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
    """Generate an HTML report from a results directory."""
    import html as _html
    import types

    cwd = Path.cwd()

    try:
        sections = resolve_sections(only=only, include=include, exclude=exclude)
    except ValueError as exc:
        _console.print(f"ERROR: {exc}", style="error")
        raise typer.Exit(1)

    results_dir = results_dir.resolve()
    if not results_dir.is_dir():
        _console.print(f"ERROR: not a directory: {results_dir}", style="error")
        raise typer.Exit(1)

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

    # When sim-quality is included, inject a "Per Character Quality Reports"
    # section immediately after it that links to the per-character HTML files
    # written into the per_character_quality/ subfolder.
    section_slugs = {s[0] for s in sections if s[0]}
    npc_hids: list[str] = []
    if "sim-quality" in section_slugs and not data.runs_df.empty and "npc_hid" in data.runs_df.columns:
        npc_hids = sorted(data.runs_df["npc_hid"].dropna().unique().tolist())

    if npc_hids:
        items = "".join(
            f'<li><a href="per_character_quality/{_html.escape(hid)}_quality_report.html">'
            f'{_html.escape(hid)}</a></li>'
            for hid in npc_hids
        )
        links_html = (
            "<p>Per-character quality reports are available for each NPC evaluated in this run.</p>"
            f'<ul class="list-unstyled">{items}</ul>'
        )
        char_links_module = types.SimpleNamespace(render=lambda _data, _h=links_html: _h)

        sim_quality_idx = next(
            (i for i, s in enumerate(sections) if s[0] == "sim-quality"), None
        )
        sections = list(sections)
        insert_at = (sim_quality_idx + 1) if sim_quality_idx is not None else len(sections)
        sections.insert(
            insert_at,
            ("char-quality-links", "Per Character Quality Reports", char_links_module, "sub"),
        )

    section_names = ", ".join(s[0] for s in sections if s[0] and s[3] != "group")
    if only:
        sections_desc = f"only sections: {', '.join(only)}"
    elif include:
        sections_desc = f"default sections including: {', '.join(include)}"
    elif exclude:
        sections_desc = f"default sections excluding: {', '.join(exclude)}"
    else:
        sections_desc = f"default sections: {section_names}"

    with _console.status(f"Generating report: {title!r} ({sections_desc})...", spinner="dots"):
        html = run_analysis(data, title=title, sections=sections)
    _console.print(f"[green]✔[/green] Generated report: {title!r} — {sections_desc}", style="dim")

    if report_path is not None:
        output_path = report_path.resolve()
    else:
        out_dir = (cwd / "results").resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        output_path = out_dir / f"{_slugify(title)}.html"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    _console.print(f"Report written to: {output_path}", style="dim")

    if npc_hids:
        from dcs_utils.auto.sections.simulation_quality import build_character_quality_report

        per_char_dir = output_path.parent / "per_character_quality"
        per_char_dir.mkdir(exist_ok=True)

        for hid in npc_hids:
            char_html = build_character_quality_report(hid, data)
            char_path = per_char_dir / f"{hid}_quality_report.html"
            char_path.write_text(char_html, encoding="utf-8")
            _console.print(f"Character report written to: {char_path}", style="dim")

    if open_browser:
        webbrowser.open(output_path.as_uri())


# ---------------------------------------------------------------------------
# dcs-utils admin publish characters
# ---------------------------------------------------------------------------


@admin_publish_app.command("characters")
def _admin_publish_characters_cmd(
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
        "--evaluator-id",
        help="Your evaluator ID to record in the evaluation entry.",
    ),
    expertise: Optional[str] = typer.Option(
        None,
        "--evaluator-expertise",
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
    from dcs_utils.auto.publish import (
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

    repo_root = _find_repo_root()
    evals_path      = repo_root / "database_seeds" / "dev" / "character_evaluations.json"
    prod_chars_path = repo_root / "database_seeds" / "prod" / "characters.json"
    dev_chars_path  = repo_root / "database_seeds" / "dev" / "characters.json"
    manifest_path   = repo_root / "database_seeds" / "prod" / "release_manifest.json"
    policy_path     = repo_root / "character-release-policy.yml"

    prod_chars: list[dict]   = load_json_file(prod_chars_path) if prod_chars_path.exists() else []
    dev_chars: list[dict]    = load_json_file(dev_chars_path)  if dev_chars_path.exists()  else []
    evaluations: list[dict]  = load_json_file(evals_path)      if evals_path.exists()      else []

    prod_hids = {c["hid"] for c in prod_chars}
    dev_by_hid = {c["hid"]: c for c in dev_chars}

    report_id = "_".join(sorted(selected_hids))

    if not evaluator_id:
        evaluator_id = typer.prompt("evaluator_id").strip()
    if not expertise:
        expertise = typer.prompt("expertise").strip()

    new_eval_entries: list[dict] = []
    chars_to_add: list[dict] = []
    chars_missing_from_dev: list[str] = []

    for row in selected_rows:
        hid = row["npc_hid"]
        char_doc = next((c for c in prod_chars if c["hid"] == hid), None)
        if char_doc is None:
            char_doc = dev_by_hid.get(hid)
        if char_doc is None:
            chars_missing_from_dev.append(hid)
            continue

        record = build_char_record_from_doc(char_doc)
        fp = compute_character_evaluation_fingerprint(record)

        new_eval_entries.append({
            "fingerprint":   fp,
            "evaluator_id":  evaluator_id,
            "expertise":     expertise,
            "character_hid": hid,
            "report_id":     report_id,
            "scores": {
                "icf":               row["icf"],
                "rf":                0.0,
                "dms":               row["dms"],
                "scenario_coverage": row.get("scenario_coverage", 0.0),
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
    _console.print(f"  [1] {evals_path.relative_to(repo_root)}")
    for entry in new_eval_entries:
        _console.print(
            f"      + append evaluation for {entry['character_hid']}  "
            f"(ICF={entry['scores']['icf']:.1%})",
            style="dim",
        )

    _console.print(f"  [2] {prod_chars_path.relative_to(repo_root)}")
    if chars_to_add:
        for doc in chars_to_add:
            _console.print(f"      + add {doc['hid']}", style="dim")
    else:
        _console.print(
            f"      (no changes — {', '.join(selected_hids)} already present)",
            style="dim",
        )

    _console.print(f"  [3] {manifest_path.relative_to(repo_root)}")
    _console.print(
        f"      + recompute approved_characters (policy: {policy_path.name})",
        style="dim",
    )
    _console.print(f"\n  [dim]To revert: git checkout -- {repo_root / 'database_seeds'}[/dim]")

    _console.print("")
    if not typer.confirm("Proceed?"):
        _console.print("Aborted.", style="warning")
        raise typer.Exit(0)

    evaluations.extend(new_eval_entries)
    save_json_file(evals_path, evaluations)
    _console.print(
        f"[green]✔[/green] Appended {len(new_eval_entries)} evaluation(s) to "
        f"{evals_path.relative_to(repo_root)}",
        style="dim",
    )

    if chars_to_add:
        prod_chars.extend(chars_to_add)
        save_json_file(prod_chars_path, prod_chars)
        _console.print(
            f"[green]✔[/green] Added {len(chars_to_add)} character(s) to "
            f"{prod_chars_path.relative_to(repo_root)}: "
            f"{', '.join(d['hid'] for d in chars_to_add)}",
            style="dim",
        )
    else:
        _console.print(
            f"[green]✔[/green] {prod_chars_path.relative_to(repo_root)} unchanged "
            f"(all characters already present)",
            style="dim",
        )

    policy = load_policy(policy_path)
    updated_prod_chars: list[dict] = load_json_file(prod_chars_path)
    prod_chars_by_hid = {c["hid"]: c for c in updated_prod_chars}
    updated_evals: list[dict] = load_json_file(evals_path)

    approved = compute_approved_characters(policy, updated_evals, prod_chars_by_hid)
    write_manifest(manifest_path, approved, policy.get("policy_version", "unknown"))

    _console.print(
        f"[green]✔[/green] Manifest updated: {len(approved)} approved character(s) "
        f"→ {manifest_path.relative_to(repo_root)}",
        style="dim",
    )
    _console.print("\n[success]Done.[/success]")


# ---------------------------------------------------------------------------
# dcs-utils hitl create
# ---------------------------------------------------------------------------

@hitl_app.command("create")
def _hitl_create_cmd(
    hid: str = typer.Argument(..., help="Character HID (e.g. FW, NA, AC)."),
    db: str = typer.Option(
        ...,
        "--db",
        help="Character seed database to read from: dev or prod.",
    ),
    game: str = typer.Option(
        "Explore",
        "--game",
        help="Game name to use for all generated scenarios.",
    ),
) -> None:
    """Create a scenario scaffold for a character.

    Writes dcs_utils/data/character_scenarios/<hid>-scenarios.json with one
    scenario group per pressure category, seeded with example player messages.
    All conversation_history fields start empty — run `dcs-utils hitl update`
    to populate them via the engine.
    """
    from dcs_utils.hitl.generate import (
        build_scaffold,
        load_character,
        save_scaffold,
        scenarios_path_for,
    )
    from dcs_utils.hitl.responses import compute_status_summary, render_status_summary

    if db not in _VALID_DB:
        _console.print(f"ERROR: --db must be 'dev' or 'prod', got {db!r}.", style="error")
        raise typer.Exit(1)

    out_path = scenarios_path_for(hid)
    if out_path.exists():
        _console.print(
            f"ERROR: Scenarios file already exists:\n  {out_path}\n"
            "Rename or delete it before recreating.",
            style="error",
        )
        raise typer.Exit(1)

    try:
        character = load_character(hid, db)
    except (ValueError, FileNotFoundError) as exc:
        _console.print(f"ERROR: {exc}", style="error")
        raise typer.Exit(1)

    with _console.status(f"Building scenario scaffold for {hid!r}...", spinner="dots"):
        scaffold = build_scaffold(character, game)

    save_scaffold(scaffold, out_path)
    _console.print(f"[green]✔[/green] Scaffold written to: {out_path}", style="dim")
    summary = compute_status_summary(out_path)
    _console.print("\n" + render_status_summary(summary), style="dim")


# ---------------------------------------------------------------------------
# dcs-utils hitl update
# ---------------------------------------------------------------------------


@hitl_app.command("update")
def _hitl_update_cmd(
    hid: str = typer.Argument(..., help="Character HID whose scenarios file to update."),
    only_history: bool = typer.Option(
        False,
        "--only-history",
        help="Only sync shared conversation history, then report remaining work.",
    ),
    skip_simulator_responses: bool = typer.Option(
        False,
        "--skip-simulator-responses",
        help="Skip generating simulator responses for attempts after history sync.",
    ),
    skip_player_feedback: bool = typer.Option(
        False,
        "--skip-player-feedback",
        help="Skip collecting evaluator feedback after history sync.",
    ),
    regenerate_parent_session: bool = typer.Option(
        False,
        "--regenerate-parent-session",
        help="Rebuild a missing parent session from the saved shared history.",
    ),
    # simulator response + history options
    server_url: str = typer.Option(
        "http://localhost:8000",
        "--server-url",
        envvar="DCS_SERVER_URL",
        help="(history/simulator) DCS server URL.",
    ),
    api_key: str = typer.Option(
        "",
        "--api-key",
        envvar="DCS_API_KEY",
        help="(history/simulator) DCS API key.",
    ),
    concurrency: int = typer.Option(
        4,
        "--concurrency",
        help="(simulator) Maximum number of parallel scenario requests.",
    ),
    # feedback options
    evaluator_id: str = typer.Option(
        "",
        "--evaluator-id",
        help="(feedback) Your evaluator ID — recorded in each feedback entry.",
    ),
    # shared scenario-filter options
    scenario_only: Optional[List[str]] = typer.Option(
        None,
        "--scenario",
        help="Limit to these scenario IDs. Repeatable.",
    ),
    scenario_exclude: Optional[List[str]] = typer.Option(
        None,
        "--exclude",
        help="Skip these scenario IDs. Repeatable.",
    ),
) -> None:
    """Update a character's scenarios with shared history, simulator responses, and/or feedback.

    Shared conversation history is always synchronized first. By default the
    command then fills missing simulator responses for attempts and collects any
    missing evaluator feedback before printing a final status summary.

    \b
    Examples:
      dcs-utils hitl update AC                                # history + responses + feedback
      dcs-utils hitl update AC --only-history                 # history only
      dcs-utils hitl update AC --skip-player-feedback         # history + responses
      dcs-utils hitl update AC --skip-simulator-responses     # history + feedback
    """
    import asyncio

    from dcs_simulation_engine.api.client import APIClient
    from dcs_utils.hitl.feedback import collect_feedback
    from dcs_utils.hitl.generate import scenarios_path_for
    from dcs_utils.hitl.responses import compute_status_summary, generate_responses, render_status_summary

    if only_history and (skip_simulator_responses or skip_player_feedback):
        _console.print(
            "ERROR: --only-history cannot be combined with --skip-simulator-responses or --skip-player-feedback.",
            style="error",
        )
        raise typer.Exit(1)

    scenarios_path = scenarios_path_for(hid)
    if not scenarios_path.is_file():
        _console.print(
            f"ERROR: scenarios file not found: {scenarios_path}\n"
            f"Run `dcs-utils hitl create {hid} --db <dev|prod>` first.",
            style="error",
        )
        raise typer.Exit(1)

    scenario_ids = list(scenario_only) if scenario_only else None
    exclude_ids = list(scenario_exclude) if scenario_exclude else None

    try:
        with APIClient(url=server_url, api_key=api_key) as client:
            client.health()
    except Exception as exc:  # noqa: BLE001
        _console.print(
            "ERROR: Could not connect to the DCS server.\n"
            f"Tried: {server_url}\n"
            "The DCS server needs to be running to use `dcs-utils hitl update`.\n"
            f"Details: {exc}",
            style="error",
        )
        raise typer.Exit(1)

    asyncio.run(
        generate_responses(
            path=scenarios_path,
            server_url=server_url,
            api_key=api_key,
            only=scenario_ids,
            include_ids=None,
            exclude=exclude_ids,
            concurrency=concurrency,
            run_attempts=not (only_history or skip_simulator_responses),
            regenerate_parent_session=regenerate_parent_session,
            console=_console,
        )
    )

    if not only_history and not skip_player_feedback:
        collect_feedback(
            scenarios_path,
            evaluator_id=evaluator_id,
            only=scenario_ids,
            include_ids=None,
            exclude=exclude_ids,
            console=_console,
        )

    summary = compute_status_summary(
        scenarios_path,
        only=scenario_ids,
        include_ids=None,
        exclude=exclude_ids,
    )
    _console.print("\n" + render_status_summary(summary), style="dim")


# ---------------------------------------------------------------------------
# dcs-utils hitl export
# ---------------------------------------------------------------------------


@hitl_app.command("export")
def _hitl_export_cmd(
    hid: str = typer.Argument(..., help="Character HID whose scenarios file to export."),
    evaluator_id: str = typer.Option(
        "evaluator",
        "--evaluator-id",
        help="Evaluator ID recorded as the synthetic player in the results.",
    ),
    output_dir: Optional[Path] = typer.Option(
        None,
        "--output-dir",
        help="Override output directory (default: results/hitl_<hid>/ in the repo root).",
    ),
) -> None:
    """Export a completed scenarios file to a standard results directory.

    The output is compatible with `dcs-utils report results`:

    \b
        dcs-utils hitl export AC
        dcs-utils report results results/hitl_AC/ --only sim-quality
    """
    from dcs_utils.hitl.export import export_results
    from dcs_utils.hitl.generate import scenarios_path_for
    from dcs_utils.hitl.responses import compute_status_summary, render_status_summary

    scenarios_path = scenarios_path_for(hid)
    if not scenarios_path.is_file():
        _console.print(
            f"ERROR: scenarios file not found: {scenarios_path}\n"
            f"Run `dcs-utils hitl create {hid} --db <dev|prod>` first.",
            style="error",
        )
        raise typer.Exit(1)

    if output_dir is None:
        repo_root = _find_repo_root()
        output_dir = repo_root / "results" / f"hitl_{hid}"

    with _console.status(f"Exporting {hid} scenarios to results directory...", spinner="dots"):
        out = export_results(
            scenarios_path,
            evaluator_id=evaluator_id,
            output_dir=output_dir.resolve(),
        )

    summary = compute_status_summary(scenarios_path)
    _console.print("\n" + render_status_summary(summary), style="dim")
    if any(
        summary[key] > 0
        for key in (
            "attempts_without_simulator_responses",
            "attempts_without_player_feedback",
            "empty_conversation_histories",
            "conversation_histories_missing_simulator_reply",
        )
    ):
        _console.print("Export is proceeding with the current scenario file state.", style="dim")
    _console.print(f"[green]✔[/green] Results written to: {out}", style="dim")
    _console.print(
        f"\nGenerate a report:\n"
        f"  dcs-utils report results {out} --only sim-quality --title \"Simulation Quality — {hid}\"",
        style="dim",
    )


def main() -> None:
    """Entrypoint for the dcs-utils CLI."""
    app()


if __name__ == "__main__":
    main()
