"""Tests for game Overrides models and updated create_from_context()."""

import pytest
from dcs_simulation_engine.core.game import BaseGameOverrides, Game
from dcs_simulation_engine.dal.base import CharacterRecord
from dcs_simulation_engine.games.explore import ExploreGame
from dcs_simulation_engine.games.foresight import ForesightGame
from dcs_simulation_engine.games.goal_horizon import GoalHorizonGame
from dcs_simulation_engine.games.infer_intent import InferIntentGame
from dcs_simulation_engine.games.teamwork import TeamworkGame
from pydantic import ValidationError

pytestmark = [pytest.mark.unit]

ALL_GAME_CLASSES = [ExploreGame, ForesightGame, GoalHorizonGame, InferIntentGame, TeamworkGame]


def test_game_is_abstract() -> None:
    """Game cannot be instantiated directly because it is abstract."""
    with pytest.raises(TypeError):
        Game()  # type: ignore[abstract]


@pytest.mark.parametrize("cls", ALL_GAME_CLASSES)
def test_game_class_metadata_present(cls) -> None:
    """Every game class exposes GAME_NAME, GAME_DESCRIPTION."""
    assert isinstance(cls.GAME_NAME, str) and cls.GAME_NAME
    assert isinstance(cls.GAME_DESCRIPTION, str) and cls.GAME_DESCRIPTION


def test_game_metadata_values() -> None:
    """Spot-check a few canonical metadata values."""
    assert ExploreGame.GAME_NAME == "Explore"
    assert InferIntentGame.GAME_NAME == "Infer Intent"
    assert ForesightGame.GAME_NAME == "Foresight"
    assert GoalHorizonGame.GAME_NAME == "Goal Horizon"
    assert TeamworkGame.GAME_NAME == "Teamwork"


@pytest.mark.parametrize("cls", ALL_GAME_CLASSES)
def test_parse_overrides_empty_dict(cls) -> None:
    """Empty dict should parse to defaults without error."""
    overrides = cls.parse_overrides({})
    assert isinstance(overrides, BaseGameOverrides)


@pytest.mark.parametrize("cls", ALL_GAME_CLASSES)
def test_parse_overrides_common_fields(cls) -> None:
    """Common BaseGameOverrides fields are accepted by every game."""
    raw = {
        "max_turns": 10,
        "max_playtime": 300,
    }
    overrides = cls.parse_overrides(raw)
    assert overrides.max_turns == 10
    assert overrides.max_playtime == 300


def test_parse_overrides_explore_retry_budget() -> None:
    """ExploreGame.Overrides accepts player_retry_budget."""
    overrides = ExploreGame.parse_overrides({"player_retry_budget": 5})
    assert overrides.player_retry_budget == 5


def test_parse_overrides_foresight_game_specific_fields() -> None:
    """ForesightGame.Overrides accepts max_predictions and min_predictions."""
    overrides = ForesightGame.parse_overrides({"max_predictions": 5, "min_predictions": 2})
    assert overrides.max_predictions == 5
    assert overrides.min_predictions == 2


@pytest.mark.parametrize("cls", ALL_GAME_CLASSES)
def test_parse_overrides_unknown_key_rejected(cls) -> None:
    """Unknown kwargs raise ValidationError because Overrides uses extra='forbid'."""
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        cls.parse_overrides({"not_a_real_field": "value"})


def test_parse_overrides_explore_rejects_foresight_field() -> None:
    """ExploreGame.Overrides rejects ForesightGame-specific fields."""
    with pytest.raises(ValidationError):
        ExploreGame.parse_overrides({"max_predictions": 5})


@pytest.fixture
def mock_character() -> CharacterRecord:
    """Return a minimal CharacterRecord with the fields used by prompt rendering."""
    return CharacterRecord(
        hid="test-char",
        name="Test Character",
        short_description="A test character",
        data={
            "abilities": ["can walk", "can speak"],
            "long_description": "A detailed character description.",
            "scenarios": ["A quiet room", "A busy hallway"],
        },
    )


def test_explore_create_custom_retry_budget(mock_character) -> None:
    """ExploreGame built with player_retry_budget override uses that value."""
    game = ExploreGame.create_from_context(mock_character, mock_character, player_retry_budget=3)
    assert game._retry_budget == 3


def test_explore_create_default_retry_budget(mock_character) -> None:
    """ExploreGame built with no overrides uses the Overrides model default (10)."""
    game = ExploreGame.create_from_context(mock_character, mock_character)
    assert game._retry_budget == ExploreGame.Overrides().player_retry_budget


def test_infer_intent_create_default_retry_budget(mock_character) -> None:
    """InferIntentGame default retry budget is 3 (as declared in Overrides)."""
    game = InferIntentGame.create_from_context(mock_character, mock_character)
    assert game._retry_budget == InferIntentGame.Overrides().player_retry_budget
    assert game._retry_budget == 3


def test_explore_create_unknown_kwarg_rejected(mock_character) -> None:
    """create_from_context() rejects unknown kwargs via Overrides validation."""
    with pytest.raises(ValidationError):
        ExploreGame.create_from_context(mock_character, mock_character, not_a_valid_kwarg=True)
