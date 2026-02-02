"""Helpers for deploying games/experiments using Fly.io."""

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, List
import json
from dotenv import dotenv_values, load_dotenv
from loguru import logger

DEFAULT_BASE_APP_NAME = "dcs-simulation-demo"


# TODO: when we know how we want to deploy, use more robust parsing (e.g., tomllib)
@dataclass(frozen=True)
class LoadedEnv:
    """Merged env + captured dotenv key/values (for forwarding to flyctl --env)."""

    dotenv_vars: Dict[str, str]

def flyctl_json(args: List[str]) -> object:
    """Run flyctl with --json and return parsed JSON.

    Raises subprocess.CalledProcessError / json.JSONDecodeError on failure.
    """
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


def load_env(env_file: Path = Path(".env")) -> LoadedEnv:
    """Load environment variables from .env and ensure FLY_API_TOKEN exists.

    Returns the parsed .env key/values (minus None values) so callers can
    forward them into `flyctl deploy --env KEY=VALUE`.
    """
    if not env_file.exists():
        logger.warning("%s not found — skipping env file load.", env_file)
        dotenv_vars: Dict[str, str] = {}
    else:
        raw = dotenv_values(env_file)
        dotenv_vars = {k: v for k, v in raw.items() if v is not None}
        load_dotenv(env_file, override=True)

    if not os.environ.get("FLY_API_TOKEN"):
        raise RuntimeError("FLY_API_TOKEN missing in environment.")

    return LoadedEnv(dotenv_vars=dotenv_vars)


def update_process_cmd(toml: str, cmd: str) -> str:
    """Replace the `web = '...'` line in the [processes] table."""
    pattern = r"(web\s*=\s*)'[^']*'"
    replacement = rf"\1'{cmd}'"
    new_toml, n = re.subn(pattern, replacement, toml)
    if n == 0:
        raise RuntimeError("Could not find `web = '...'` in fly.toml.")
    return new_toml


def extract_region_from_toml(toml: str) -> Optional[str]:
    """Extract primary_region from fly.toml contents, if present."""
    match = re.search(r"^primary_region\s*=\s*'([^']+)'", toml, flags=re.MULTILINE)
    return match.group(1) if match else None


def update_app_and_region(
    toml: str, app_name: str, region: Optional[str] = None
) -> str:
    """Update app name and (optionally) primary_region in fly.toml contents."""
    app_pattern = r"^(app\s*=\s*)'[^']*'"
    app_replacement = rf"\1'{app_name}'"
    new_toml, n_app = re.subn(app_pattern, app_replacement, toml, flags=re.MULTILINE)
    if n_app == 0:
        raise RuntimeError("Could not find `app = '...'` in fly.toml.")

    if region is None:
        return new_toml

    region_pattern = r"^(primary_region\s*=\s*)'[^']*'"
    region_replacement = rf"\1'{region}'"
    new_toml2, n_region = re.subn(
        region_pattern, region_replacement, new_toml, flags=re.MULTILINE
    )
    if n_region > 0:
        return new_toml2

    # Insert primary_region directly after app line
    lines = new_toml.splitlines()
    for idx, line in enumerate(lines):
        if line.strip().startswith("app "):
            lines.insert(idx + 1, f"primary_region = '{region}'")
            break
    else:
        lines.insert(0, f"primary_region = '{region}'")

    return "\n".join(lines) + "\n"


def ensure_app_exists(app_name: str) -> None:
    """Ensure the Fly app exists. If not, create it."""
    result = subprocess.run(
        ["flyctl", "apps", "list"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        logger.warning(
            "Failed to list apps (exit %s), proceeding to deploy anyway.",
            result.returncode,
        )
        return

    for line in result.stdout.splitlines()[1:]:  # skip header
        if not line.strip():
            continue
        name = line.split()[0]
        if name == app_name:
            logger.info("App %r already exists.", app_name)
            return

    cmd = ["flyctl", "apps", "create", app_name]
    logger.info("App %r not found. Creating via: %s", app_name, " ".join(cmd))
    subprocess.run(cmd, check=True)


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


def validate_tag(tag: str) -> str:
    """Validate the tag string for use in app name and banner."""
    if len(tag) > 20:
        raise ValueError("--tag must be at most 20 characters.")
    if not re.fullmatch(r"[A-Za-z0-9-]+", tag):
        raise ValueError("--tag must contain only letters, numbers, and dashes.")
    return tag


def compute_app_name(base_app_name: str, tag: Optional[str]) -> str:
    """Compute the full app name, incorporating the tag if provided."""
    return f"dcs-simulation-{tag}" if tag else base_app_name


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

        # Use your new Typer command instead of scripts.run_widget
        cmd_parts: list[str] = [
            "poetry",
            "run",
            "dcs",
            "run",
            "--game",
            str(game),
            "--port",
            "8080",
            "--host",
            "0.0.0.0",
        ]
        if tag:
            cmd_parts.extend(["--banner", tag])
        else:
            logger.warning("Tag is not provided; default banner will be used.")

        # version currently unused (kept for parity)
        _ = version
        return " ".join(cmd_parts)

    # api
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
