"""Errors for DCS Simulation Engine."""


class DCSError(RuntimeError):
    """Base class for all domain errors."""


class GameValidationError(DCSError):
    """Raised when a game config fails validation."""
