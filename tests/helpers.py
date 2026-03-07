"""Helpers tests."""

import copy
from pathlib import Path
from types import SimpleNamespace

import yaml


def _merge_into(base: dict, patch: dict) -> dict:
    """Deep-ish merge: patch keys overwrite; descend only if both sides are dicts."""
    out = copy.deepcopy(base)
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge_into(out[k], v)
        else:
            out[k] = v
    return out


def patch_yaml(base_path: Path, patch_yaml_str: str) -> SimpleNamespace:
    """Patch a YAML file with additional YAML content."""
    base = yaml.safe_load(base_path.read_text())
    patch = yaml.safe_load(patch_yaml_str)
    merged = _merge_into(base, patch)

    patched_path = base_path.with_name(base_path.stem + "_patched.yaml")
    patched_path.write_text(yaml.safe_dump(merged))
    return SimpleNamespace(path=patched_path, data=merged)
