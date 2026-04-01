"""Unit tests for utils/auth.py."""

import pytest
from dcs_simulation_engine.utils.auth import (
    ACCESS_KEY_TOTAL_LENGTH,
    DEFAULT_KEY_PREFIX,
    generate_access_key,
    validate_access_key,
)


@pytest.mark.unit
def test_generate_access_key_returns_string():
    """generate_access_key returns a raw key string."""
    raw_key = generate_access_key()
    assert isinstance(raw_key, str)
    assert len(raw_key) == ACCESS_KEY_TOTAL_LENGTH


@pytest.mark.unit
def test_generate_access_key_default_prefix():
    """Default prefix 'dcs-ak-' is prepended to the generated key."""
    raw_key = generate_access_key()
    assert raw_key.startswith(DEFAULT_KEY_PREFIX)
    assert raw_key.startswith("dcs-ak-")


@pytest.mark.unit
def test_generate_access_key_custom_prefix():
    """Custom prefix is respected."""
    raw_key = generate_access_key(prefix="test-")
    assert raw_key.startswith("test-")


@pytest.mark.unit
def test_generate_access_key_unique():
    """Each call to generate_access_key produces a unique key."""
    key1 = generate_access_key()
    key2 = generate_access_key()
    assert key1 != key2


@pytest.mark.unit
def test_validate_access_key_accepts_generated_key():
    """validate_access_key accepts the generated dcs-ak format."""
    raw_key = generate_access_key()
    assert validate_access_key(raw_key) == raw_key


@pytest.mark.unit
@pytest.mark.parametrize(
    ("raw_key", "message"),
    [
        ("dcs-ak-short", "exactly"),
        ("bad-prefix-" + ("A" * 39), "must start"),
        ("dcs-ak-" + ("A" * 42) + "!", "URL-safe"),
    ],
)
def test_validate_access_key_rejects_invalid_keys(raw_key: str, message: str):
    """validate_access_key rejects malformed admin keys."""
    with pytest.raises(ValueError, match=message):
        validate_access_key(raw_key)
