import httpx


class AIClient:
    """Abstract base class for AI clients."""

    async def chat(self, user_input: str) -> str:
        raise NotImplementedError

    def reset(self) -> None:
        raise NotImplementedError


class LLMClient(AIClient):
    """Async client for LM Studio's native chat API."""

    def __init__(
        self,
        model: str,
        base_url: str = "http://localhost:1234",
        system_prompt: str | None = None,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.system_prompt = system_prompt
        self._last_response_id: str | None = None

    def reset(self) -> None:
        """Clear conversation history by dropping the stored response ID."""
        self._last_response_id = None

    async def chat(self, user_input: str | None) -> str:
        """Send a message and return the assistant's reply, maintaining conversation context."""
        if not user_input:
            user_input = "Begin."

        payload: dict = {"model": self.model, "input": user_input}
        if self.system_prompt and not self._last_response_id:
            payload["system_prompt"] = self.system_prompt

        if self._last_response_id:
            payload["previous_response_id"] = self._last_response_id

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/v1/chat",
                json=payload,
                timeout=None,
            )
            response.raise_for_status()
            data = response.json()

        self._last_response_id = data.get("id")

        message_content = None
        for x in data["output"]:
            if x["type"] == "message":
                message_content = x["content"]
                break

        if message_content is None:
            raise ValueError("No message content found in response")

        return message_content


class OpenRouterClient(AIClient):
    """Async client for OpenRouter's OpenAI-compatible chat API."""

    def __init__(
        self,
        model: str,
        api_key: str,
        system_prompt: str | None = None,
    ) -> None:
        """Initialize the OpenRouter client."""
        self.model = model
        self.api_key = api_key
        self.system_prompt = system_prompt
        self._messages: list[dict] = []

    def reset(self) -> None:
        """Clear conversation history."""
        self._messages = []

    async def chat(self, user_input: str) -> str:
        """Send a message and return the assistant's reply, maintaining conversation context."""
        self._messages.append({"role": "user", "content": user_input})

        messages = self._messages
        if self.system_prompt:
            messages = [{"role": "system", "content": self.system_prompt}] + self._messages

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": self.model, "messages": messages},
                timeout=None,
            )
            if response.is_error:
                raise httpx.HTTPStatusError(
                    f"{response.status_code}: {response.text}",
                    request=response.request,
                    response=response,
                )
            data = response.json()

        reply = data["choices"][0]["message"]["content"]
        self._messages.append({"role": "assistant", "content": reply})
        return reply
