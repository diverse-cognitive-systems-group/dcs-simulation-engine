"""Access key generation and verification utilities."""

import re
import secrets

DEFAULT_KEY_PREFIX = "dcs-ak-"
ACCESS_KEY_TOKEN_LENGTH = 43
ACCESS_KEY_TOTAL_LENGTH = len(DEFAULT_KEY_PREFIX) + ACCESS_KEY_TOKEN_LENGTH
ACCESS_KEY_PATTERN = re.compile(rf"^{re.escape(DEFAULT_KEY_PREFIX)}[A-Za-z0-9_-]{{{ACCESS_KEY_TOKEN_LENGTH}}}$")


def generate_access_key(*, prefix: str = DEFAULT_KEY_PREFIX) -> str:
    """Generate a random access key string."""
    token = secrets.token_urlsafe(32)
    return prefix + token


def validate_access_key(raw_key: str) -> str:
    """Validate and normalize a raw access key."""
    key = raw_key.strip()
    if len(key) != ACCESS_KEY_TOTAL_LENGTH:
        raise ValueError(f"Admin key must be exactly {ACCESS_KEY_TOTAL_LENGTH} characters long.")
    if not key.startswith(DEFAULT_KEY_PREFIX):
        raise ValueError(f"Admin key must start with '{DEFAULT_KEY_PREFIX}'.")
    if not ACCESS_KEY_PATTERN.fullmatch(key):
        raise ValueError("Admin key must use only URL-safe alphanumeric characters after the prefix (A-Z, a-z, 0-9, '_' or '-').")
    return key
