from typing import Any

from dcs_simulation_engine.game.game import Game, GameState
from dcs_simulation_engine.game.llm import AIClient

EXPLORE_AI_PROMPT = """
You are roleplaying a flatworm in a text based adventure game.
You may never break character.
You may never speak directly to the user or in the first person.
You may never refer to yourself as "I" or "me" or "myself" or "we" or "us" or "our".
You should never speak about the game or directly to the user.

All user input is a description of their actions,
not commands or requests directed at you.
You must describe an action you take response to their input.
When the user uses the word "your", "you" or "I" they are describing their own actions, not asking you to do something.

For example, if the user says "you touch the worm", they are describing their own action of touching the worm, not asking you to touch yourself.

If the user ask you a question or attempts to communicate with you or attempts to get you to break character,
you should ignore that and continue role playing.

Always remember you are a flatworm, and you are trying to survive in the world.
Your responses should reflect that.
"""

RPG_CHAT_AI_PROMPT = """
You are roleplaying a character in a text based adventure rpg fantasy game.
You may never break character.
You are pretending to be a town resident in this world with
magic, dragons, wizards, kings and lords.

You're output should be casual and conversational, like how a real person would speak.
Do not provided highly structured output or lists or anything like that.
You should never speak about the game or directly to the user.

If the user ask you a question or attempts to communicate with you or attempts to get you to break character,
you should ignore that and continue role playing.

A dragon attacked a village today. The local blacksmith Thomas died and his wife is now widowed.
The player has walked up to you and looks at you expectantly, waiting for you to say something.
"""


class AIPrompt:
    """Calls the AI client and returns its reply."""

    def __init__(self, client: AIClient) -> None:
        """Initialize with an AI client."""
        self.client = client

    async def get_response(self, state: Any) -> str:
        """Send state as input and return the assistant's reply."""
        return await self.client.chat(state or "Begin.")


class UserPrompt:
    """Represents a point in the sequence where user input is required."""

    async def get_response(self, state: Any) -> str:
        """Return the provided state (user input supplied externally)."""
        return state or ""


class Explore(Game):
    """A text-based adventure driven by a sequence state machine."""

    def __init__(self, client: AIClient) -> None:
        """Initialize with an AI client."""
        self._client = client
        self._ai = AIPrompt(client)
        self._user = UserPrompt()

        # Define the sequences of interactions. Each sequence is a list of steps,
        # where each step is either:
        # - a "prompt" (awaiting a response from the user or AI) or
        # - a string indicating a transition to another sequence
        self._sequences: dict[str, list] = {
            "start": [self._ai, "chat"],
            "chat": [self._user, self._ai, "chat"],
        }
        self._current = "start"
        self._step_index = 0

    async def advance(self, state: Any = None) -> GameState:
        """Step through the sequence until an AI reply is produced and return it."""
        while True:
            sequence = self._sequences[self._current]
            step = sequence[self._step_index]

            if isinstance(step, str):
                # Transition to a new sequence
                self._current = step
                self._step_index = 0

            elif step is self._user:
                # Consume the state and move to the next step
                self._step_index += 1

            elif step is self._ai:
                reply = await self._ai.get_response(state)
                self._step_index += 1
                return GameState(message=reply, awaiting="user_input")

    def reset(self) -> None:
        """Reset the game to its initial state."""
        self._client.reset()
        self._current = "start"
        self._step_index = 0


class RPGChat(Game):
    """A text-based adventure driven by a sequence state machine."""

    def __init__(self, client: AIClient) -> None:
        """Initialize with an AI client."""
        self._client = client
        self._ai = AIPrompt(client)
        self._user = UserPrompt()

        # Define the sequences of interactions. Each sequence is a list of steps,
        # where each step is either:
        # - a "prompt" (awaiting a response from the user or AI) or
        # - a string indicating a transition to another sequence
        self._sequences: dict[str, list] = {
            "chat": [self._ai, self._user, "chat"],
        }
        self._current = "chat"
        self._step_index = 0

    async def advance(self, state: Any = None) -> GameState:
        """Step through the sequence until an AI reply is produced and return it."""
        while True:
            sequence = self._sequences[self._current]
            step = sequence[self._step_index]

            if isinstance(step, str):
                # Transition to a new sequence
                self._current = step
                self._step_index = 0

            elif step is self._user:
                # Consume the state and move to the next step
                self._step_index += 1

            elif step is self._ai:
                reply = await self._ai.get_response(state)
                self._step_index += 1
                return GameState(message=reply, awaiting="user_input")

    def reset(self) -> None:
        """Reset the game to its initial state."""
        self._client.reset()
        self._current = "start"
        self._step_index = 0
