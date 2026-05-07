"""Verify that a built wheel contains packaged local engine assets."""

import re
import sys
import zipfile
from email.parser import Parser
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

REQUIRED_RUNTIME_DEPENDENCIES = [
    "seaborn",
]


def package_asset_errors(wheel_path: Path) -> list[str]:
    """Return missing or malformed package asset errors for a wheel."""
    if not wheel_path.is_file():
        return [f"Wheel not found: {wheel_path}"]
    if wheel_path.suffix != ".whl":
        return [f"Expected a .whl artifact, got: {wheel_path}"]

    with zipfile.ZipFile(wheel_path) as wheel:
        names = set(wheel.namelist())
        metadata_path = next((name for name in names if name.endswith(".dist-info/METADATA")), None)
        metadata = wheel.read(metadata_path).decode("utf-8") if metadata_path is not None else ""

    errors = [f"Missing packaged asset: {name}" for name in REQUIRED_WHEEL_FILES if name not in names]
    ui_asset_prefix = "dcs_simulation_engine/package_assets/ui_dist/assets/"
    if not any(name.startswith(ui_asset_prefix) and name.endswith(".js") for name in names):
        errors.append("Missing packaged UI JavaScript asset under package_assets/ui_dist/assets/")
    if not any(name.startswith(ui_asset_prefix) and name.endswith(".css") for name in names):
        errors.append("Missing packaged UI CSS asset under package_assets/ui_dist/assets/")
    errors.extend(_runtime_dependency_errors(metadata))
    return errors


def _runtime_dependency_errors(metadata: str) -> list[str]:
    if not metadata:
        return ["Missing wheel metadata: *.dist-info/METADATA"]

    parsed = Parser().parsestr(metadata)
    requires_dist = parsed.get_all("Requires-Dist") or []
    normalized = {_runtime_dependency_name(requirement) for requirement in requires_dist}
    return [
        f"Missing runtime dependency in wheel metadata: {dependency}"
        for dependency in REQUIRED_RUNTIME_DEPENDENCIES
        if dependency not in normalized
    ]


def _runtime_dependency_name(requirement: str) -> str:
    package = requirement.split(";", 1)[0].split("[", 1)[0].split("(", 1)[0].strip().lower()
    return re.split(r"\s|[<>=!~]", package, maxsplit=1)[0]


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
