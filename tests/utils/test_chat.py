"""Tests chat_utils module."""

import os

import pytest
from dotenv import load_dotenv

from dcs_simulation_engine.utils.chat import ChatOpenRouter

load_dotenv()

# TODO: pre-oss - consider adding "secrets" in github actions
# if we want to test with real API keys...for now we'll skip


@pytest.mark.slow
@pytest.mark.external
def test_chat_openrouter_instantiation() -> None:
    """Ensure ChatOpenRouter instantiates correctly and uses the API key."""
    api_key = os.getenv("OPENROUTER_API_KEY")
    assert api_key, "OPENROUTER_API_KEY must be set in the environment"

    model = ChatOpenRouter(model="openai/gpt-oss-20b:free")
    assert isinstance(model, ChatOpenRouter)
    assert model.openai_api_key is not None, "openai_api_key should not be None"
    assert model.openai_api_key.get_secret_value() == api_key


@pytest.mark.external
@pytest.mark.slow
def test_chat_openrouter_invoke_responds() -> None:
    """Test that the invoke method returns a response from the model."""
    model = ChatOpenRouter(model="openai/gpt-oss-20b:free")
    response = model.invoke([{"role": "user", "content": "Say hello in Spanish."}])

    assert response is not None
    assert hasattr(response, "content")
    assert isinstance(response.content, str)
    assert len(response.content.strip()) > 0
    print("Response:", response.content)  # run with -s to show
    assert "hola" in response.content.lower()


@pytest.mark.external
@pytest.mark.slow
def test_chat_openrouter_invoke_multi_turn() -> None:
    """Test that invoke handles a multi-message conversation with a system prompt."""
    model = ChatOpenRouter(model="openai/gpt-oss-20b:free", temperature=0.7)

    messages = [
        {
            "role": "system",
            "content": "You are a sad and emotionally withdrawn assistant. \
                Respond with a tone of melancholy.",
        },
        {"role": "user", "content": "I'm planning a trip to Japan."},
        {
            "role": "assistant",
            "content": "That sounds nice... I guess. Japan has some beautiful places.",
        },
        {"role": "user", "content": "Kyoto. What are the top historical sites?"},
    ]

    response = model.invoke(messages)

    assert response is not None
    assert hasattr(response, "content")
    assert isinstance(response.content, str)
    assert len(response.content.strip()) > 0
    print("Sad assistant response:", response.content)
