"""Fly.io management."""

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import dotenv_values, load_dotenv
from loguru import logger

from dcs_simulation_engine.infra.toml import (
    update_app_and_region,
    update_process_cmd,
)


class FlyError(RuntimeError):
    """Raised for Fly-related operational failures."""


@dataclass(frozen=True)
class DeployResult:
    """Result of a deployment."""

    app_name: str
    process_cmd: str
    forwarded_env_keys: list[str]


@dataclass(frozen=True)
class LoadedEnv:
    """Merged env + captured dotenv key/values (for forwarding to flyctl --env)."""

    dotenv_vars: Dict[str, str]


def flyctl_json(args: List[str]) -> object:
    """Run flyctl with --json and return parsed JSON."""
    proc = subprocess.run(
        ["flyctl", *args, "--json"],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(proc.stdout)


def check_flyctl() -> None:
    """Verify that `flyctl` is installed and accessible on PATH."""
    if shutil.which("flyctl") is None:
        raise RuntimeError("flyctl not installed or not on PATH.")


def ensure_fly_available() -> None:
    """Verify flyctl is installed and usable."""
    try:
        check_flyctl()
    except Exception as e:
        raise FlyError(str(e)) from e


def load_env(env_file: Optional[Path] = Path(".env")) -> LoadedEnv:
    """Load env vars from .env and ensure FLY_API_TOKEN exists in environment."""
    if env_file is None or not env_file.exists():
        if env_file is not None:
            logger.warning("%s not found — skipping env file load.", env_file)
        dotenv_vars: Dict[str, str] = {}
    else:
        raw = dotenv_values(env_file)
        dotenv_vars = {k: v for k, v in raw.items() if v is not None}
        load_dotenv(env_file, override=True)

    if not os.environ.get("FLY_API_TOKEN"):
        raise RuntimeError("FLY_API_TOKEN missing in environment.")

    return LoadedEnv(dotenv_vars=dotenv_vars)


def build_deploy_cmd(
    config_path: Path, app_name: str, dotenv_vars: Dict[str, str]
) -> list[str]:
    """Build the flyctl deploy command, injecting env vars from .env."""
    cmd: list[str] = [
        "flyctl",
        "deploy",
        "--config",
        str(config_path),
        "--app",
        app_name,
        "--ha=false",
    ]
    for key, value in dotenv_vars.items():
        if key == "FLY_API_TOKEN":
            continue
        cmd.extend(["--env", f"{key}={value}"])
    return cmd


def ensure_app_exists(app_name: str) -> None:
    """Ensure the Fly app exists. If not, create it."""
    result = subprocess.run(["flyctl", "apps", "list"], capture_output=True, text=True)
    if result.returncode != 0:
        logger.warning(
            "Failed to list apps (exit %s), proceeding to deploy anyway.",
            result.returncode,
        )
        return

    for line in result.stdout.splitlines()[1:]:
        if not line.strip():
            continue
        name = line.split()[0]
        if name == app_name:
            logger.info("App %r already exists.", app_name)
            return

    cmd = ["flyctl", "apps", "create", app_name]
    logger.info("App %r not found. Creating via: %s", app_name, " ".join(cmd))
    subprocess.run(cmd, check=True)


def build_process_command(
    interface: str,
    *,
    game: Optional[str],
    version: str,
    tag: Optional[str],
) -> str:
    """Build the command string that becomes the Fly [processes].web command."""
    if interface not in {"widget", "api"}:
        raise ValueError("interface must be 'widget' or 'api'.")

    if interface == "widget":
        if not game:
            raise ValueError("--game is required for widget deployments.")

        cmd_parts: list[str] = [
            "poetry",
            "run",
            "dcs",
            "run",
            "game",
            str(game),
            "--port",
            "8080",
            "--host",
            "0.0.0.0",
        ]
        if tag:
            cmd_parts.extend(["--banner", tag])
        _ = version
        return " ".join(cmd_parts)

    cmd_parts = [
        "poetry",
        "run",
        "python",
        "-m",
        "scripts.run_api",
        "--port",
        "8080",
        "--host",
        "0.0.0.0",
    ]
    _ = version
    return " ".join(cmd_parts)


def deploy_app(
    *,
    game: str,
    app_name: str,
    version: str = "latest",
    fly_toml: Path = Path("fly.toml"),
    env_file: Optional[Path] = Path(".env"),
    region: Optional[str] = None,
) -> DeployResult:
    """Deploy the widget process for a game to Fly."""
    ensure_fly_available()

    try:
        loaded = load_env(env_file=env_file)
    except Exception as e:
        raise FlyError(f"Failed to load env file: {e}") from e

    process_cmd = build_process_command("widget", game=game, version=version, tag=None)

    try:
        original = fly_toml.read_text()
        updated = update_app_and_region(original, app_name=app_name, region=region)
        updated = update_process_cmd(updated, process_cmd)
        fly_toml.write_text(updated)
    except FileNotFoundError as e:
        raise FlyError(f"fly.toml not found at: {fly_toml}") from e
    except Exception as e:
        raise FlyError(f"Failed updating {fly_toml}: {e}") from e

    try:
        ensure_app_exists(app_name)
    except Exception as e:
        raise FlyError(f"Failed ensuring Fly app exists ({app_name}): {e}") from e

    dotenv_vars = loaded.dotenv_vars or {}
    forwarded_keys = [k for k in dotenv_vars.keys() if k != "FLY_API_TOKEN"]

    try:
        deploy_cmd = build_deploy_cmd(fly_toml, app_name, dotenv_vars)
        logger.info("Deploying with: %s", " ".join(deploy_cmd))
        subprocess.run(deploy_cmd, check=True)
    except subprocess.CalledProcessError as e:
        raise FlyError(f"flyctl deploy failed (exit {e.returncode})") from e

    return DeployResult(
        app_name=app_name, process_cmd=process_cmd, forwarded_env_keys=forwarded_keys
    )


def list_apps() -> list[dict[str, Any]]:
    """List Fly apps in the current account."""
    ensure_fly_available()
    try:
        apps = flyctl_json(["apps", "list"])
        return apps if isinstance(apps, list) else []
    except Exception as e:
        raise FlyError(f"Failed to list Fly apps: {e}") from e


def list_machines(app_name: str) -> list[dict[str, Any]]:
    """List machines for a Fly app."""
    ensure_fly_available()
    try:
        machines = flyctl_json(["machine", "list", "--app", app_name])
        return machines if isinstance(machines, list) else []
    except Exception as e:
        raise FlyError(f"Failed to list machines for {app_name}: {e}") from e


def stop_all_machines(app_name: str) -> list[str]:
    """Stop all machines for a Fly app."""
    machines = list_machines(app_name)
    machine_ids: list[str] = []
    for m in machines:
        mid = m.get("id") or m.get("ID") or m.get("Id")
        if mid:
            machine_ids.append(str(mid))

    if not machine_ids:
        return []

    try:
        subprocess.run(
            ["flyctl", "machine", "stop", *machine_ids, "--app", app_name], check=True
        )
    except subprocess.CalledProcessError as e:
        raise FlyError(f"flyctl machine stop failed (exit {e.returncode})") from e

    return machine_ids


def download_logs_json(*, app_name: str, no_tail: bool = True) -> str:
    """Download logs for a Fly app."""
    ensure_fly_available()
    cmd = ["flyctl", "logs", "--app", app_name]
    if no_tail:
        cmd.append("--no-tail")
    cmd.append("--json")
    try:
        proc = subprocess.run(cmd, check=True, capture_output=True, text=True)
        return proc.stdout
    except subprocess.CalledProcessError as e:
        err = (e.stderr or "").strip() or (e.stdout or "").strip() or str(e)
        raise FlyError(f"Failed to download logs: {err}") from e


def sftp_get(*, app_name: str, remote_path: str, local_path: Path) -> None:
    """Get a file from the Fly app via SFTP."""
    ensure_fly_available()
    try:
        subprocess.run(
            [
                "flyctl",
                "ssh",
                "sftp",
                "get",
                remote_path,
                str(local_path),
                "--app",
                app_name,
            ],
            check=True,
        )
    except subprocess.CalledProcessError as e:
        raise FlyError(f"flyctl sftp get failed (exit {e.returncode})") from e
