"""Import boundary tests for the autoplay client."""

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_FORBIDDEN_PREFIXES = (
    "dcs_simulation_engine.api.app",
    "dcs_simulation_engine.api.routers",
    "dcs_simulation_engine.cli",
    "dcs_simulation_engine.core",
    "dcs_simulation_engine.dal",
    "dcs_simulation_engine.games",
)


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def test_autoplay_imports_only_api_boundary_modules() -> None:
    """Autoplay should remain a client package, separate from engine internals."""
    root = Path("autoplay")
    violations = []
    for path in sorted(root.glob("*.py")):
        for module in _imported_modules(path):
            if module == "dcs_simulation_engine.api.models":
                continue
            if module.startswith(_FORBIDDEN_PREFIXES):
                violations.append(f"{path}: {module}")

    assert not violations, "autoplay imported engine internals:\n" + "\n".join(violations)
