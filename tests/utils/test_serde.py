"""Tests for serde utilities with enhanced error messages."""

from typing import Optional

import pytest
from pydantic import ConfigDict

from dcs_simulation_engine.utils.serde import SerdeMixin


class ATestClass(SerdeMixin):
    """Test class for serde with validation."""

    model_config = ConfigDict(extra="forbid")
    name: str
    count: int
    enabled: bool
    metadata: Optional[dict] = None


def test_yaml_validation_errors_are_user_friendly() -> None:
    """Should raise ValueError with friendly message on bad YAML."""
    # YAML with multiple problems:
    # - missing 'name'
    # - wrong type for 'count'
    # - unknown field 'extra'
    bad_yaml = """
count: "not_a_number"
enabled: true
extra: value
"""

    with pytest.raises(ValueError) as exc:
        ATestClass.from_yaml(bad_yaml)

    msg = str(exc.value)

    # All errors in one message
    assert "doesn't match the expected structure" in msg
    assert "Missing required field: `name`" in msg
    # accept either our friendly wording or Pydantic's native text with the location
    assert ("Wrong type at `count`" in msg) or (
        "Input should be a valid integer" in msg and "at `count`" in msg
    )
    assert "Unknown field at `extra`" in msg
    # sanity check that tip line shows up
    assert "Tip:" in msg


def test_json_roundtrip_from_string() -> None:
    """from_json should construct the model from a JSON string."""
    original = ATestClass(name="alpha", count=3, enabled=True, metadata={"k": "v"})
    js = original.to_json()
    loaded = ATestClass.from_json(js)
    assert loaded == original


def test_from_json_from_path(tmp_path) -> None:
    """from_json should accept both Path objects and string file paths."""
    obj = ATestClass(name="bravo", count=7, enabled=False)
    p = tmp_path / "obj.json"
    obj.save_json(p, indent=2)

    # Path object
    loaded_path = ATestClass.from_json(p)
    assert loaded_path == obj

    # String path
    loaded_strpath = ATestClass.from_json(str(p))
    assert loaded_strpath == obj


def test_from_json_from_mapping() -> None:
    """from_json should accept a Mapping and validate it directly."""
    data = {"name": "charlie", "count": 10, "enabled": True, "metadata": {"x": 1}}
    loaded = ATestClass.from_json(data)
    assert isinstance(loaded, ATestClass)
    assert loaded.name == "charlie"
    assert loaded.count == 10
    assert loaded.enabled is True
    assert loaded.metadata == {"x": 1}
