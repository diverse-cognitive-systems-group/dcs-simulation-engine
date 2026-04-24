"""Tests for canonical candidate-based assignment strategies."""

from pathlib import Path
from typing import Any

import pytest
from dcs_simulation_engine.core.assignment_strategies import get_assignment_strategy
from dcs_simulation_engine.core.assignment_strategies.common import CandidateAssignmentStrategy
from dcs_simulation_engine.core.experiment_config import ExperimentConfig
from dcs_simulation_engine.core.session_manager import SessionManager
from dcs_simulation_engine.dal.mongo.const import MongoColumns

pytestmark = [pytest.mark.unit, pytest.mark.anyio]


class _StubGameConfig:
    def __init__(self, *, pcs: list[str], npcs: list[str]) -> None:
        self._pcs = pcs
        self._npcs = npcs

    async def get_valid_characters_async(self, **_kwargs):
        return ([(hid, hid) for hid in self._pcs], [(hid, hid) for hid in self._npcs])


def _load_strategy_config(
    write_yaml,
    *,
    strategy: str,
    name: str,
    games: list[str] | None = None,
    assignment_mode: str = "auto",
    max_assignments_per_player: int = 3,
) -> ExperimentConfig:
    games_yaml = "\n".join(f"    - {game}" for game in (games or ["Explore", "Foresight"]))
    path = write_yaml(
        f"{name}.yaml",
        "\n".join(
            [
                f"name: {name}",
                "description: Strategy test fixture",
                "assignment_strategy:",
                f"  strategy: {strategy}",
                "  games:",
                games_yaml,
                "  quota_per_game: 10",
                f"  max_assignments_per_player: {max_assignments_per_player}",
                f"  assignment_mode: {assignment_mode}",
                f"  seed: {name}-seed",
            ]
        )
        + "\n",
    )
    return ExperimentConfig.load(Path(path))


async def _seed_characters(provider) -> None:
    profiles = {
        "normative": {
            "physical_ability_assumptions": {"vision": {"value": "normative"}},
            "social_and_communicative_assumptions": {"communication": {"value": "normative"}},
        },
        "mild": {
            "physical_ability_assumptions": {"vision": {"value": "divergent"}},
            "social_and_communicative_assumptions": {"communication": {"value": "normative"}},
        },
        "strong": {
            "physical_ability_assumptions": {"vision": {"value": "divergent"}},
            "social_and_communicative_assumptions": {"communication": {"value": "divergent"}},
        },
    }
    records = [
        ("pc-alpha", ["generalist"], profiles["normative"]),
        ("pc-beta", ["generalist"], profiles["mild"]),
        ("npc-research", ["researcher"], profiles["normative"]),
        ("npc-support", ["helper"], profiles["mild"]),
        ("npc-strong", ["other"], profiles["strong"]),
    ]
    for hid, labels, profile in records:
        await provider.upsert_character(
            {
                "hid": hid,
                "name": hid,
                "short_description": hid,
                "common_labels": labels,
                "hsn_divergence": profile,
                "pc_eligible": hid.startswith("pc-"),
            },
            character_id=hid,
        )


def _patch_game_configs(monkeypatch: pytest.MonkeyPatch, game_map: dict[str, tuple[list[str], list[str]]]) -> None:
    def _get_game_config(game_name: str) -> _StubGameConfig:
        pcs, npcs = game_map[game_name]
        return _StubGameConfig(pcs=pcs, npcs=npcs)

    monkeypatch.setattr(SessionManager, "get_game_config_cached", _get_game_config)


def _patch_auto_pick_first(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        CandidateAssignmentStrategy,
        "_select_auto_candidate",
        lambda self, *, config, player, candidates: candidates[0],
    )


async def _create_assignment(
    provider,
    *,
    experiment_name: str,
    player_id: str,
    game_name: str,
    pc_hid: str,
    npc_hid: str,
    status: str = "completed",
    metadata: dict[str, Any] | None = None,
) -> None:
    assignment_doc = {
        MongoColumns.EXPERIMENT_NAME: experiment_name,
        MongoColumns.PLAYER_ID: player_id,
        MongoColumns.GAME_NAME: game_name,
        MongoColumns.PC_HID: pc_hid,
        MongoColumns.NPC_HID: npc_hid,
        MongoColumns.FORM_RESPONSES: {},
    }
    if metadata:
        assignment_doc.update(metadata)
    assignment = await provider.create_assignment(assignment_doc=assignment_doc, allow_concurrent=True)
    await provider.update_assignment_status(assignment_id=assignment.assignment_id, status=status)


class _StrategyTestBase:
    strategy_id = ""

    def _assert_missing_games(self, write_yaml) -> None:
        path = write_yaml(
            f"missing-{self.strategy_id}.yaml",
            "\n".join(
                [
                    f"name: missing-{self.strategy_id}",
                    "description: Missing games",
                    "assignment_strategy:",
                    f"  strategy: {self.strategy_id}",
                    "  quota_per_game: 10",
                ]
            )
            + "\n",
        )
        with pytest.raises(ValueError, match="games"):
            ExperimentConfig.load(Path(path))


class TestFullCharacterAccess(_StrategyTestBase):
    """Behavioral tests for the full-character-access strategy."""

    strategy_id = "full_character_access"

    def test_validate_config_requires_games(self, write_yaml) -> None:
        """The strategy should reject configs that omit the game list."""
        self._assert_missing_games(write_yaml)

    async def test_get_or_create_assignment_async_returns_expected_assignment(self, async_mongo_provider, write_yaml, monkeypatch) -> None:
        """The strategy should create and then reuse the first deterministic candidate."""
        _patch_auto_pick_first(monkeypatch)
        _patch_game_configs(monkeypatch, {"Explore": (["pc-alpha"], ["npc-research", "npc-support"]), "Foresight": (["pc-beta"], ["npc-support"])})
        await _seed_characters(async_mongo_provider)
        config = _load_strategy_config(write_yaml, strategy=self.strategy_id, name="full-character")
        player, _ = await async_mongo_provider.create_player(player_data={"full_name": {"answer": "A"}})
        strategy = get_assignment_strategy(self.strategy_id)

        first = await strategy.get_or_create_assignment_async(provider=async_mongo_provider, config=config, player=player)
        second = await strategy.get_or_create_assignment_async(provider=async_mongo_provider, config=config, player=player)

        assert first is not None
        assert first.game_name == "Explore"
        assert first.pc_hid == "pc-alpha"
        assert first.npc_hid == "npc-research"
        assert second is not None
        assert second.assignment_id == first.assignment_id


class TestUnplayedCombinationChoice(_StrategyTestBase):
    """Behavioral tests for the unplayed-combination-choice strategy."""

    strategy_id = "unplayed_combination_choice"

    def test_validate_config_requires_games(self, write_yaml) -> None:
        """The strategy should reject configs that omit the game list."""
        self._assert_missing_games(write_yaml)

    async def test_get_or_create_assignment_async_returns_expected_assignment(self, async_mongo_provider, write_yaml, monkeypatch) -> None:
        """The strategy should prioritize triples the player has not completed yet."""
        _patch_auto_pick_first(monkeypatch)
        _patch_game_configs(monkeypatch, {"Explore": (["pc-alpha"], ["npc-research", "npc-support"]), "Foresight": (["pc-beta"], ["npc-support"])})
        await _seed_characters(async_mongo_provider)
        config = _load_strategy_config(write_yaml, strategy=self.strategy_id, name="unplayed")
        player, _ = await async_mongo_provider.create_player(player_data={"full_name": {"answer": "A"}})
        await _create_assignment(
            async_mongo_provider,
            experiment_name=config.name,
            player_id=player.id,
            game_name="Explore",
            pc_hid="pc-alpha",
            npc_hid="npc-research",
        )
        strategy = get_assignment_strategy(self.strategy_id)

        first = await strategy.get_or_create_assignment_async(provider=async_mongo_provider, config=config, player=player)
        second = await strategy.get_or_create_assignment_async(provider=async_mongo_provider, config=config, player=player)

        assert first is not None
        assert first.npc_hid == "npc-support"
        assert second is not None
        assert second.assignment_id == first.assignment_id


class TestExpertiseMatchedCharacterChoice(_StrategyTestBase):
    """Behavioral tests for the expertise-matched-character-choice strategy."""

    strategy_id = "expertise_matched_character_choice"

    def test_validate_config_requires_games(self, write_yaml) -> None:
        """The strategy should reject configs that omit the game list."""
        self._assert_missing_games(write_yaml)

    async def test_get_or_create_assignment_async_returns_expected_assignment(self, async_mongo_provider, write_yaml, monkeypatch) -> None:
        """The strategy should prioritize NPCs that match the player's expertise."""
        _patch_auto_pick_first(monkeypatch)
        _patch_game_configs(monkeypatch, {"Explore": (["pc-alpha"], ["npc-support", "npc-research"]), "Foresight": (["pc-beta"], ["npc-support"])})
        await _seed_characters(async_mongo_provider)
        config = _load_strategy_config(write_yaml, strategy=self.strategy_id, name="expertise-choice")
        player, _ = await async_mongo_provider.create_player(
            player_data={"full_name": {"answer": "A"}, "expertise": "researcher"}
        )
        strategy = get_assignment_strategy(self.strategy_id)

        first = await strategy.get_or_create_assignment_async(provider=async_mongo_provider, config=config, player=player)
        second = await strategy.get_or_create_assignment_async(provider=async_mongo_provider, config=config, player=player)

        assert first is not None
        assert first.npc_hid == "npc-research"
        assert second is not None
        assert second.assignment_id == first.assignment_id


class TestNextIncompleteCombination(_StrategyTestBase):
    """Behavioral tests for the next-incomplete-combination strategy."""

    strategy_id = "next_incomplete_combination"

    def test_validate_config_requires_games(self, write_yaml) -> None:
        """The strategy should reject configs that omit the game list."""
        self._assert_missing_games(write_yaml)

    async def test_get_or_create_assignment_async_returns_expected_assignment(self, async_mongo_provider, write_yaml, monkeypatch) -> None:
        """The strategy should pick the first incomplete game/NPC group."""
        _patch_auto_pick_first(monkeypatch)
        _patch_game_configs(monkeypatch, {"Explore": (["pc-alpha"], ["npc-research", "npc-support"]), "Foresight": (["pc-beta"], ["npc-support"])})
        await _seed_characters(async_mongo_provider)
        config = _load_strategy_config(write_yaml, strategy=self.strategy_id, name="next-incomplete")
        player, _ = await async_mongo_provider.create_player(player_data={"full_name": {"answer": "A"}})
        await _create_assignment(
            async_mongo_provider,
            experiment_name=config.name,
            player_id=player.id,
            game_name="Explore",
            pc_hid="pc-alpha",
            npc_hid="npc-research",
        )
        strategy = get_assignment_strategy(self.strategy_id)

        first = await strategy.get_or_create_assignment_async(provider=async_mongo_provider, config=config, player=player)
        second = await strategy.get_or_create_assignment_async(provider=async_mongo_provider, config=config, player=player)

        assert first is not None
        assert first.game_name == "Explore"
        assert first.npc_hid == "npc-support"
        assert second is not None
        assert second.assignment_id == first.assignment_id


class TestLeastPlayedCombinationNext(_StrategyTestBase):
    """Behavioral tests for the least-played-combination-next strategy."""

    strategy_id = "least_played_combination_next"

    def test_validate_config_requires_games(self, write_yaml) -> None:
        """The strategy should reject configs that omit the game list."""
        self._assert_missing_games(write_yaml)

    async def test_get_or_create_assignment_async_returns_expected_assignment(self, async_mongo_provider, write_yaml, monkeypatch) -> None:
        """The strategy should pick the least-played game/NPC group."""
        _patch_auto_pick_first(monkeypatch)
        _patch_game_configs(monkeypatch, {"Explore": (["pc-alpha"], ["npc-research"]), "Foresight": (["pc-beta"], ["npc-support"])})
        await _seed_characters(async_mongo_provider)
        config = _load_strategy_config(write_yaml, strategy=self.strategy_id, name="least-played")
        player, _ = await async_mongo_provider.create_player(player_data={"full_name": {"answer": "A"}})
        other, _ = await async_mongo_provider.create_player(player_data={"full_name": {"answer": "B"}})
        await _create_assignment(
            async_mongo_provider,
            experiment_name=config.name,
            player_id=other.id,
            game_name="Explore",
            pc_hid="pc-alpha",
            npc_hid="npc-research",
        )
        strategy = get_assignment_strategy(self.strategy_id)

        first = await strategy.get_or_create_assignment_async(provider=async_mongo_provider, config=config, player=player)
        second = await strategy.get_or_create_assignment_async(provider=async_mongo_provider, config=config, player=player)

        assert first is not None
        assert first.game_name == "Foresight"
        assert first.npc_hid == "npc-support"
        assert second is not None
        assert second.assignment_id == first.assignment_id


class TestProgressiveDivergenceAssignment(_StrategyTestBase):
    """Behavioral tests for the progressive-divergence strategy."""

    strategy_id = "progressive_divergence_assignment"

    def test_validate_config_requires_games(self, write_yaml) -> None:
        """The strategy should reject configs that omit the game list."""
        self._assert_missing_games(write_yaml)

    async def test_get_or_create_assignment_async_returns_expected_assignment(self, async_mongo_provider, write_yaml, monkeypatch) -> None:
        """The strategy should prefer the most divergent NPC from the last completed NPC."""
        _patch_auto_pick_first(monkeypatch)
        _patch_game_configs(monkeypatch, {"Explore": (["pc-alpha"], ["npc-support", "npc-strong"]), "Foresight": (["pc-beta"], ["npc-support"])})
        await _seed_characters(async_mongo_provider)
        config = _load_strategy_config(write_yaml, strategy=self.strategy_id, name="progressive-divergence")
        player, _ = await async_mongo_provider.create_player(player_data={"full_name": {"answer": "A"}})
        await _create_assignment(
            async_mongo_provider,
            experiment_name=config.name,
            player_id=player.id,
            game_name="Explore",
            pc_hid="pc-alpha",
            npc_hid="npc-research",
        )
        strategy = get_assignment_strategy(self.strategy_id)

        first = await strategy.get_or_create_assignment_async(provider=async_mongo_provider, config=config, player=player)
        second = await strategy.get_or_create_assignment_async(provider=async_mongo_provider, config=config, player=player)

        assert first is not None
        assert first.npc_hid == "npc-strong"
        assert second is not None
        assert second.assignment_id == first.assignment_id


class TestMaxContrastPairing(_StrategyTestBase):
    """Behavioral tests for the max-contrast-pairing strategy."""

    strategy_id = "max_contrast_pairing"

    def test_validate_config_requires_games(self, write_yaml) -> None:
        """The strategy should reject configs that omit the game list."""
        self._assert_missing_games(write_yaml)

    async def test_get_or_create_assignment_async_returns_expected_assignment(self, async_mongo_provider, write_yaml, monkeypatch) -> None:
        """The strategy should pick the PC/NPC pair with the highest contrast."""
        _patch_auto_pick_first(monkeypatch)
        _patch_game_configs(monkeypatch, {"Explore": (["pc-alpha"], ["npc-support", "npc-strong"]), "Foresight": (["pc-beta"], ["npc-support"])})
        await _seed_characters(async_mongo_provider)
        config = _load_strategy_config(write_yaml, strategy=self.strategy_id, name="max-contrast")
        player, _ = await async_mongo_provider.create_player(player_data={"full_name": {"answer": "A"}})
        strategy = get_assignment_strategy(self.strategy_id)

        first = await strategy.get_or_create_assignment_async(provider=async_mongo_provider, config=config, player=player)
        second = await strategy.get_or_create_assignment_async(provider=async_mongo_provider, config=config, player=player)

        assert first is not None
        assert first.npc_hid == "npc-strong"
        assert second is not None
        assert second.assignment_id == first.assignment_id


class TestExpertiseMatchedCharacterNext(_StrategyTestBase):
    """Behavioral tests for the expertise-matched-character-next strategy."""

    strategy_id = "expertise_matched_character_next"

    def test_validate_config_requires_games(self, write_yaml) -> None:
        """The strategy should reject configs that omit the game list."""
        self._assert_missing_games(write_yaml)

    async def test_get_or_create_assignment_async_returns_expected_assignment(self, async_mongo_provider, write_yaml, monkeypatch) -> None:
        """The strategy should auto-pick expertise-matching NPCs first."""
        _patch_auto_pick_first(monkeypatch)
        _patch_game_configs(monkeypatch, {"Explore": (["pc-alpha"], ["npc-support", "npc-research"]), "Foresight": (["pc-beta"], ["npc-support"])})
        await _seed_characters(async_mongo_provider)
        config = _load_strategy_config(write_yaml, strategy=self.strategy_id, name="expertise-next")
        player, _ = await async_mongo_provider.create_player(
            player_data={"full_name": {"answer": "A"}, "expertise": "researcher"}
        )
        strategy = get_assignment_strategy(self.strategy_id)

        first = await strategy.get_or_create_assignment_async(provider=async_mongo_provider, config=config, player=player)
        second = await strategy.get_or_create_assignment_async(provider=async_mongo_provider, config=config, player=player)

        assert first is not None
        assert first.npc_hid == "npc-research"
        assert second is not None
        assert second.assignment_id == first.assignment_id


class TestExpertiseMatchedCharacterBatch(_StrategyTestBase):
    """Behavioral tests for the expertise-matched-character-batch strategy."""

    strategy_id = "expertise_matched_character_batch"

    def test_validate_config_requires_games(self, write_yaml) -> None:
        """The strategy should reject configs that omit the game list."""
        self._assert_missing_games(write_yaml)

    async def test_get_or_create_assignment_async_returns_expected_assignment(self, async_mongo_provider, write_yaml, monkeypatch) -> None:
        """The strategy should keep the player on the same NPC batch across games."""
        _patch_auto_pick_first(monkeypatch)
        _patch_game_configs(monkeypatch, {"Explore": (["pc-alpha"], ["npc-support", "npc-research"]), "Foresight": (["pc-beta"], ["npc-support", "npc-research"])})
        await _seed_characters(async_mongo_provider)
        config = _load_strategy_config(write_yaml, strategy=self.strategy_id, name="expertise-batch")
        player, _ = await async_mongo_provider.create_player(
            player_data={"full_name": {"answer": "A"}, "expertise": "researcher"}
        )
        await _create_assignment(
            async_mongo_provider,
            experiment_name=config.name,
            player_id=player.id,
            game_name="Explore",
            pc_hid="pc-alpha",
            npc_hid="npc-research",
            metadata={"batch_id": f"{config.name}:{player.id}:npc-research", "batch_npc_hid": "npc-research"},
        )
        strategy = get_assignment_strategy(self.strategy_id)

        first = await strategy.get_or_create_assignment_async(provider=async_mongo_provider, config=config, player=player)
        second = await strategy.get_or_create_assignment_async(provider=async_mongo_provider, config=config, player=player)

        assert first is not None
        assert first.game_name == "Foresight"
        assert first.npc_hid == "npc-research"
        assert first.data["batch_npc_hid"] == "npc-research"
        assert second is not None
        assert second.assignment_id == first.assignment_id
