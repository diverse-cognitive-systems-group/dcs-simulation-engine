"""Serialization / deserialization (serde) mixin for Pydantic models.

Example Usage:
x = X(uid="sys1", short_description="Test")

d = x.to_dict()
js = x.to_json(indent=2)
ys = x.to_yaml()

x1 = X.from_json(js)
x2 = X.from_yaml(ys)

x.save_json("system.json", indent=2)
x.save_yaml("system.yml")

x4 = X.load_json("system.json")
x5 = X.load_yaml("system.yml")

"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, TypeVar, Union, get_args, get_origin

import yaml
from loguru import logger
from pydantic import BaseModel, ValidationError, fields

T = TypeVar("T", bound="BaseModel")


class SerdeMixin(BaseModel):
    """Mixin adding serialization / deserialization methods to Pydantic models."""

    # ---------- nice exports ----------
    def to_dict(self, **dump_kwargs: Any) -> dict[str, Any]:
        """Convert model to dict. Pass model_dump kwargs if desired."""
        return self.model_dump(**dump_kwargs)

    def to_json(self, **dump_kwargs: Any) -> str:
        """Convert model to JSON string."""
        return self.model_dump_json(**dump_kwargs)

    def to_yaml(self, **dump_kwargs: Any) -> str:
        """Convert model to readable YAML.

        Pass yaml.safe_dump kwargs if desired (e.g., sort_keys=False).
        """
        # TODO: pre-v001 make export nice yml not all the /newlines
        data = self.model_dump()
        # readable, block-style YAML; avoid single-line flow; keep key order
        return str(
            yaml.safe_dump(
                data,
                allow_unicode=True,
                sort_keys=False,
                default_flow_style=False,
                width=88,
                **dump_kwargs,
            )
        )

    # ---------- user-friendly loaders ----------
    @classmethod
    def from_json(
        cls: type[T], source: Union[Mapping[str, Any], str, Path], **kw: Any
    ) -> T:
        """Instantiate model from a JSON string or a file path with friendly errors."""
        # logger.debug(f"Serde called with source type: {type(source)}")
        # logger.debug(f"Source content: {str(source)}")
        if isinstance(source, Mapping):
            logger.debug("Source is a Mapping, using model_validate")
            return cls.model_validate(source, **kw)
        if isinstance(source, Path):
            logger.debug("Source is a Path, reading text")
            text = source.read_text(encoding="utf-8")
            return cls.model_validate_json(text, **kw)
        # string: prefer JSON first; only then try file
        logger.debug("Source is a string, checking content")
        s = source.strip()
        if s.startswith("{") or s.startswith("["):
            return cls.model_validate_json(s, **kw)
        try:
            return cls.model_validate_json(
                Path(source).read_text(encoding="utf-8"), **kw
            )
        except OSError:
            # Not a file; assume it's JSON content even if not '{'/'[' prefixed
            return cls.model_validate_json(source, **kw)

    @classmethod
    def from_yaml(cls: type[T], source: Union[str, Path], **validate_kwargs: Any) -> T:
        """Instantiate model from a YAML string or a file path with friendly errors."""
        if isinstance(source, Path) or (
            isinstance(source, str) and Path(source).exists()
        ):
            text = Path(source).read_text(encoding="utf-8")
        else:
            text = str(source)

        try:
            data = yaml.safe_load(text) or {}
        except yaml.YAMLError as e:
            raise ValueError(SerdeMixin._format_yaml_syntax_error(e, text)) from e

        try:
            return cls.model_validate(data, **validate_kwargs)
        except ValidationError as e:
            raise ValueError(
                SerdeMixin._format_validation_error(e, data=data, model=cls)
            ) from e

    # ---------- convenience save/load ----------
    def save_json(self, path: Union[str, Path], **dump_kwargs: Any) -> Path:
        """Save model to a JSON file. Returns the Path."""
        p = Path(path)
        p.write_text(self.to_json(**dump_kwargs), encoding="utf-8")
        return p

    def save_yaml(self, path: Union[str, Path], **dump_kwargs: Any) -> Path:
        """Save model to a YAML file. Returns the Path."""
        p = Path(path)
        p.write_text(self.to_yaml(**dump_kwargs), encoding="utf-8")
        return p

    @classmethod
    def load_json(cls: type[T], path: Union[str, Path], **validate_kwargs: Any) -> T:
        """Load model from a JSON file."""
        return cls.from_json(Path(path), **validate_kwargs)  # type: ignore

    @classmethod
    def load_yaml(cls: type[T], path: Union[str, Path], **validate_kwargs: Any) -> T:
        """Load model from a YAML file."""
        return cls.from_yaml(Path(path), **validate_kwargs)  # type: ignore

    # ---------- helpers: friendly error messages ----------
    @staticmethod
    def _yaml_context_snippet(text: str, line: int, col: int, context: int = 1) -> str:
        """Build a tiny snippet pointing to the YAML error location.

        Lines are 1-based.
        """
        lines = text.splitlines()
        i = max(line - 1 - context, 0)
        j = min(line + context, len(lines))
        out = []
        for idx in range(i, j):
            prefix = ">" if idx == line - 1 else " "
            out.append(f"{prefix} {idx+1:>4}: {lines[idx]}")
            if idx == line - 1:
                caret = " " * (col + 7) + "^"  # 7 accounts for formatting above
                out.append(caret)
        return "\n".join(out)

    @classmethod
    def _format_yaml_syntax_error(cls, e: yaml.YAMLError, text: str) -> str:
        # Try to extract line/column from PyYAML mark
        line = col = None
        problem_mark = getattr(e, "problem_mark", None)
        if problem_mark:
            line = problem_mark.line + 1
            col = problem_mark.column
        header = "Your YAML isn't valid."
        if line is not None and col is not None:
            snippet = cls._yaml_context_snippet(text, line, col)
            return f"{header}\nLine {line}, column {col+1}.\n\n{snippet}\n\nFix the \
                 YAML formatting at the ^ marker."
        return f"{header} {str(e)}"

    @classmethod
    def _format_validation_error(
        cls,
        e: ValidationError,
        data: Any | None = None,
        model: type[BaseModel] | None = None,
    ) -> str:
        """Turn Pydantic errors into actionable, plain-English guidance."""
        lines = ["Your YAML loaded, but it doesn't match the expected structure:"]
        for err in e.errors():
            loc = ".".join(str(p) for p in err.get("loc", ()))
            typ = err.get("type", "")
            msg = err.get("msg", "")
            entry = cls._humanize_error(loc, typ, msg, model)
            lines.append(f"• {entry}")
        lines.append(
            "\nTip: keys are case-sensitive; remove unknown keys; \
                match the types shown."
        )
        return "\n".join(lines)

    @classmethod
    def _humanize_error(
        cls, loc: str, typ: str, msg: str, model: type[BaseModel] | None
    ) -> str:
        # Missing required field
        if "missing" in typ or "missing" in msg.lower():
            suggestion = cls._suggest_example(loc, model)
            return f"Missing required field: `{loc}`. Add it like:\n{suggestion}"
        # Extra / unknown field
        if "extra_forbidden" in typ or "extra fields not permitted" in msg.lower():
            return f"Unknown field at `{loc}`. Remove this key or rename it to a \
                valid field."
        # Type error
        if "type_error" in typ or "input_type" in typ or "value_error" in typ:
            expected = cls._extract_expected_type_from_msg(msg)
            return f"Wrong type at `{loc}`. {expected}"
        # Fallback
        nice = msg[0].upper() + msg[1:] if msg else "Invalid value."
        return f"{nice} (at `{loc}`)."

    @staticmethod
    def _extract_expected_type_from_msg(msg: str) -> str:
        # Pydantic v2 error messages often include "Input should be <type>"
        # Keep this short and friendly.
        if msg.lower().startswith("input should be"):
            return msg
        return f"{msg}"

    @classmethod
    def _suggest_example(cls, loc: str, model: type[BaseModel] | None) -> str:
        """Build a minimal YAML example for a missing field by inspecting the model."""
        if not model:
            return f"{cls._yaml_block_for_path(loc, '<value>')}"
        # Walk model_fields using the dotted path if possible
        parts = loc.split(".") if loc else []
        current_model = model
        field_type = None
        try:
            for p in parts:
                fld: fields.FieldInfo = current_model.model_fields[p]
                field_type = fld.annotation
                origin = get_origin(field_type)
                args = get_args(field_type)
                # If nested BaseModel, descend
                if isinstance(fld.annotation, type) and issubclass(
                    fld.annotation, BaseModel
                ):
                    current_model = fld.annotation
                elif (
                    origin in (list, tuple)
                    and args
                    and isinstance(args[0], type)
                    and issubclass(args[0], BaseModel)
                ):
                    current_model = args[0]  # item model
                # else:
                #     current_model = None  # stop
        except Exception:
            pass

        example_val = cls._example_for_type(field_type)
        return cls._yaml_block_for_path(loc, example_val)

    @staticmethod
    def _yaml_block_for_path(path: str, leaf: str) -> str:
        """Build a tiny YAML block with indentation for a dotted path.

        Return an indented YAML block like:
        parent:
          child: <example>
        """
        if not path:
            return leaf
        parts = path.split(".")
        indent = ""
        lines = []
        for i, p in enumerate(parts):
            if i == len(parts) - 1:
                lines.append(f"{indent}{p}: {leaf}")
            else:
                lines.append(f"{indent}{p}:")
            indent += "  "
        return "\n" + "\n".join(lines)

    @staticmethod
    def _example_for_type(tp: Any) -> str:
        # Heuristic examples; kept simple for lay users
        if tp is None:
            return "<value>"
        origin = get_origin(tp)
        args = get_args(tp)

        def name(t: Any) -> Any:
            """Get a friendly name for a type."""
            try:
                return t.__name__
            except Exception:
                return str(t)

        # Common primitives
        if tp in (int, float):
            return "123" if tp is int else "12.34"
        if tp is bool:
            return "true"
        if tp is str:
            return "<text>"
        # Optionals / Unions
        if origin is Union:
            return f"<{ ' or '.join(name(a) for a in args) }>"
        # Collections
        if origin in (list, tuple, set):
            inner = _try_example(args[0]) if args else "<item>"
            return f"\n  - {inner}"
        if origin is dict:
            k = _try_example(args[0]) if args else "<key>"
            v = _try_example(args[1]) if len(args) > 1 else "<value>"
            return f"\n  {k}: {v}"
        # Nested models
        try:
            if issubclass(tp, BaseModel):
                return "\n  <subfields…>"
        except Exception:
            pass
        return "<value>"


def _try_example(tp: Any) -> str:
    return SerdeMixin._example_for_type(tp)
