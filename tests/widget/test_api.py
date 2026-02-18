"""Tests for the Gradio API functions."""

import pytest
from unittest.mock import MagicMock, patch

from dcs_simulation_engine.widget import api
from dcs_simulation_engine.widget.services import RunRegistry, get_registry


@pytest.fixture
def mock_registry():
    """Provide a fresh registry for each test."""
    registry = RunRegistry()
    with patch("dcs_simulation_engine.widget.api.get_registry", return_value=registry):
        with patch(
            "dcs_simulation_engine.widget.services.get_registry", return_value=registry
        ):
            yield registry


@pytest.fixture
def mock_run_manager():
    """Create a mock RunManager."""
    mock = MagicMock()
    mock.name = "test-run-123"
    mock.turns = 0
    mock.runtime_seconds = 0
    mock.runtime_string = "00:00:00"
    mock.exited = False
    mock.exit_reason = ""
    mock.saved = False
    mock.state = {}
    mock.context = {"pc": {"hid": "pc-1", "name": "Player"}, "npc": {"hid": "npc-1", "name": "NPC"}}
    mock.game_config = MagicMock()
    mock.game_config.name = "test-game"
    return mock


class TestCreateRun:
    """Tests for create_run API function."""

    @pytest.mark.unit
    def test_create_run_success(self, mock_registry, mock_run_manager):
        """Test successful run creation."""
        with patch(
            "dcs_simulation_engine.widget.api.RunManager.create",
            return_value=mock_run_manager,
        ):
            result = api.create_run(game="test-game")

            assert "run_id" in result
            assert result["run_id"] == "test-run-123"
            assert result["game_name"] == "test-game"
            assert "pc" in result
            assert "npc" in result
            assert "meta" in result
            assert "error" not in result

    @pytest.mark.unit
    def test_create_run_with_options(self, mock_registry, mock_run_manager):
        """Test run creation with all optional parameters."""
        with patch(
            "dcs_simulation_engine.widget.api.RunManager.create",
            return_value=mock_run_manager,
        ) as mock_create:
            result = api.create_run(
                game="test-game",
                source="test",
                pc_choice="pc-1",
                npc_choice="npc-1",
                access_key="key123",
                player_id="player-1",
            )

            mock_create.assert_called_once_with(
                game="test-game",
                source="test",
                pc_choice="pc-1",
                npc_choice="npc-1",
                access_key="key123",
                player_id="player-1",
            )
            assert "error" not in result

    @pytest.mark.unit
    def test_create_run_error(self, mock_registry):
        """Test error handling when run creation fails."""
        with patch(
            "dcs_simulation_engine.widget.api.RunManager.create",
            side_effect=ValueError("Invalid game config"),
        ):
            result = api.create_run(game="nonexistent-game")

            assert "error" in result
            assert "Invalid game config" in result["error"]


class TestStepRun:
    """Tests for step_run API function."""

    @pytest.mark.unit
    def test_step_run_with_input(self, mock_registry, mock_run_manager):
        """Test stepping with user input."""
        mock_registry.add("test-run", mock_run_manager)

        result = api.step_run(run_id="test-run", user_input="hello")

        mock_run_manager.step.assert_called_once_with(user_input="hello")
        assert "state" in result
        assert "meta" in result
        assert "error" not in result

    @pytest.mark.unit
    def test_step_run_without_input(self, mock_registry, mock_run_manager):
        """Test stepping without user input."""
        mock_registry.add("test-run", mock_run_manager)

        result = api.step_run(run_id="test-run", user_input=None)

        mock_run_manager.step.assert_called_once_with(user_input=None)
        assert "error" not in result

    @pytest.mark.unit
    def test_step_run_not_found(self, mock_registry):
        """Test stepping a non-existent run."""
        result = api.step_run(run_id="nonexistent", user_input=None)

        assert "error" in result
        assert "not found" in result["error"].lower()


class TestPlayRun:
    """Tests for play_run API function."""

    @pytest.mark.unit
    def test_play_run_batch_processing(self, mock_registry, mock_run_manager):
        """Test processing a batch of inputs."""
        mock_registry.add("test-run", mock_run_manager)
        mock_run_manager.exited = False

        result = api.play_run(run_id="test-run", inputs=["input1", "input2", "input3"])

        assert mock_run_manager.step.call_count == 3
        assert "final_state" in result
        assert "meta" in result
        assert "error" not in result

    @pytest.mark.unit
    def test_play_run_early_exit(self, mock_registry, mock_run_manager):
        """Test stopping when simulation exits."""
        mock_registry.add("test-run", mock_run_manager)

        # Simulate exit after first step
        def side_effect(*args, **kwargs):
            mock_run_manager.exited = True

        mock_run_manager.step.side_effect = side_effect

        result = api.play_run(run_id="test-run", inputs=["input1", "input2", "input3"])

        # Should only call step once before exiting
        assert mock_run_manager.step.call_count == 1
        assert "error" not in result

    @pytest.mark.unit
    def test_play_run_not_found(self, mock_registry):
        """Test playing a non-existent run."""
        result = api.play_run(run_id="nonexistent", inputs=["input"])

        assert "error" in result


class TestGetState:
    """Tests for get_state API function."""

    @pytest.mark.unit
    def test_get_state_success(self, mock_registry, mock_run_manager):
        """Test retrieving run state."""
        mock_run_manager.state = {"key": "value"}
        mock_registry.add("test-run", mock_run_manager)

        result = api.get_state(run_id="test-run")

        assert "state" in result
        assert result["state"] == {"key": "value"}
        assert "meta" in result
        assert "error" not in result

    @pytest.mark.unit
    def test_get_state_not_found(self, mock_registry):
        """Test getting state of non-existent run."""
        result = api.get_state(run_id="nonexistent")

        assert "error" in result


class TestSaveRun:
    """Tests for save_run API function."""

    @pytest.mark.unit
    def test_save_run_default_path(self, mock_registry, mock_run_manager):
        """Test saving with default path."""
        mock_run_manager.save.return_value = "/tmp/output/run.json"
        mock_registry.add("test-run", mock_run_manager)

        result = api.save_run(run_id="test-run")

        mock_run_manager.save.assert_called_once()
        assert result["saved"] is True
        assert result["output_path"] == "/tmp/output/run.json"
        assert "error" not in result

    @pytest.mark.unit
    def test_save_run_custom_path(self, mock_registry, mock_run_manager):
        """Test saving with custom path."""
        mock_run_manager.save.return_value = "/custom/path/run.json"
        mock_registry.add("test-run", mock_run_manager)

        result = api.save_run(run_id="test-run", output_dir="/custom/path")

        mock_run_manager.save.assert_called_once_with(path="/custom/path")
        assert result["saved"] is True
        assert "error" not in result

    @pytest.mark.unit
    def test_save_run_not_found(self, mock_registry):
        """Test saving non-existent run."""
        result = api.save_run(run_id="nonexistent")

        assert "error" in result


class TestDeleteRun:
    """Tests for delete_run API function."""

    @pytest.mark.unit
    def test_delete_run_exists(self, mock_registry, mock_run_manager):
        """Test deleting an existing run."""
        mock_registry.add("test-run", mock_run_manager)

        result = api.delete_run(run_id="test-run")

        assert result["success"] is True
        assert mock_registry.get("test-run") is None

    @pytest.mark.unit
    def test_delete_run_idempotent(self, mock_registry):
        """Test deleting non-existent run is idempotent."""
        result = api.delete_run(run_id="nonexistent")

        # Should succeed even if run doesn't exist
        assert result["success"] is True


class TestSharedRegistry:
    """Tests for shared registry behavior."""

    @pytest.mark.unit
    def test_registry_singleton(self):
        """Test that get_registry returns the same instance."""
        registry1 = get_registry()
        registry2 = get_registry()

        assert registry1 is registry2

    @pytest.mark.unit
    def test_registry_add_and_get(self, mock_registry, mock_run_manager):
        """Test adding and retrieving from registry."""
        mock_registry.add("run-1", mock_run_manager)

        retrieved = mock_registry.get("run-1")

        assert retrieved is mock_run_manager

    @pytest.mark.unit
    def test_registry_remove(self, mock_registry, mock_run_manager):
        """Test removing from registry."""
        mock_registry.add("run-1", mock_run_manager)
        mock_registry.remove("run-1")

        assert mock_registry.get("run-1") is None

    @pytest.mark.unit
    def test_registry_list_runs(self, mock_registry, mock_run_manager):
        """Test listing all runs."""
        mock_registry.add("run-1", mock_run_manager)
        mock_registry.add("run-2", mock_run_manager)

        runs = mock_registry.list_runs()

        assert "run-1" in runs
        assert "run-2" in runs
        assert len(runs) == 2
