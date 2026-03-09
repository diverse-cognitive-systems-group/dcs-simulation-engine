"""Unit tests for utils/auth.py."""

import pytest
from dcs_simulation_engine.utils.auth import (
    DEFAULT_KEY_PREFIX,
    generate_access_key,
    hash_key,
    verify_key,
)


@pytest.mark.unit
def test_hash_and_verify_roundtrip():
    """hash_key + verify_key round-trips correctly."""
    secret = "my-secret-key"
    hashed = hash_key(secret)
    assert verify_key(secret, hashed) is True


@pytest.mark.unit
def test_verify_rejects_wrong_key():
    """verify_key returns False for a different secret."""
    hashed = hash_key("correct-key")
    assert verify_key("wrong-key", hashed) is False


@pytest.mark.unit
def test_hash_is_non_deterministic():
    """Each call to hash_key produces a unique hash (random bcrypt salt)."""
    h1 = hash_key("same-secret")
    h2 = hash_key("same-secret")
    assert h1 != h2


@pytest.mark.unit
def test_generate_access_key_returns_raw_and_hash():
    """generate_access_key returns (raw_key, key_hash) tuple."""
    raw_key, key_hash = generate_access_key()
    assert isinstance(raw_key, str)
    assert isinstance(key_hash, str)
    assert len(raw_key) > 0
    assert len(key_hash) > 0


@pytest.mark.unit
def test_generate_access_key_default_prefix():
    """Default prefix 'dcs-ak-' is prepended to the generated key."""
    raw_key, _ = generate_access_key()
    assert raw_key.startswith(DEFAULT_KEY_PREFIX)
    assert raw_key.startswith("dcs-ak-")


@pytest.mark.unit
def test_generate_access_key_custom_prefix():
    """Custom prefix is respected."""
    raw_key, _ = generate_access_key(prefix="test-")
    assert raw_key.startswith("test-")


@pytest.mark.unit
def test_generate_access_key_hash_verifies():
    """Hash returned by generate_access_key verifies correctly against raw key."""
    raw_key, key_hash = generate_access_key()
    assert verify_key(raw_key, key_hash) is True


@pytest.mark.unit
def test_generate_access_key_unique():
    """Each call to generate_access_key produces a unique key."""
    key1, _ = generate_access_key()
    key2, _ = generate_access_key()
    assert key1 != key2
