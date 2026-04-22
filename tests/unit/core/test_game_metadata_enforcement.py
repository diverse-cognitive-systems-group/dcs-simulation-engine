"""Tests for Game class metadata enforcement."""

import pytest
from dcs_simulation_engine.core.game import BaseGameOverrides, Game


class TestGameMetadataEnforcement:
    """Test suite for GAME_NAME and GAME_DESCRIPTION enforcement."""

    def test_game_name_and_description_required(self) -> None:
        """Test that a concrete game subclass must define GAME_NAME and GAME_DESCRIPTION."""
        with pytest.raises(TypeError, match="TestGame must define non-empty GAME_NAME class attribute"):

            class TestGame(Game):
                GAME_DESCRIPTION = "A test game"

                class Overrides(BaseGameOverrides):
                    pass

    def test_missing_game_name(self) -> None:
        """Test that missing GAME_NAME raises TypeError."""
        with pytest.raises(TypeError, match="must define non-empty GAME_NAME"):

            class IncompleteGame(Game):
                GAME_DESCRIPTION = "A game without a name"

                class Overrides(BaseGameOverrides):
                    pass

    def test_missing_game_description(self) -> None:
        """Test that missing GAME_DESCRIPTION raises TypeError."""
        with pytest.raises(TypeError, match="must define non-empty GAME_DESCRIPTION"):

            class IncompleteGame(Game):
                GAME_NAME = "Incomplete Game"

                class Overrides(BaseGameOverrides):
                    pass

    def test_empty_game_name(self) -> None:
        """Test that empty GAME_NAME raises TypeError."""
        with pytest.raises(TypeError, match="must define non-empty GAME_NAME"):

            class EmptyNameGame(Game):
                GAME_NAME = ""
                GAME_DESCRIPTION = "A game with empty name"

                class Overrides(BaseGameOverrides):
                    pass

    def test_empty_game_description(self) -> None:
        """Test that empty GAME_DESCRIPTION raises TypeError."""
        with pytest.raises(TypeError, match="must define non-empty GAME_DESCRIPTION"):

            class EmptyDescGame(Game):
                GAME_NAME = "Empty Desc Game"
                GAME_DESCRIPTION = ""

                class Overrides(BaseGameOverrides):
                    pass

    def test_whitespace_only_game_name(self) -> None:
        """Test that whitespace-only GAME_NAME raises TypeError."""
        with pytest.raises(TypeError, match="must define non-empty GAME_NAME"):

            class WhitespaceNameGame(Game):
                GAME_NAME = "   "
                GAME_DESCRIPTION = "A game with whitespace name"

                class Overrides(BaseGameOverrides):
                    pass

    def test_whitespace_only_game_description(self) -> None:
        """Test that whitespace-only GAME_DESCRIPTION raises TypeError."""
        with pytest.raises(TypeError, match="must define non-empty GAME_DESCRIPTION"):

            class WhitespaceDescGame(Game):
                GAME_NAME = "Whitespace Desc Game"
                GAME_DESCRIPTION = "\t\n  "

                class Overrides(BaseGameOverrides):
                    pass

    def test_non_string_game_name(self) -> None:
        """Test that non-string GAME_NAME raises TypeError."""
        with pytest.raises(TypeError, match="must define non-empty GAME_NAME"):

            class NonStringNameGame(Game):
                GAME_NAME = 123  # type: ignore
                GAME_DESCRIPTION = "A game with non-string name"

                class Overrides(BaseGameOverrides):
                    pass

    def test_non_string_game_description(self) -> None:
        """Test that non-string GAME_DESCRIPTION raises TypeError."""
        with pytest.raises(TypeError, match="must define non-empty GAME_DESCRIPTION"):

            class NonStringDescGame(Game):
                GAME_NAME = "Non String Desc Game"
                GAME_DESCRIPTION = ["list", "of", "strings"]  # type: ignore

                class Overrides(BaseGameOverrides):
                    pass

    def test_valid_concrete_game(self) -> None:
        """Test that a properly-defined concrete game class is accepted."""

        # This should not raise any exception
        class ValidGame(Game):
            GAME_NAME = "Valid Game"
            GAME_DESCRIPTION = "A properly defined game"

            class Overrides(BaseGameOverrides):
                pass

            def get_help_content(self) -> str:
                return "Help"

            def get_abilities_content(self) -> str:
                return "Abilities"

            async def on_finish(self):
                return
                yield

            @classmethod
            def create_from_context(cls, pc, npc, **kwargs):
                return cls(
                    pc=pc,
                    npc=npc,
                    engine=None,
                )

        assert ValidGame.GAME_NAME == "Valid Game"
        assert ValidGame.GAME_DESCRIPTION == "A properly defined game"

    def test_valid_game_with_special_characters(self) -> None:
        """Test that game names/descriptions with special characters are accepted."""

        class SpecialCharGame(Game):
            GAME_NAME = "Game: The Sequel! (v2.0)"
            GAME_DESCRIPTION = "A game with special chars: @#$%^&*()"

            class Overrides(BaseGameOverrides):
                pass

            def get_help_content(self) -> str:
                return "Help"

            def get_abilities_content(self) -> str:
                return "Abilities"

            async def on_finish(self):
                return
                yield

            @classmethod
            def create_from_context(cls, pc, npc, **kwargs):
                return cls(
                    pc=pc,
                    npc=npc,
                    engine=None,
                )

        assert "Sequel!" in SpecialCharGame.GAME_NAME
        assert "@#$" in SpecialCharGame.GAME_DESCRIPTION
