"""Unit tests for base Game defaults exercised through ExploreGame."""

import pytest
from dcs_simulation_engine.core.game import Game, GameEvent
from dcs_simulation_engine.dal.base import CharacterRecord
from dcs_simulation_engine.dal.character_filters import get_character_filter
from dcs_simulation_engine.games.ai_client import ParsedSimulatorResponse, SimulatorClient, SimulatorComponentResult, SimulatorTurnResult
from dcs_simulation_engine.games.explore import ExploreGame
from dcs_simulation_engine.games.foresight import ForesightGame
from dcs_simulation_engine.games.goal_horizon import GoalHorizonGame
from dcs_simulation_engine.games.infer_intent import InferIntentGame
from dcs_simulation_engine.games.teamwork import TeamworkGame
from pydantic import ValidationError

pytestmark = [pytest.mark.unit, pytest.mark.anyio]


class StubEngine:
    """Minimal engine stub for exercising Game.step() behavior."""

    def __init__(
        self,
        *,
        opening: ParsedSimulatorResponse | None = None,
        step_results: list[SimulatorTurnResult] | None = None,
    ) -> None:
        """Configure the opening response and queued step results for the stub."""
        self.opening = opening or ParsedSimulatorResponse(
            type="ai",
            content="The room hums quietly around you.",
            metadata={},
            raw_response='{"type":"ai","content":"The room hums quietly around you."}',
        )
        self.step_results = list(step_results or [])
        self.chat_calls: list[str | None] = []
        self.step_calls: list[str] = []

    async def chat(self, user_input: str | None) -> ParsedSimulatorResponse:
        """Record the chat input and return the configured opening response."""
        self.chat_calls.append(user_input)
        return self.opening

    async def step(self, user_input: str) -> SimulatorTurnResult:
        """Record the step input and return the next queued simulator result."""
        self.step_calls.append(user_input)
        if not self.step_results:
            raise AssertionError(f"No stubbed step result available for {user_input!r}")
        return self.step_results.pop(0)


def _make_character(hid: str, *, is_human: bool = True, common_labels: list[str] | None = None) -> CharacterRecord:
    return CharacterRecord(
        hid=hid,
        name=f"{hid} Name",
        short_description=f"{hid} short description",
        data={
            "abilities": ["observe carefully", "move deliberately"],
            "long_description": f"{hid} long description.",
            "scenarios": ["A lab bench", "A quiet corridor"],
            "is_human": is_human,
            "common_labels": common_labels or ["neurotypical"],
        },
    )


@pytest.fixture
def pc() -> CharacterRecord:
    """Return a representative player character for base Game tests."""
    return _make_character("NA", is_human=True, common_labels=["neurotypical"])


@pytest.fixture
def npc() -> CharacterRecord:
    """Return a representative NPC for base Game tests."""
    return _make_character("FW", is_human=False, common_labels=["hypervigilance"])


def _ok_turn(content: str = "The flatworm moves slowly across the surface.") -> SimulatorTurnResult:
    return SimulatorTurnResult(
        ok=True,
        simulator_response=content,
        updater_result=SimulatorComponentResult(
            name="updater",
            content=content,
            ok=True,
            metadata={"scene_state": "stable"},
            raw_response='{"type":"ai","content":"ok"}',
        ),
    )


def _invalid_turn(message: str = "That action does not fit the situation.") -> SimulatorTurnResult:
    return SimulatorTurnResult(
        ok=False,
        error_message=message,
        updater_result=SimulatorComponentResult(
            name="updater",
            content="",
            ok=False,
            metadata={},
            raw_response='{"type":"error","content":"invalid"}',
        ),
    )


async def _drain(game: ExploreGame, user_input: str | None = None) -> list[GameEvent]:
    return [event async for event in game.step(user_input)]


def test_game_is_abstract() -> None:
    """Game cannot be instantiated directly because it is abstract."""
    with pytest.raises(TypeError):
        Game()  # type: ignore[abstract]


def test_explore_parse_overrides_accepts_common_base_fields() -> None:
    """ExploreGame accepts the base override contract it inherits from Game."""
    overrides = ExploreGame.parse_overrides(
        {
            "max_turns": 10,
            "max_playtime": 300,
            "player_retry_budget": 4,
            "max_input_length": 120,
            "pcs_allowed": "human-normative",
            "npcs_allowed": "hypersensitive",
        }
    )

    assert overrides.max_turns == 10
    assert overrides.max_playtime == 300
    assert overrides.player_retry_budget == 4
    assert overrides.max_input_length == 120
    assert overrides.pcs_allowed == "human-normative"
    assert overrides.npcs_allowed == "hypersensitive"


def test_explore_parse_overrides_rejects_unknown_fields() -> None:
    """ExploreGame forbids undeclared override keys."""
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ExploreGame.parse_overrides({"not_a_real_field": "value"})


def test_explore_create_from_context_uses_default_base_configuration(pc: CharacterRecord, npc: CharacterRecord) -> None:
    """ExploreGame wires default base Game configuration through create_from_context()."""
    game = ExploreGame.create_from_context(pc, npc)

    assert isinstance(game._engine, SimulatorClient)
    assert game._player_retry_budget == ExploreGame.DEFAULT_PLAYER_RETRY_BUDGET
    assert game._max_input_length == ExploreGame.DEFAULT_MAX_INPUT_LENGTH
    assert game._pcs_allowed.name == "pc-eligible"
    assert game._npcs_allowed.name == "all"
    assert game.exited is False
    assert game.exit_reason == ""
    assert game.get_transcript() == ""


def test_explore_create_from_context_applies_each_supported_base_override(pc: CharacterRecord, npc: CharacterRecord) -> None:
    """ExploreGame applies all current base-level override values it customizes."""
    game = ExploreGame.create_from_context(
        pc,
        npc,
        player_retry_budget=3,
        max_input_length=80,
        pcs_allowed="human-normative",
        npcs_allowed="hypersensitive",
    )

    assert game._player_retry_budget == 3
    assert game._max_input_length == 80
    assert game._pcs_allowed.name == "human-normative"
    assert game._npcs_allowed.name == "hypersensitive"


def test_explore_create_from_context_rejects_unknown_kwargs(pc: CharacterRecord, npc: CharacterRecord) -> None:
    """create_from_context() still validates kwargs through ExploreGame.Overrides."""
    with pytest.raises(ValidationError):
        ExploreGame.create_from_context(pc, npc, not_a_valid_kwarg=True)


def test_explore_parse_overrides_rejects_numeric_values_outside_allowed_range() -> None:
    """Shared numeric override bounds are enforced during parse_overrides()."""
    with pytest.raises(ValueError, match=r"max_turns"):
        ExploreGame.parse_overrides({"max_turns": 1_000_000})


def test_explore_create_from_context_rejects_invalid_shared_override_values(
    pc: CharacterRecord,
    npc: CharacterRecord,
) -> None:
    """create_from_context() routes through parse_overrides() for shared bound checks."""
    with pytest.raises(ValueError, match=r"max_turns"):
        ExploreGame.create_from_context(pc, npc, max_turns=1_000_000)


def test_game_subclass_rejects_widened_numeric_range() -> None:
    """Child classes cannot widen numeric bounds beyond the parent range."""
    with pytest.raises(TypeError, match=r"ALLOWED_MAX_TURNS_RANGE"):

        class InvalidWidenedRangeGame(ExploreGame):
            GAME_NAME = "Invalid Widened Range"
            GAME_DESCRIPTION = "Should fail during class creation."
            ALLOWED_MAX_TURNS_RANGE = (0, 500)


def test_game_subclass_rejects_widened_filter_set() -> None:
    """Child classes cannot add filter names that the parent disallows."""

    class RestrictedExploreGame(ExploreGame):
        GAME_NAME = "Restricted Explore"
        GAME_DESCRIPTION = "Narrows the allowed PC filters."
        ALLOWED_PCS = frozenset({"human-normative"})
        DEFAULT_PCS_FILTER = get_character_filter("human-normative")

    with pytest.raises(TypeError, match=r"ALLOWED_PCS"):

        class InvalidWidenedFilterGame(RestrictedExploreGame):
            GAME_NAME = "Invalid Widened Filter"
            GAME_DESCRIPTION = "Should fail during class creation."
            ALLOWED_PCS = frozenset({"human-normative", "all"})


def test_game_subclass_rejects_default_outside_its_own_range() -> None:
    """Child defaults must fall inside the child range they declare."""
    with pytest.raises(TypeError, match=r"DEFAULT_MAX_INPUT_LENGTH"):

        class InvalidDefaultGame(ExploreGame):
            GAME_NAME = "Invalid Default"
            GAME_DESCRIPTION = "Should fail during class creation."
            ALLOWED_MAX_INPUT_LENGTH_RANGE = (1, 100)
            DEFAULT_MAX_INPUT_LENGTH = 101


def test_game_subclass_accepts_narrower_bounds_and_defaults() -> None:
    """Child classes may narrow allowed values when defaults stay inside them."""

    class NarrowedGame(ExploreGame):
        GAME_NAME = "Narrowed"
        GAME_DESCRIPTION = "Valid narrowed bounds."
        ALLOWED_MAX_TURNS_RANGE = (10, 20)
        DEFAULT_MAX_TURNS = 12
        ALLOWED_PCS = frozenset({"human-normative"})
        DEFAULT_PCS_FILTER = get_character_filter("human-normative")

    overrides = NarrowedGame.parse_overrides({"max_turns": 20, "pcs_allowed": "human-normative"})

    assert overrides.max_turns == 20
    assert overrides.pcs_allowed == "human-normative"


def test_game_parse_overrides_rejects_disallowed_known_filter_name() -> None:
    """Known registry filters are rejected when the game narrows its allowed set."""

    class RestrictedFilterGame(ExploreGame):
        GAME_NAME = "Restricted Filter"
        GAME_DESCRIPTION = "Only allows one PC filter."
        ALLOWED_PCS = frozenset({"human-normative"})
        DEFAULT_PCS_FILTER = get_character_filter("human-normative")

    with pytest.raises(ValueError, match=r"pcs_allowed"):
        RestrictedFilterGame.parse_overrides({"pcs_allowed": "all"})


@pytest.mark.parametrize(
    "game_cls",
    [ExploreGame, InferIntentGame, ForesightGame, GoalHorizonGame, TeamworkGame],
)
def test_shipped_game_classes_load_with_valid_bounds(game_cls: type[Game]) -> None:
    """Importing each shipped game class should succeed with valid bound metadata."""
    assert issubclass(game_cls, Game)
    assert isinstance(game_cls.ALLOWED_PCS, frozenset)
    assert isinstance(game_cls.ALLOWED_NPCS, frozenset)
    assert getattr(game_cls.DEFAULT_PCS_FILTER, "name", "")
    assert getattr(game_cls.DEFAULT_NPCS_FILTER, "name", "")


async def test_explore_step_enter_flow_emits_setup_and_opening(pc: CharacterRecord, npc: CharacterRecord) -> None:
    """First step yields setup info, then opening AI content, and records opening transcript only once."""
    engine = StubEngine()
    game = ExploreGame(pc=pc, npc=npc, engine=engine)

    events = await _drain(game)

    assert [event.type for event in events] == ["info", "ai"]
    assert events[0].content == game.get_help_content()
    assert events[1].content == "The room hums quietly around you."
    assert engine.chat_calls == [None]
    assert game.get_transcript() == "Opening scene: The room hums quietly around you."


async def test_explore_step_help_abilities_and_finish_are_command_responses(pc: CharacterRecord, npc: CharacterRecord) -> None:
    """ExploreGame uses the base command routing for help, abilities, and finish."""
    engine = StubEngine()
    game = ExploreGame(pc=pc, npc=npc, engine=engine)
    await _drain(game)

    help_events = await _drain(game, "/help")
    abilities_events = await _drain(game, "/abilities")
    finish_events = await _drain(game, "/finish")

    assert len(help_events) == 1
    assert help_events[0].type == "info"
    assert help_events[0].command_response is True
    assert "Player Character" in help_events[0].content

    assert len(abilities_events) == 1
    assert abilities_events[0].type == "info"
    assert abilities_events[0].command_response is True
    assert "Abilities" in abilities_events[0].content

    assert len(finish_events) == 1
    assert finish_events[0].type == "info"
    assert finish_events[0].command_response is True
    assert game.exited is True
    assert game.exit_reason == "player finished"


async def test_explore_step_empty_input_after_enter_is_no_op(pc: CharacterRecord, npc: CharacterRecord) -> None:
    """Empty input after the initial enter step should not advance the game."""
    engine = StubEngine()
    game = ExploreGame(pc=pc, npc=npc, engine=engine)
    await _drain(game)

    events = await _drain(game, "")

    assert events == []
    assert engine.step_calls == []


async def test_explore_step_overlong_input_returns_error_without_engine_call(pc: CharacterRecord, npc: CharacterRecord) -> None:
    """The base max-input-length guard should reject the turn before engine.step()."""
    engine = StubEngine(step_results=[_ok_turn()])
    game = ExploreGame(pc=pc, npc=npc, engine=engine, max_input_length=5)
    await _drain(game)

    events = await _drain(game, "too long")

    assert len(events) == 1
    assert events[0].type == "error"
    assert "maximum length of 5" in events[0].content
    assert engine.step_calls == []
    assert game.exited is False


async def test_explore_step_failed_validation_exhausts_retry_budget(pc: CharacterRecord, npc: CharacterRecord) -> None:
    """Repeated invalid turns should decrement the retry budget and then exit the game."""
    engine = StubEngine(step_results=[_invalid_turn("Try something else."), _invalid_turn("Still invalid.")])
    game = ExploreGame(pc=pc, npc=npc, engine=engine, player_retry_budget=2)
    await _drain(game)

    first_events = await _drain(game, "bad action")
    second_events = await _drain(game, "bad action again")

    assert [event.type for event in first_events] == ["error"]
    assert first_events[0].content == "Try something else."
    assert [event.type for event in second_events] == ["error", "info"]
    assert second_events[0].content == "Still invalid."
    assert "allowed retries" in second_events[1].content
    assert game.exited is True
    assert game.exit_reason == "retry budget exhausted"
    assert game._player_retry_budget == 0
    assert engine.step_calls == ["bad action", "bad action again"]


async def test_explore_transcript_includes_only_opening_and_successful_turns(pc: CharacterRecord, npc: CharacterRecord) -> None:
    """Filtered transcript should exclude commands and rejected turns."""
    engine = StubEngine(step_results=[_invalid_turn("Nope."), _ok_turn("The flatworm pivots toward the light.")])
    game = ExploreGame(pc=pc, npc=npc, engine=engine, max_input_length=5, player_retry_budget=2)

    await _drain(game)
    await _drain(game, "/help")
    await _drain(game, "too long")
    await _drain(game, "bad")
    await _drain(game, "okay")
    await _drain(game, "/abilities")
    await _drain(game, "/finish")

    transcript = game.get_transcript()

    assert "Opening scene: The room hums quietly around you." in transcript
    assert f"Player ({pc.hid}): okay" in transcript
    assert "Simulator: The flatworm pivots toward the light." in transcript
    assert "/help" not in transcript
    assert "/abilities" not in transcript
    assert "too long" not in transcript
    assert "bad" not in transcript
    assert "Nope." not in transcript


async def test_explore_step_is_no_op_after_exit(pc: CharacterRecord, npc: CharacterRecord) -> None:
    """Once ExploreGame exits, subsequent steps should yield nothing."""
    engine = StubEngine(step_results=[_ok_turn()])
    game = ExploreGame(pc=pc, npc=npc, engine=engine)
    await _drain(game)
    await _drain(game, "/finish")

    events = await _drain(game, "I keep walking")

    assert events == []
    assert engine.step_calls == []
