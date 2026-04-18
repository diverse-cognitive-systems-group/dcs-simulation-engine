"""Unit tests for concrete character filter implementations."""

import pytest
from dcs_simulation_engine.dal.base import CharacterRecord
from dcs_simulation_engine.dal.character_filters import get_character_filter
from dcs_simulation_engine.dal.character_filters.all import AllCharactersFilter
from dcs_simulation_engine.dal.character_filters.human_normative import HumanNormativeFilter
from dcs_simulation_engine.dal.character_filters.hypersensitive import HypersensitiveFilter
from dcs_simulation_engine.dal.character_filters.hyposensitive import HyposensitiveFilter
from dcs_simulation_engine.dal.character_filters.neurotypical import NeurotypicalFilter


class StubProvider:
    """Minimal provider stub exposing the characters API used by filters."""

    def __init__(self, characters: list[CharacterRecord]) -> None:
        """Store the character records returned by this provider stub."""
        self._characters = characters

    def get_characters(self) -> list[CharacterRecord]:
        """Return a copy of the configured character list."""
        return list(self._characters)


def _character(
    hid: str,
    *,
    is_human: bool,
    common_labels: list[str],
) -> CharacterRecord:
    return CharacterRecord(
        hid=hid,
        name=f"{hid} Name",
        short_description=f"{hid} short description",
        data={
            "is_human": is_human,
            "common_labels": common_labels,
        },
    )


@pytest.fixture
def provider() -> StubProvider:
    """Return a mixed character set that exercises each concrete filter."""
    return StubProvider(
        [
            _character("NA", is_human=True, common_labels=["neurotypical"]),
            _character("BC", is_human=False, common_labels=["neurotypical"]),
            _character("WS", is_human=True, common_labels=["anxiety", "hypervigilance"]),
            _character("KAT", is_human=True, common_labels=["ADHD"]),
            _character("GEN", is_human=True, common_labels=["other"]),
        ]
    )


@pytest.mark.unit
def test_all_characters_filter_returns_every_character(provider: StubProvider) -> None:
    """The all filter should return every character in provider order."""
    result = AllCharactersFilter().get_characters(provider=provider)
    assert [character.hid for character in result] == ["NA", "BC", "WS", "KAT", "GEN"]


@pytest.mark.unit
def test_human_normative_filter_returns_only_human_neurotypical_characters(provider: StubProvider) -> None:
    """human-normative should require both is_human and neurotypical labeling."""
    result = HumanNormativeFilter().get_characters(provider=provider)
    assert [character.hid for character in result] == ["NA"]


@pytest.mark.unit
def test_neurotypical_filter_returns_any_neurotypical_character(provider: StubProvider) -> None:
    """Neurotypical should include both human and non-human neurotypical characters."""
    result = NeurotypicalFilter().get_characters(provider=provider)
    assert [character.hid for character in result] == ["NA", "BC"]


@pytest.mark.unit
def test_hypersensitive_filter_matches_any_configured_hypersensitive_label(provider: StubProvider) -> None:
    """Hypersensitive should match characters whose labels overlap the hypersensitive set."""
    result = HypersensitiveFilter().get_characters(provider=provider)
    assert [character.hid for character in result] == ["WS"]


@pytest.mark.unit
def test_hyposensitive_filter_matches_any_configured_hyposensitive_label(provider: StubProvider) -> None:
    """Hyposensitive should match characters whose labels overlap the hyposensitive set."""
    result = HyposensitiveFilter().get_characters(provider=provider)
    assert [character.hid for character in result] == ["KAT"]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("name", "expected_type"),
    [
        ("all", AllCharactersFilter),
        ("human-normative", HumanNormativeFilter),
        ("neurotypical", NeurotypicalFilter),
        ("hypersensitive", HypersensitiveFilter),
        ("hyposensitive", HyposensitiveFilter),
    ],
)
def test_get_character_filter_resolves_registered_filters(name: str, expected_type: type) -> None:
    """Registry lookup should return the concrete filter registered under each name."""
    filter_instance = get_character_filter(name)
    assert isinstance(filter_instance, expected_type)
    assert filter_instance.name == name


@pytest.mark.unit
def test_get_character_filter_rejects_unknown_name() -> None:
    """Registry lookup should fail with a helpful error for unknown filters."""
    with pytest.raises(ValueError, match="Unknown character filter"):
        get_character_filter("not-a-real-filter")
