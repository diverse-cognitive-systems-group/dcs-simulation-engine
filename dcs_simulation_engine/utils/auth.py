"""Access key generation and verification utilities."""

import secrets

DEFAULT_KEY_PREFIX = "dcs-ak-"


def generate_access_key(*, prefix: str = DEFAULT_KEY_PREFIX) -> str:
    """Generate a random access key string.

    Args:
        prefix: String prepended to the key (e.g. "dcs-ak-").

    Returns:
        The raw access key.
    """
    token = secrets.token_urlsafe(32)
    return prefix + token
