"""Remote Fly deployment and lifecycle commands."""

import json
from pathlib import Path
from typing import Optional

import typer
from dcs_simulation_engine.cli.common import echo, step
from dcs_simulation_engine.infra.remote import (
    RemoteDeploymentResult,
    RemoteStatusResult,
    deploy_remote_experiment,
    fetch_remote_status,
    save_remote_database,
    stop_remote_experiment,
)

remote_app = typer.Typer(help="Remote Fly experiment deployment and lifecycle commands.")

_REGION_CAPACITY_ERROR_SNIPPETS = (
    "insufficient resources available to fulfill request",
    "could not reserve resource for machine",
    "insufficient memory available to fulfill request",
)


def _print_json(payload: RemoteDeploymentResult | RemoteStatusResult | dict) -> None:
    """Write one JSON payload to stdout."""
    data = payload if isinstance(payload, dict) else payload.model_dump()
    typer.echo(json.dumps(data, indent=2, sort_keys=True))


def _parse_region_candidates(ctx: typer.Context, region: str | None) -> list[str | None]:
    """Return the ordered region candidates selected on the CLI."""
    trailing_tokens = list(ctx.args)
    if not trailing_tokens:
        return [region]

    if region is None:
        raise ValueError(f"Unexpected extra arguments: {' '.join(trailing_tokens)}")
    if any(token.startswith("-") for token in trailing_tokens):
        raise ValueError("Pass plain Fly region ids after --regions, for example: --regions lax sjc dfw")

    ordered_regions: list[str] = []
    for candidate in [region, *trailing_tokens]:
        if candidate not in ordered_regions:
            ordered_regions.append(candidate)
    return ordered_regions


def _is_region_capacity_error(exc: Exception) -> bool:
    """Return whether a deploy failure looks like a retryable Fly capacity error."""
    message = str(exc).lower()
    return any(snippet in message for snippet in _REGION_CAPACITY_ERROR_SNIPPETS)


def _deploy_with_region_fallback(
    *,
    ctx: typer.Context,
    config: Path | None,
    openrouter_key: str,
    mongo_seed_path: Path,
    admin_key: str | None,
    fly_io_key: str | None,
    region_candidates: list[str | None],
    api_app: str | None,
    ui_app: str | None,
    db_app: str | None,
    only_app: list[str] | None,
    announce_attempts: bool,
) -> RemoteDeploymentResult:
    """Try one or more regions in order until deploy succeeds or a non-retryable error occurs."""
    for index, region in enumerate(region_candidates):
        if announce_attempts and region is not None:
            echo(ctx, f"Attempting Fly deploy in region: {region}", style="warning")
        try:
            return deploy_remote_experiment(
                config=config,
                openrouter_key=openrouter_key,
                mongo_seed_path=mongo_seed_path,
                admin_key=admin_key,
                fly_api_token=fly_io_key,
                region=region,
                api_app=api_app,
                ui_app=ui_app,
                db_app=db_app,
                deploy_apps=set(only_app or []),
            )
        except Exception as exc:
            if region is None or index >= len(region_candidates) - 1:
                raise
            if not _is_region_capacity_error(exc):
                raise
            echo(ctx, f"Region {region} is out of capacity. Attempting another region.", style="error")

    raise AssertionError("Expected at least one region deployment attempt.")


@remote_app.command("deploy", context_settings={"allow_extra_args": True})
def deploy(
    ctx: typer.Context,
    config: Path = typer.Option(
        Path("examples/run_configs/demo.yml"),
        "--config",
        exists=True,
        dir_okay=False,
        file_okay=True,
        readable=True,
        resolve_path=True,
        help="Run config YAML to deploy.",
    ),
    openrouter_key: str = typer.Option(
        ...,
        "--openrouter-key",
        envvar="OPENROUTER_API_KEY",
        help="OpenRouter API key forwarded to the remote API deployment.",
    ),
    fly_io_key: Optional[str] = typer.Option(
        None,
        "--fly-io-key",
        envvar="FLY_API_TOKEN",
        help="Fly API token used for deploy and destroy operations.",
    ),
    mongo_seed_path: Path = typer.Option(
        ...,
        "--mongo-seed-path",
        exists=True,
        dir_okay=True,
        file_okay=True,
        readable=True,
        resolve_path=True,
        help="Local seed source for Mongo bootstrap: a .zip/.tar.gz archive, a .json/.ndjson dump, or a directory.",
    ),
    admin_key: Optional[str] = typer.Option(
        None,
        "--admin-key",
        envvar="DCS_ADMIN_KEY",
        help="Optional explicit remote admin key to install during bootstrap. Must match the dcs-ak- key format.",
    ),
    region: Optional[str] = typer.Option(
        None,
        "--regions",
        "--region",
        help=("Fly region(s) to try in order. Example: --regions lax sjc dfw"),
    ),
    only_app: Optional[list[str]] = typer.Option(
        None,
        "--only-app",
        help="Redeploy only the selected app(s): api, ui, or db. Repeat the flag to deploy multiple apps.",
    ),
    api_app: Optional[str] = typer.Option(None, "--api-app", help="Optional explicit Fly app name for the API."),
    ui_app: Optional[str] = typer.Option(None, "--ui-app", help="Optional explicit Fly app name for the UI."),
    db_app: Optional[str] = typer.Option(None, "--db-app", help="Optional explicit Fly app name for MongoDB."),
    json_output: bool = typer.Option(False, "--json", help="Print the deployment result as JSON."),
) -> None:
    """Deploy one remote-managed stack to Fly as API, UI, and Mongo apps."""
    try:
        region_candidates = _parse_region_candidates(ctx, region)
        if json_output:
            result = _deploy_with_region_fallback(
                ctx=ctx,
                config=config,
                openrouter_key=openrouter_key,
                mongo_seed_path=mongo_seed_path,
                admin_key=admin_key,
                fly_io_key=fly_io_key,
                region_candidates=region_candidates,
                api_app=api_app,
                ui_app=ui_app,
                db_app=db_app,
                only_app=only_app,
                announce_attempts=False,
            )
        else:
            with step("Deploying remote experiment to Fly"):
                result = _deploy_with_region_fallback(
                    ctx=ctx,
                    config=config,
                    openrouter_key=openrouter_key,
                    mongo_seed_path=mongo_seed_path,
                    admin_key=admin_key,
                    fly_io_key=fly_io_key,
                    region_candidates=region_candidates,
                    api_app=api_app,
                    ui_app=ui_app,
                    db_app=db_app,
                    only_app=only_app,
                    announce_attempts=True,
                )
    except Exception as exc:
        echo(ctx, f"Remote deploy failed: {exc}", style="error")
        raise typer.Exit(code=1) from exc

    if json_output:
        _print_json(result)
        return

    echo(ctx, f"Deployment ready: {result.experiment_name}", style="success")
    echo(ctx, f"Deployed apps: {', '.join(result.deployed_apps)}")
    echo(ctx, f"API: {result.api_url}")
    echo(ctx, f"UI: {result.ui_url}")
    echo(ctx, f"Open the UI in your browser: {result.ui_url}")
    echo(ctx, f"Apps: api={result.api_app} ui={result.ui_app} db={result.db_app}")
    if result.admin_api_key:
        echo(ctx, f"Admin access key: {result.admin_api_key}", style="error")
        echo(ctx, "Save this admin key now. It will only be shown once.", style="error")
    else:
        echo(ctx, "Admin access key unchanged: targeted app deploys do not re-bootstrap the deployment.")
    echo(ctx, "Next commands:")
    echo(ctx, f"  {result.status_command}")
    if result.save_command:
        echo(ctx, f"  {result.save_command}")
    if result.stop_command:
        echo(ctx, f"  {result.stop_command}")


@remote_app.command("status")
def status(
    ctx: typer.Context,
    uri: str = typer.Option(..., "--uri", help="Remote API base URL."),
    admin_key: str = typer.Option(..., "--admin-key", envvar="DCS_ADMIN_KEY", help="Saved remote admin access key."),
    json_output: bool = typer.Option(False, "--json", help="Print the status result as JSON."),
) -> None:
    """Return the authenticated status payload for one remote deployment."""
    try:
        result = fetch_remote_status(
            uri=uri,
            admin_key=admin_key,
        )
    except Exception as exc:
        echo(ctx, f"Remote status failed: {exc}", style="error")
        raise typer.Exit(code=1) from exc

    if json_output:
        _print_json(result.experiment_status or {})
        return

    typer.echo(json.dumps(result.experiment_status or {}, indent=2, sort_keys=True))


@remote_app.command("save")
def save(
    ctx: typer.Context,
    uri: str = typer.Option(..., "--uri", help="Remote API base URL."),
    admin_key: str = typer.Option(..., "--admin-key", envvar="DCS_ADMIN_KEY", help="Admin access key returned by remote deploy."),
    save_db_path: Path = typer.Option(
        ...,
        "--save-db-path",
        dir_okay=False,
        file_okay=True,
        writable=True,
        resolve_path=True,
        help="Local path for the downloaded database export archive (.tar.gz or .zip).",
    ),
) -> None:
    """Download the remote database export archive to a local file."""
    try:
        with step("Downloading remote database export"):
            result_path = save_remote_database(uri=uri, admin_key=admin_key, save_db_path=save_db_path)
    except Exception as exc:
        echo(ctx, f"Remote save failed: {exc}", style="error")
        raise typer.Exit(code=1) from exc

    typer.echo(f"Database export written to: {result_path}")


@remote_app.command("stop")
def stop(
    ctx: typer.Context,
    uri: str = typer.Option(..., "--uri", help="Remote API base URL."),
    admin_key: str = typer.Option(..., "--admin-key", envvar="DCS_ADMIN_KEY", help="Admin access key returned by remote deploy."),
    save_db_path: Path = typer.Option(
        ...,
        "--save-db-path",
        dir_okay=False,
        file_okay=True,
        writable=True,
        resolve_path=True,
        help="Local path for the downloaded database export archive (.tar.gz or .zip).",
    ),
    api_app: str = typer.Option(..., "--api-app", help="Fly API app name."),
    ui_app: str = typer.Option(..., "--ui-app", help="Fly UI app name."),
    db_app: str = typer.Option(..., "--db-app", help="Fly Mongo app name."),
    fly_io_key: Optional[str] = typer.Option(
        None,
        "--fly-io-key",
        envvar="FLY_API_TOKEN",
        help="Fly API token used to destroy the remote apps.",
    ),
) -> None:
    """Save the remote DB archive, then destroy all Fly apps for the experiment."""
    try:
        with step("Saving remote database and destroying Fly apps"):
            result_path = stop_remote_experiment(
                uri=uri,
                admin_key=admin_key,
                save_db_path=save_db_path,
                api_app=api_app,
                ui_app=ui_app,
                db_app=db_app,
                fly_api_token=fly_io_key,
            )
    except Exception as exc:
        echo(ctx, f"Remote stop failed: {exc}", style="error")
        raise typer.Exit(code=1) from exc

    typer.echo(f"Database export written to: {result_path}")
    echo(ctx, "Remote deployment destroyed.", style="success")
