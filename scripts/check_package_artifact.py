"""Verify that a built wheel contains packaged local engine assets."""

import sys
import zipfile
from pathlib import Path

REQUIRED_WHEEL_FILES = [
    "dcs_simulation_engine/package_assets/compose.yml",
    "dcs_simulation_engine/package_assets/docker/Caddyfile",
    "dcs_simulation_engine/package_assets/docker/api.dockerfile",
    "dcs_simulation_engine/package_assets/docker/db.dockerfile",
    "dcs_simulation_engine/package_assets/docker/ui.dockerfile",
    "dcs_simulation_engine/package_assets/examples/run_configs/demo.yml",
    "dcs_simulation_engine/package_assets/database_seeds/dev/characters.json",
    "dcs_simulation_engine/package_assets/ui_dist/index.html",
]


def package_asset_errors(wheel_path: Path) -> list[str]:
    """Return missing or malformed package asset errors for a wheel."""
    if not wheel_path.is_file():
        return [f"Wheel not found: {wheel_path}"]
    if wheel_path.suffix != ".whl":
        return [f"Expected a .whl artifact, got: {wheel_path}"]

    with zipfile.ZipFile(wheel_path) as wheel:
        names = set(wheel.namelist())

    errors = [f"Missing packaged asset: {name}" for name in REQUIRED_WHEEL_FILES if name not in names]
    ui_asset_prefix = "dcs_simulation_engine/package_assets/ui_dist/assets/"
    if not any(name.startswith(ui_asset_prefix) and name.endswith(".js") for name in names):
        errors.append("Missing packaged UI JavaScript asset under package_assets/ui_dist/assets/")
    if not any(name.startswith(ui_asset_prefix) and name.endswith(".css") for name in names):
        errors.append("Missing packaged UI CSS asset under package_assets/ui_dist/assets/")
    return errors


def main(argv: list[str] | None = None) -> int:
    """Check that a built wheel artifact includes required package assets."""
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 1:
        print("Usage: python scripts/check_package_artifact.py dist/package.whl", file=sys.stderr)
        return 2

    errors = package_asset_errors(Path(args[0]))
    if errors:
        print("Package artifact is missing required assets:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print(f"Package artifact includes required local engine assets: {args[0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
