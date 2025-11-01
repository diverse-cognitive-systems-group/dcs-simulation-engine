"""Validation helpers module.

Generic YAML validation helpers using Yamale.

- Works with a single file OR a directory.
- If target is a directory, you can --include / --exclude globs.
- Schema resolution priority when schema_path is not given:
    1) <target_dir>/<schema_filename>
    2) <target_dir>/schemas/<schema_filename>
    3) ./schemas/<schema_filename>   (cwd fallback)
- Returns structured results to the caller (script does the printing/exit).
"""

from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import Dict, List

import yamale
from yamale import YamaleError


def _is_yaml(p: Path) -> bool:
    """Check if a Path is a YAML file by extension."""
    return p.is_file() and p.suffix.lower() in {".yml", ".yaml"}


def _match_any(name: str, patterns: List[str]) -> bool:
    """Check if name matches any of the given glob patterns."""
    return any(fnmatch.fnmatch(name, pat) for pat in patterns)


def _list_dir_yaml(dir_path: Path) -> List[Path]:
    """List all YAML files in a directory (non-recursive)."""
    return [p for p in dir_path.iterdir() if _is_yaml(p) and not p.name.startswith(".")]


# def _resolve_target_files(
#     target_path: Path,
#     includes: List[str] | None,
#     excludes: List[str] | None,
#     schema_filename: str,
# ) -> List[Path]:
#     """Resolve target files to validate.

#     If target_path is a file -> validate that file.
#     If directory -> collect YAML files, apply include/exclude globs.
#     Also auto-protect typical schema filenames from being validated.
#     """
#     schema_candidates = {schema_filename, ".schema.yml", "schema.yamale"}

#     if target_path.is_file():
#         return [target_path] if _is_yaml(target_path) else []

#     # directory mode
#     excludes = excludes or []
#     if includes:
#         selected: set[Path] = set()
#         for pat in includes:
#             selected.update({p for p in target_path.glob(pat) if _is_yaml(p)})
#         files = sorted(selected)
#     else:
#         files = sorted(_list_dir_yaml(target_path))

#     def keep(p: Path) -> bool:
#         if p.name in schema_candidates or p.name.startswith("."):
#             return False
#         if excludes and _match_any(p.name, excludes):
#             return False
#         return True

#     return [p for p in files if keep(p)]


# def _resolve_schema_path(
#     target_path: Path, schema_path: str | Path | None, schema_filename: str
# ) -> Path:
#     """Choose a schema path using the priority described in the module docstring."""
#     if schema_path:
#         sp = Path(schema_path).resolve()
#         if not sp.exists():
#             raise FileNotFoundError(f"Schema file not found: {sp}")
#         return sp

#     base_dir = target_path.parent if target_path.is_file() else target_path
#     candidates = [
#         (base_dir / schema_filename),
#         (base_dir / "schemas" / schema_filename),
#         (Path.cwd() / "schemas" / schema_filename),
#     ]
#     for c in candidates:
#         if c.exists():
#             return c.resolve()
#     raise FileNotFoundError(
#         f"No schema found. Tried: {', '.join(str(c) for c in candidates)}"
#     )


# def validate_files_with_schema(
#     target: str | Path,
#     schema_path: str | Path | None = None,
#     *,
#     schema_filename: str = ".schema.yml",
#     includes: List[str] | None = None,
#     excludes: List[str] | None = None,
# ) -> Dict[Path, List[str]]:
#     """Validate YAML file(s) against a Yamale schema.

#     Returns:
#         dict[Path, list[str]]  # empty list means valid; non-empty list = errors

#     Raises:
#         FileNotFoundError if target or schema not found.
#     """
#     target_path = Path(target).resolve()
#     if not target_path.exists():
#         raise FileNotFoundError(f"Target not found: {target_path}")

#     schema_p = _resolve_schema_path(target_path, schema_path, schema_filename)
#     files = _resolve_target_files(target_path, includes, excludes, schema_p.name)

#     if not files:
#         return {}  # nothing to validate (caller can treat as no-op)

#     schema = yamale.make_schema(str(schema_p))
#     # data = yamale.make_data([str(p) for p in files], parser="ruamel")
#     data_parts = []
#     for p in files:
#         data_parts.extend(yamale.make_data(str(p)))
#     data = data_parts

#     results: Dict[Path, List[str]] = {p: [] for p in files}
#     try:
#         yamale.validate(schema, data)
#     except YamaleError as e:
#         # Build a quick index by filename to be resilient to absolute/relative diffs
#         by_name = {p.name: p for p in files}

#         for r in e.results:
#             # r.data may be a Data obj with .path OR a str
#             raw_path = getattr(r.data, "path", r.data)
#             fname = Path(str(raw_path)).name  # normalize to just the filename
#             target_path = by_name.get(fname, Path(str(raw_path)))

#             # ensure key exists even if path styles differ
#             results.setdefault(target_path, [])
#             results[target_path].extend(str(err) for err in r.errors)
#     return results


# def validate_and_print(
#     target: str | Path,
#     schema_path: str | Path | None = None,
#     *,
#     schema_filename: str = ".schema.yml",
#     includes: List[str] | None = None,
#     excludes: List[str] | None = None,
# ) -> bool:
#     """Convenience wrapper to pretty print validation summary.

#     Returns:
#         bool # True if all files are valid.
#     """
#     results = validate_files_with_schema(
#         target=target,
#         schema_path=schema_path,
#         schema_filename=schema_filename,
#         includes=includes,
#         excludes=excludes,
#     )

#     if not results:
#         print(f"ℹ️ No YAML files to validate under {Path(target).resolve()}")
#         return True

#     invalid = {p: errs for p, errs in results.items() if errs}
#     if not invalid:
#         print(f"✅ {len(results)} file(s) valid against schema")
#         for p in sorted(results.keys()):
#             print(f"   • {p.name}")
#         return True

#     print("❌ Validation failed:")
#     for p, errs in invalid.items():
#         print(f"\n— File: {p.name}")
#         for msg in errs:
#             hint = "  (Hint: required by schema)" if "required" in msg else ""
#             print(f"   • {msg}{hint}")
#     return False
