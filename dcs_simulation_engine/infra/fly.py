"""Fly.io management."""

import json
import os
import shutil
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import dotenv_values, load_dotenv
from loguru import logger


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


def _toml_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return f'"{_toml_escape(value)}"'
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    if value is None:
        raise ValueError("TOML does not support null values.")
    if hasattr(value, "isoformat"):
        return value.isoformat()
    raise TypeError(f"Unsupported TOML value type: {type(value)!r}")


def _write_table(lines: list[str], key_path: list[str], table: dict[str, Any]) -> None:
    scalar_items: list[tuple[str, Any]] = []
    table_items: list[tuple[str, dict[str, Any]]] = []
    array_table_items: list[tuple[str, list[dict[str, Any]]]] = []

    for key, value in table.items():
        if isinstance(value, dict):
            table_items.append((key, value))
        elif isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
            array_table_items.append((key, value))
        else:
            scalar_items.append((key, value))

    if key_path:
        lines.append(f"[{'.'.join(key_path)}]")
    for key, value in scalar_items:
        lines.append(f"{key} = {_toml_value(value)}")
    if key_path:
        lines.append("")

    for key, value in table_items:
        _write_table(lines, [*key_path, key], value)

    for key, value in array_table_items:
        full_key = ".".join([*key_path, key])
        for idx, item in enumerate(value):
            lines.append(f"[[{full_key}]]")
            for item_key, item_value in item.items():
                if isinstance(item_value, dict):
                    raise TypeError(f"Nested table inside array-of-tables is unsupported ({full_key}.{item_key}).")
                lines.append(f"{item_key} = {_toml_value(item_value)}")
            if idx != len(value) - 1:
                lines.append("")
        lines.append("")


def update_fly_toml(*, original_toml: str, app_name: str, process_cmd: str, region: Optional[str] = None) -> str:
    """Update app/process settings in fly.toml using TOML parsing and serialization."""
    data = tomllib.loads(original_toml)
    if not isinstance(data, dict):
        raise RuntimeError("fly.toml root must be a table.")

    data["app"] = app_name
    if region is not None:
        data["primary_region"] = region

    processes = data.get("processes")
    if processes is None:
        data["processes"] = {"web": process_cmd}
    elif isinstance(processes, dict):
        processes["web"] = process_cmd
    else:
        raise RuntimeError("[processes] must be a table in fly.toml.")

    lines: list[str] = []
    _write_table(lines, [], data)
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines) + "\n"


def destroy_app(app_name: str) -> None:
    """Destroy a Fly app."""
    try:
        subprocess.run(["fly", "apps", "destroy", app_name, "--yes"], check=True)
    except subprocess.CalledProcessError as e:
        raise FlyError(f"fly apps destroy failed (exit {e.returncode})") from e


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


def ensure_fly_auth() -> None:
    """Verify flyctl is authenticated (i.e. `fly auth whoami` works and returns an email)."""
    try:
        res = subprocess.run(
            ["fly", "auth", "whoami", "--json"],
            check=True,
            capture_output=True,
            text=True,
        )
        data = json.loads(res.stdout or "{}")
        email = data.get("email") or data.get("Email") or data.get("user") or data.get("User")
        if not email:
            raise RuntimeError("not logged in")
    except FileNotFoundError:
        raise FlyError("flyctl not found. Please install flyctl and ensure it's on your PATH.")
    except Exception as e:
        raise FlyError(
            "Failed to verify Fly authentication. Please ensure you're logged in via `fly auth login`."
        ) from e


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


def build_deploy_cmd(config_path: Path, app_name: str, dotenv_vars: Dict[str, str]) -> list[str]:
    """Build the flyctl deploy command, injecting env vars from .env."""
    cmd: list[str] = [
        "fly",
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
            "uv",
            "run",
            "dcs",
            "run",
        ]
        if tag:
            cmd_parts.extend(["--banner", tag])
        _ = version
        return " ".join(cmd_parts)

    cmd_parts = [
        "uv",
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
        updated = update_fly_toml(
            original_toml=original,
            app_name=app_name,
            process_cmd=process_cmd,
            region=region,
        )
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

    return DeployResult(app_name=app_name, process_cmd=process_cmd, forwarded_env_keys=forwarded_keys)


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
        subprocess.run(["flyctl", "machine", "stop", *machine_ids, "--app", app_name], check=True)
    except subprocess.CalledProcessError as e:
        raise FlyError(f"flyctl machine stop failed (exit {e.returncode})") from e

    return machine_ids


def download_db(*, app_name: str, remote_path: str, local_path: Path) -> None:
    """Download a file from the Fly app via SFTP."""
    ensure_fly_available()
    local_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        sftp_get(app_name=app_name, remote_path=remote_path, local_path=local_path)
    except Exception as e:
        raise FlyError(f"Failed to download DB: {e}") from e


def download_logs_jsonl(*, app_name: str, out_path: Path, no_tail: bool = True) -> None:
    """Download Fly logs in JSONL format and write to out_path."""
    ensure_fly_available()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = ["fly", "logs", "--app", app_name, "--json"]
    if no_tail:
        cmd.append("--no-tail")

    try:
        proc = subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        err = (e.stderr or "").strip() or (e.stdout or "").strip() or str(e)
        raise FlyError(f"Failed to download logs: {err}") from e

    # fly logs --json outputs newline-delimited JSON objects (JSONL)
    out_path.write_text(proc.stdout, encoding="utf-8")


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
