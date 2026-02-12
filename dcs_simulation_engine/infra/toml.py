"""Fly parsing.

TODO: this uses brittle toml parsing to launch fly
A better solution is to refactor/update to use a proper toml library
OR even better, launch fly from docker with env vars and no fly.toml at all.

"""

import re
from typing import Optional


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
