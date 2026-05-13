"""Errors for DCS Simulation Engine."""

from dataclasses import dataclass


class APIRequestError(RuntimeError):
    """Base class for all domain errors."""


class GameValidationError(APIRequestError):
    """Raised when a game config fails validation."""


@dataclass
class ModelProviderError(APIRequestError):
    """Raised when an upstream model provider rejects or cannot serve a request."""

    provider: str
    model: str
    status_code: int | None = None
    provider_code: str | None = None
    provider_message: str = ""
    user_message: str = ""
    retryable: bool = False

    def __post_init__(self) -> None:
        """Generate a user-friendly message if one isn't provided."""
        if not self.user_message:
            self.user_message = _default_user_message(
                provider=self.provider,
                model=self.model,
                status_code=self.status_code,
                provider_message=self.provider_message,
            )
        super().__init__(self.user_message)

    def metadata(self) -> dict[str, str | int | None]:
        """Return public structured fields safe to send to API clients."""
        return {
            "provider": self.provider,
            "provider_status_code": self.status_code,
            "provider_code": self.provider_code,
        }


def _default_user_message(
    *,
    provider: str,
    model: str,
    status_code: int | None,
    provider_message: str,
) -> str:
    provider_label = "OpenRouter" if provider == "openrouter" else provider.title()
    message = " ".join(provider_message.split())
    if status_code == 402:
        return (
            f"Model provider error: {provider_label} needs more credits for {model}. "
            "Add credits, choose a cheaper model, or reduce token usage."
        )
    if message:
        return f"Model provider error from {provider_label} for {model}: {message}"
    return f"Model provider error from {provider_label} for {model}."
