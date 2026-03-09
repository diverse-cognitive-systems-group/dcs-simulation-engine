"""Access key generation and verification utilities."""

import secrets

import bcrypt

DEFAULT_KEY_PREFIX = "dcs-ak-"


def hash_key(secret: str) -> str:
    """Hash a raw key using bcrypt.

    Returns:
        A bcrypt hash string suitable for storage.
    """
    return bcrypt.hashpw(secret.encode(), bcrypt.gensalt()).decode()


def verify_key(secret: str, hashed: str) -> bool:
    """Verify a raw key against a stored bcrypt hash.

    Returns:
        True if the key matches, False otherwise.
    """
    return bcrypt.checkpw(secret.encode(), hashed.encode())


def generate_access_key(*, prefix: str = DEFAULT_KEY_PREFIX) -> tuple[str, str]:
    """Generate a random access key and its bcrypt hash.

    Args:
        prefix: String prepended to the key (e.g. "dcs-ak-").

    Returns:
        (raw_key, key_hash) — show raw_key to user once, store only key_hash.
    """
    token = secrets.token_urlsafe(32)
    raw_key = prefix + token
    return raw_key, hash_key(raw_key)
