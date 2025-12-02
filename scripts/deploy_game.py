"""Game deployment script for easy Fly.io deployments.

Usage:
    python deploy_game.py --interface widget --game Explore --version latest --tag exp382
    python deploy_game.py --interface api --version v0.3.0 --tag demo
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict

from dotenv import dotenv_values, load_dotenv

BASE_APP_NAME = "dcs-simulation-demo"

logger = logging.getLogger(__name__)

# All key/values loaded from .env (used to forward into flyctl --env)
DOTENV_VARS: Dict[str, str] = {}


def check_flyctl() -> None:
    """Verify that `flyctl` is installed and accessible on PATH.

    Exits the process with an error message if not available.
    """
    if shutil.which("flyctl") is None:
        logger.error("flyctl not installed or not on PATH.")
        sys.exit(1)


def load_env(env_file: Path = Path(".env")) -> None:
    """Load environment variables.

    Uses python-dotenv to merge .env into os.environ and also records
    all key/value pairs from the .env file for later forwarding to Fly.
    """
    global DOTENV_VARS

    if not env_file.exists():
        logger.warning("%s not found — skipping env file load.", env_file)
        DOTENV_VARS = {}
    else:
        # Capture raw .env contents so we know exactly what to forward
        raw = dotenv_values(env_file)
        DOTENV_VARS = {k: v for k, v in raw.items() if v is not None}

        # Also merge into process env (so local code using os.environ works)
        load_dotenv(env_file, override=True)

    # # Force non-interactive flyctl mode (optional)
    # os.environ.setdefault("FLY_NO_INTERACTIVE", "1")

    if not os.environ.get("FLY_API_TOKEN"):
        logger.error("FLY_API_TOKEN missing in environment.")
        sys.exit(1)


def load_toml(path: Path) -> str:
    """Load and return the text contents of the given fly.toml file."""
    if not path.exists():
        logger.error("%s not found.", path)
        sys.exit(1)
    return path.read_text()


def update_process_cmd(toml: str, cmd: str) -> str:
    """Update the process command in the fly.toml contents.

    Replace the `web = '...'` line in the [processes] table
    with the provided command string.
    """
    pattern = r"(web\s*=\s*)'[^']*'"
    replacement = rf"\1'{cmd}'"

    new_toml, n = re.subn(pattern, replacement, toml)
    if n == 0:
        logger.error("Could not find `web = '...'` in fly.toml.")
        sys.exit(1)

    return new_toml


def extract_region_from_toml(toml: str) -> str | None:
    """Extract primary_region from fly.toml if present."""
    match = re.search(r"^primary_region\s*=\s*'([^']+)'", toml, flags=re.MULTILINE)
    if match:
        return match.group(1)
    return None


def update_app_and_region(
    toml: str,
    app_name: str,
    region: str | None = None,
) -> str:
    """Update app name and (optionally) primary_region in fly.toml contents."""
    # Update app name
    app_pattern = r"^(app\s*=\s*)'[^']*'"
    app_replacement = rf"\1'{app_name}'"
    new_toml, n_app = re.subn(app_pattern, app_replacement, toml, flags=re.MULTILINE)
    if n_app == 0:
        logger.error("Could not find `app = '...'` in fly.toml.")
        sys.exit(1)

    if region is None:
        return new_toml

    # Update or insert primary_region
    region_pattern = r"^(primary_region\s*=\s*)'[^']*'"
    region_replacement = rf"\1'{region}'"
    new_toml2, n_region = re.subn(
        region_pattern, region_replacement, new_toml, flags=re.MULTILINE
    )
    if n_region > 0:
        return new_toml2

    # If no primary_region present, add it directly after app line
    lines = new_toml.splitlines()
    for idx, line in enumerate(lines):
        if line.strip().startswith("app "):
            lines.insert(idx + 1, f"primary_region = '{region}'")
            break
    else:
        # Fallback: prepend if we somehow didn't find app line again
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

    # Skip header line
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


def build_deploy_cmd(
    config_path: Path,
    app_name: str,
    dotenv_vars: Dict[str, str],
) -> list[str]:
    """Build the flyctl deploy command, injecting env vars from .env."""
    cmd: list[str] = [
        "flyctl",
        "deploy",
        "--config",
        str(config_path),
        "--app",
        app_name,
        "--ha=false",  # deploy using single instance/machine
    ]

    # Forward all .env vars except FLY_API_TOKEN (used only for flyctl auth)
    for key, value in dotenv_vars.items():
        if key == "FLY_API_TOKEN":
            continue
        cmd.extend(["--env", f"{key}={value}"])

    return cmd


def validate_tag(tag: str) -> str:
    """Validate the tag string for use in app name and banner."""
    if len(tag) > 20:
        logger.error("--tag must be at most 10 characters.")
        sys.exit(1)
    if not re.fullmatch(r"[A-Za-z0-9-]+", tag):
        logger.error("--tag must contain only letters, numbers, and dashes.")
        sys.exit(1)
    return tag


def main() -> None:
    """Entry point: parse arguments, update fly.toml, and deploy."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(description="Deploy to Fly.io")
    parser.add_argument("--interface", choices=["widget", "api"], required=True)
    parser.add_argument("--game", help="Required when --interface widget")
    parser.add_argument("--version", default="latest")
    parser.add_argument("--fly-toml", default="fly.toml")
    parser.add_argument(
        "--tag",
        help=(
            "Short tag used to distinguish app instances. "
            "App name becomes 'dcs-simulation-<tag>' and widget gets --banner=<tag>. "
            "Must contain only letters, numbers, and dashes."
        ),
    )
    parser.add_argument(
        "--with-db",
        action="store_true",
        help="Deploy with a new DB (currently unimplemented; will exit with an error).",
    )

    args = parser.parse_args()

    if args.with_db:
        logger.error("--with-db is not implemented yet.")
        sys.exit(1)

    load_env()
    check_flyctl()

    if args.interface == "widget" and not args.game:
        logger.error("--game required for --interface widget.")
        sys.exit(1)

    tag: str | None = None
    if args.tag:
        tag = validate_tag(args.tag)

    # Compute app name
    if tag:
        app_name = f"dcs-simulation-{tag}"
    else:
        app_name = BASE_APP_NAME

    # Construct process command (what goes into fly.toml)
    if args.interface == "widget":
        cmd_parts: list[str] = [
            "poetry",
            "run",
            "python",
            "-m",
            "scripts.run_widget",
            "--game",
            str(args.game),
            # "--version",
            # str(args.version),
            "--port",
            "8080",
            "--host",
            "0.0.0.0",
        ]
        if tag:
            cmd_parts.extend(["--banner", tag])
        else:
            logger.warning("Tag is not provided; default banner will be used.")
    else:
        cmd_parts = [
            "poetry",
            "run",
            "python",
            "-m",
            "scripts.run_api",
            # "--version",
            # str(args.version),
            "--port",
            "8080",
            "--host",
            "0.0.0.0",
        ]

    cmd = " ".join(cmd_parts)

    config_path = Path(args.fly_toml)
    original = load_toml(config_path)

    # Update app name + region + process command in toml
    updated = update_app_and_region(original, app_name=app_name)
    updated = update_process_cmd(updated, cmd)
    config_path.write_text(updated)

    logger.info("Updated process command: %s", cmd)
    ensure_app_exists(app_name)

    # Build deploy command with envs from .env
    visible_env_keys = [k for k in DOTENV_VARS.keys() if k != "FLY_API_TOKEN"]
    logger.info(
        "Forwarding .env keys to Fly (excluding FLY_API_TOKEN): %s",
        ", ".join(visible_env_keys) or "(none)",
    )
    deploy_cmd = build_deploy_cmd(config_path, app_name, DOTENV_VARS)

    logger.info("Deploying with: %s", " ".join(deploy_cmd))
    subprocess.run(deploy_cmd, check=True)


if __name__ == "__main__":
    main()
