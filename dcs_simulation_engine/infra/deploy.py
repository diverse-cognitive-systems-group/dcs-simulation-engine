"""Deployment management."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from dcs_simulation_engine.infra import fly as provider


def list_deployments() -> list[dict]:
    """List deployments."""
    # this might raise FlyError
    return provider.list_apps()


def deploy_app(
    *,
    game: str,
    deployment: str,
    version: str = "latest",
    fly_toml: Path = Path("fly.toml"),
    env_file: Optional[Path] = Path(".env"),
    region: Optional[str] = None,
) -> provider.DeployResult:
    """Deploy a game."""
    return provider.deploy_app(
        game=game,
        app_name=deployment,
        version=version,
        fly_toml=fly_toml,
        env_file=env_file,
        region=region,
    )


def destroy_deployment(app_name: str) -> None:
    """Destroy a deployment."""
    provider.destroy_app(app_name)


def stop_deployment(
    *,
    deployment: str,
    logs_out: Optional[Path] = None,
    logs_no_tail: bool = True,
    db_remote: Optional[str] = None,
    db_out: Optional[Path] = None,
) -> list[str]:
    """Stop a deployment and optionally download logs + DB."""
    # best-effort logs
    if logs_out:
        logs = provider.download_logs_jsonl(
            app_name=deployment, no_tail=logs_no_tail, out_path=logs_out
        )
        logs_out.parent.mkdir(parents=True, exist_ok=True)
        logs_out.write_text(logs)

    # best-effort db
    if db_remote:
        if db_out is None:
            db_out = Path(f"{deployment}-db.sqlite3")
        provider.sftp_get(app_name=deployment, remote_path=db_remote, local_path=db_out)

    # stop machines
    return provider.stop_all_machines(deployment)
