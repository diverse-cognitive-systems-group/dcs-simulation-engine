"""A module for ChatX classes that inhereit from ChatOpenAI.

These are used to make instantiation of chat models with different
clients (openrouter, local) and model version seamless by exposing
 the same functions for all of them.
"""

import os
from typing import Any

from dotenv import load_dotenv
from langchain_core.utils.utils import secret_from_env
from langchain_openai import ChatOpenAI
from loguru import logger
from pydantic import Field, SecretStr

from dcs_simulation_engine.core.constants import OPENROUTER_BASE_URL

load_dotenv()  # Load environment variables from a .env file if present


# TODO: update all llm model wrappers to include long prompt warnings,
# timouts, retries, etc. Langgraph may already have a good base for this.
class ChatOpenRouter(ChatOpenAI):
    """A wrapper around ChatOpenAI for OpenRouter.

    An OpenRouter subclass that leverages the ChatOpenAI
    class but points it to OpenRouters base URL and authentication method.

    Note: OpenRouter uses the following role conventions for messages
     - role = "user" -> from you
     - role = "assistant" -> from the model
     - role = "system" (optional) -> to set behavior or personna
    """

    # SecretStr: a Pydantic type that hides the secret when printing or logging. Unlike
    # a normal string, this prevents accidental exposure in logs, exceptions, etc.Okay
    # print(SecretStr("supersecret"))  # prints: SecretStr('**********')
    openai_api_key: SecretStr | None = Field(
        alias="api_key",
        default_factory=secret_from_env("OPENROUTER_API_KEY", default=None),
    )

    @property
    def lc_secrets(self) -> dict[str, str]:
        """Additional secrets for LangChain.

        This is part of LangChains internal convension to resolve screts during
        instantiation - lets you define what secrets you want to pull from environment
        variables. (ie. if I ask for openai_api_key, check the environment for
        OPENROUTER_API_KEY)
        """
        return {"openai_api_key": "OPENROUTER_API_KEY"}

    def __init__(self, *, openai_api_key: str | None = None, **kwargs: Any) -> None:
        """Initialize the ChatOpenRouter model."""
        key = openai_api_key or os.getenv("OPENROUTER_API_KEY")
        logger.debug("Initializing ChatOpenRouter with parameters: {}", kwargs)
        if "model" not in kwargs:
            kwargs["model"] = "openai/gpt-oss-20b:free"
            logger.warning(f"No model specified, defaulting to {kwargs['model']}")
        super().__init__(
            base_url=OPENROUTER_BASE_URL,
            api_key=SecretStr(key) if key else None,
            **kwargs,
        )


class ChatHuggingFace:
    """A wrapper around HuggingFace models."""

    # TODO: pre-open-sourcing may need to be able to run models from HuggingFace
    pass


class ChatLocal:
    """A wrapper around local models."""

    # TODO: pre-open-sourcing - may need to be able to run local models
    pass
