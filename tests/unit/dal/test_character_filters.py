"""Unit tests for concrete character filter implementations."""

import pytest
from dcs_simulation_engine.dal.base import CharacterRecord
from dcs_simulation_engine.dal.character_filters import get_character_filter
from dcs_simulation_engine.dal.character_filters.all import AllCharactersFilter
from dcs_simulation_engine.dal.character_filters.divergent import DivergentFilter
from dcs_simulation_engine.dal.character_filters.human import HumanFilter
from dcs_simulation_engine.dal.character_filters.human_normative import HumanNormativeFilter
from dcs_simulation_engine.dal.character_filters.hypersensitive import HypersensitiveFilter
from dcs_simulation_engine.dal.character_filters.hyposensitive import HyposensitiveFilter
from dcs_simulation_engine.dal.character_filters.neurodivergent import NeurodivergentFilter
from dcs_simulation_engine.dal.character_filters.neurotypical import NeurotypicalFilter
from dcs_simulation_engine.dal.character_filters.non_human import NonHumanFilter
from dcs_simulation_engine.dal.character_filters.pc_eligible import PcEligibleFilter
from dcs_simulation_engine.dal.character_filters.physical_divergence import PhysicalDivergenceFilter


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
    pc_eligible: bool = False,
    hsn_divergence: dict | None = None,
) -> CharacterRecord:
    return CharacterRecord(
        hid=hid,
        name=f"{hid} Name",
        short_description=f"{hid} short description",
        data={
            "is_human": is_human,
            "pc_eligible": pc_eligible,
            "common_labels": common_labels,
            "hsn_divergence": hsn_divergence,
        },
    )


def _normative_hsn() -> dict:
    return {
        "physical_ability_assumptions": {
            "vision": {"value": "normative"},
            "hearing": {"value": "normative"},
        },
        "cognitive_and_perceptual_assumptions": {
            "attention_control": {"value": "normative"},
            "processing_speed": {"value": "normative"},
        },
        "social_and_communicative_assumptions": {
            "neurotypical_communication": {"value": "normative"},
        },
    }


def _cognitive_divergent_hsn() -> dict:
    return {
        "physical_ability_assumptions": {
            "vision": {"value": "normative"},
        },
        "cognitive_and_perceptual_assumptions": {
            "attention_control": {"value": "divergent"},
        },
        "social_and_communicative_assumptions": {
            "neurotypical_communication": {"value": "normative"},
        },
    }


def _communication_divergent_hsn() -> dict:
    return {
        "physical_ability_assumptions": {
            "speech": {"value": "normative"},
        },
        "cognitive_and_perceptual_assumptions": {
            "attention_control": {"value": "normative"},
        },
        "social_and_communicative_assumptions": {
            "neurotypical_communication": {"value": "divergent"},
        },
    }


def _physical_divergent_hsn() -> dict:
    return {
        "physical_ability_assumptions": {
            "ambulation": {"value": "divergent"},
        },
        "cognitive_and_perceptual_assumptions": {
            "attention_control": {"value": "normative"},
        },
        "social_and_communicative_assumptions": {
            "neurotypical_communication": {"value": "normative"},
        },
    }


@pytest.fixture
def provider() -> StubProvider:
    """Return a mixed character set that exercises each concrete filter."""
    return StubProvider(
        [
            _character(
                "NA",
                is_human=True,
                pc_eligible=True,
                common_labels=["neurotypical"],
                hsn_divergence=_normative_hsn(),
            ),
            _character(
                "BC",
                is_human=False,
                pc_eligible=False,
                common_labels=["neurotypical"],
                hsn_divergence=None,
            ),
            _character(
                "COG",
                is_human=True,
                pc_eligible=True,
                common_labels=["other"],
                hsn_divergence=_cognitive_divergent_hsn(),
            ),
            _character(
                "COM",
                is_human=True,
                pc_eligible=False,
                common_labels=["other"],
                hsn_divergence=_communication_divergent_hsn(),
            ),
            _character(
                "PHY",
                is_human=False,
                pc_eligible=False,
                common_labels=["other"],
                hsn_divergence=_physical_divergent_hsn(),
            ),
            _character("WS", is_human=True, pc_eligible=True, common_labels=["anxiety", "hypervigilance"]),
            _character("KAT", is_human=True, pc_eligible=True, common_labels=["ADHD"]),
            _character("GEN", is_human=True, pc_eligible=False, common_labels=["other"]),
        ]
    )


@pytest.mark.unit
def test_all_characters_filter_returns_every_character(provider: StubProvider) -> None:
    """The all filter should return every character in provider order."""
    result = AllCharactersFilter().get_characters(provider=provider)
    assert [character.hid for character in result] == ["NA", "BC", "COG", "COM", "PHY", "WS", "KAT", "GEN"]


@pytest.mark.unit
def test_pc_eligible_filter_returns_only_pc_eligible_characters(provider: StubProvider) -> None:
    """pc-eligible should include only characters with a truthy pc_eligible flag."""
    result = PcEligibleFilter().get_characters(provider=provider)
    assert [character.hid for character in result] == ["NA", "COG", "WS", "KAT"]


@pytest.mark.unit
def test_human_filter_returns_only_humans(provider: StubProvider) -> None:
    """Human should require is_human to be truthy."""
    result = HumanFilter().get_characters(provider=provider)
    assert [character.hid for character in result] == ["NA", "COG", "COM", "WS", "KAT", "GEN"]


@pytest.mark.unit
def test_non_human_filter_returns_only_non_humans(provider: StubProvider) -> None:
    """Non-human should include only characters with a falsy is_human flag."""
    result = NonHumanFilter().get_characters(provider=provider)
    assert [character.hid for character in result] == ["BC", "PHY"]


@pytest.mark.unit
def test_human_normative_filter_returns_only_human_neurotypical_characters(provider: StubProvider) -> None:
    """Human-normative should require both is_human and neurotypical labeling."""
    result = HumanNormativeFilter().get_characters(provider=provider)
    assert [character.hid for character in result] == ["NA"]


@pytest.mark.unit
def test_neurotypical_filter_returns_any_neurotypical_character(provider: StubProvider) -> None:
    """Neurotypical should include both human and non-human neurotypical characters."""
    result = NeurotypicalFilter().get_characters(provider=provider)
    assert [character.hid for character in result] == ["NA", "BC"]


@pytest.mark.unit
def test_divergent_filter_matches_any_non_normative_hsn_profile(provider: StubProvider) -> None:
    """Divergent should include any character with at least one non-normative HSN value."""
    result = DivergentFilter().get_characters(provider=provider)
    assert [character.hid for character in result] == ["COG", "COM", "PHY"]


@pytest.mark.unit
def test_neurodivergent_filter_matches_cognitive_and_communication_divergence(provider: StubProvider) -> None:
    """Neurodivergent should include cognitive and neurotypical-communication divergence."""
    result = NeurodivergentFilter().get_characters(provider=provider)
    assert [character.hid for character in result] == ["COG", "COM"]


@pytest.mark.unit
def test_physical_divergence_filter_matches_physical_only_divergence(provider: StubProvider) -> None:
    """Physical-divergence should include physical divergence but exclude cognitive-only divergence."""
    result = PhysicalDivergenceFilter().get_characters(provider=provider)
    assert [character.hid for character in result] == ["PHY"]


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
        ("pc-eligible", PcEligibleFilter),
        ("human", HumanFilter),
        ("non-human", NonHumanFilter),
        ("human-normative", HumanNormativeFilter),
        ("neurotypical", NeurotypicalFilter),
        ("divergent", DivergentFilter),
        ("neurodivergent", NeurodivergentFilter),
        ("physical-divergence", PhysicalDivergenceFilter),
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
