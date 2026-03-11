"""Errors for DCS Simulation Engine."""


class APIRequestError(RuntimeError):
    """Base class for all domain errors."""


class GameValidationError(APIRequestError):
    """Raised when a game config fails validation."""
