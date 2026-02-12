"""Mock LLM client for testing without real API calls."""
from typing import Any, Dict, List, Optional, Iterator
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, AIMessage
from langchain_core.outputs import ChatResult, ChatGeneration
from langchain_core.callbacks.manager import CallbackManagerForLLMRun


class MockChatModel(BaseChatModel):
    """Deterministic mock LLM for testing.

    This mock replaces ChatOpenRouter calls with predetermined responses,
    allowing tests to run without external API dependencies.

    Responses can be customized by providing a responses dict with
    "validator" and "updater" keys, or by providing a list of responses
    that will be cycled through.
    """

    responses: Dict[str, Any] = {}
    call_count: int = 0

    def __init__(self, responses: Optional[Dict[str, Any]] = None, **kwargs):
        """Initialize mock with predetermined responses.

        Args:
            responses: Dict with "validator" and "updater" keys, or
                      "responses_list" for cycling through multiple responses
        """
        super().__init__(**kwargs)
        self.responses = responses or {
            "validator": '{"type": "info", "content": "Valid action within character abilities"}',
            "updater": '{"type": "ai", "content": "The flatworm moves slowly across the surface."}'
        }
        self.call_count = 0

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Return mock response based on prompt content.

        Detects whether the prompt is for a validator or updater based on
        keywords in the system prompt, and returns appropriate response.
        """
        # Get the prompt text from messages
        prompt_text = messages[0].content if messages else ""

        # If responses_list is provided, cycle through them
        if "responses_list" in self.responses:
            response_list = self.responses["responses_list"]
            response_text = response_list[self.call_count % len(response_list)]
            self.call_count += 1
        # Otherwise, detect validator vs updater based on system prompt
        elif "valid observable action" in prompt_text.lower() or "validator" in prompt_text.lower():
            response_text = self.responses.get("validator", self.responses["validator"])
            self.call_count += 1
        else:
            # For updater, cycle through responses if it's a list
            updater_response = self.responses.get("updater", self.responses["updater"])
            if isinstance(updater_response, list):
                response_text = updater_response[self.call_count % len(updater_response)]
            else:
                response_text = updater_response
            self.call_count += 1

        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content=response_text))]
        )

    @property
    def _llm_type(self) -> str:
        """Return identifier for this LLM type."""
        return "mock"

    @property
    def _identifying_params(self) -> Dict[str, Any]:
        """Return identifying parameters."""
        return {"model": "mock", "responses": self.responses}
