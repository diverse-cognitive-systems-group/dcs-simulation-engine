"""Unit tests for remote CLI command wiring."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from dcs_simulation_engine.cli.app import app
from dcs_simulation_engine.cli.commands import remote as remote_command
from dcs_simulation_engine.infra import remote as remote_infra
from dcs_simulation_engine.infra.remote import RemoteDeploymentResult, RemoteStatusResult
from typer.testing import CliRunner


@pytest.mark.unit
def test_remote_deploy_command_outputs_json(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Remote deploy should surface the structured deployment payload when --json is set."""
    config_path = tmp_path / "experiment.yaml"
    seed_path = tmp_path / "seed.json"
    config_path.write_text(
        ("name: usability-ca\nassignment_strategy:\n  strategy: random_unique\n  games: [explore]\n  quota_per_game: 1\n"),
        encoding="utf-8",
    )
    seed_path.write_text("[]", encoding="utf-8")
    deploy = MagicMock(
        return_value=RemoteDeploymentResult(
            experiment_name="usability-ca",
            deployed_apps=["db", "api", "ui"],
            api_app="dcs-usability-ca-api",
            ui_app="dcs-usability-ca-ui",
            db_app="dcs-usability-ca-db",
            api_url="https://dcs-usability-ca-api.fly.dev",
            ui_url="https://dcs-usability-ca-ui.fly.dev",
            admin_api_key="admin-key",
            status_command="dcs remote status ...",
            save_command="dcs remote save ...",
            stop_command="dcs remote stop ...",
        )
    )
    monkeypatch.setattr(remote_command, "deploy_remote_experiment", deploy)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "remote",
            "deploy",
            "--config",
            str(config_path),
            "--openrouter-key",
            "or-key",
            "--mongo-seed-path",
            str(seed_path),
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["experiment_name"] == "usability-ca"
    assert payload["api_app"] == "dcs-usability-ca-api"
    deploy.assert_called_once()
    assert deploy.call_args.kwargs["mongo_seed_path"] == seed_path


@pytest.mark.unit
def test_remote_deploy_command_passes_targeted_apps(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Remote deploy should allow targeted redeploys of one or more explicit apps."""
    config_path = tmp_path / "experiment.yaml"
    seed_path = tmp_path / "seed.json"
    config_path.write_text(
        ("name: usability-ca\nassignment_strategy:\n  strategy: random_unique\n  games: [explore]\n  quota_per_game: 1\n"),
        encoding="utf-8",
    )
    seed_path.write_text("[]", encoding="utf-8")
    deploy = MagicMock(
        return_value=RemoteDeploymentResult(
            experiment_name="usability-ca",
            deployed_apps=["ui"],
            api_app="dcs-usability-ca-api",
            ui_app="dcs-usability-ca-ui",
            db_app="dcs-usability-ca-db",
            api_url="https://dcs-usability-ca-api.fly.dev",
            ui_url="https://dcs-usability-ca-ui.fly.dev",
            admin_api_key=None,
            status_command="dcs remote status ...",
            save_command=None,
            stop_command=None,
        )
    )
    monkeypatch.setattr(remote_command, "deploy_remote_experiment", deploy)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "remote",
            "deploy",
            "--config",
            str(config_path),
            "--openrouter-key",
            "or-key",
            "--mongo-seed-path",
            str(seed_path),
            "--only-app",
            "ui",
        ],
    )

    assert result.exit_code == 0
    deploy.assert_called_once()
    assert deploy.call_args.kwargs["deploy_apps"] == {"ui"}
    assert deploy.call_args.kwargs["free_play"] is False
    assert deploy.call_args.kwargs["mongo_seed_path"] == seed_path


@pytest.mark.unit
def test_remote_deploy_command_supports_free_play_without_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Remote deploy should allow free-play mode without an experiment config."""
    seed_path = tmp_path / "seed.json"
    seed_path.write_text("[]", encoding="utf-8")
    deploy = MagicMock(
        return_value=RemoteDeploymentResult(
            experiment_name="free-play",
            deployed_apps=["db", "api", "ui"],
            api_app="dcs-free-play-api",
            ui_app="dcs-free-play-ui",
            db_app="dcs-free-play-db",
            api_url="https://dcs-free-play-api.fly.dev",
            ui_url="https://dcs-free-play-ui.fly.dev",
            admin_api_key="admin-key",
            status_command="dcs remote status ...",
            save_command="dcs remote save ...",
            stop_command="dcs remote stop ...",
        )
    )
    monkeypatch.setattr(remote_command, "deploy_remote_experiment", deploy)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "remote",
            "deploy",
            "--free-play",
            "--openrouter-key",
            "or-key",
            "--mongo-seed-path",
            str(seed_path),
        ],
    )

    assert result.exit_code == 0
    deploy.assert_called_once()
    assert deploy.call_args.kwargs["config"] is None
    assert deploy.call_args.kwargs["free_play"] is True
    assert deploy.call_args.kwargs["mongo_seed_path"] == seed_path


@pytest.mark.unit
def test_remote_deploy_command_prints_admin_key_once(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Remote deploy should surface the admin key once and warn the user to save it."""
    config_path = tmp_path / "experiment.yaml"
    seed_path = tmp_path / "seed.json"
    config_path.write_text(
        ("name: usability-ca\nassignment_strategy:\n  strategy: random_unique\n  games: [explore]\n  quota_per_game: 1\n"),
        encoding="utf-8",
    )
    seed_path.write_text("[]", encoding="utf-8")
    deploy = MagicMock(
        return_value=RemoteDeploymentResult(
            experiment_name="usability-ca",
            deployed_apps=["db", "api", "ui"],
            api_app="dcs-usability-ca-api",
            ui_app="dcs-usability-ca-ui",
            db_app="dcs-usability-ca-db",
            api_url="https://dcs-usability-ca-api.fly.dev",
            ui_url="https://dcs-usability-ca-ui.fly.dev",
            admin_api_key="issued-secret-key",
            status_command="dcs remote status --uri https://dcs-usability-ca-api.fly.dev --admin-key <saved-admin-key>",
            save_command="dcs remote save ...",
            stop_command="dcs remote stop ...",
        )
    )
    monkeypatch.setattr(remote_command, "deploy_remote_experiment", deploy)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "remote",
            "deploy",
            "--config",
            str(config_path),
            "--openrouter-key",
            "or-key",
            "--mongo-seed-path",
            str(seed_path),
        ],
    )

    assert result.exit_code == 0
    assert "Save this admin key now. It will only be shown once." in result.stdout
    assert result.stdout.count("issued-secret-key") == 1


@pytest.mark.unit
def test_remote_deploy_command_passes_explicit_admin_key(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Remote deploy should forward a user-supplied admin key override."""
    config_path = tmp_path / "experiment.yaml"
    seed_path = tmp_path / "seed.json"
    config_path.write_text(
        ("name: usability-ca\nassignment_strategy:\n  strategy: random_unique\n  games: [explore]\n  quota_per_game: 1\n"),
        encoding="utf-8",
    )
    seed_path.write_text("[]", encoding="utf-8")
    requested_key = "dcs-ak-r9kc-B9kmhuyV85tUWIcl8KHrPl_HO7Z3BnAlcgMtJU"
    deploy = MagicMock(
        return_value=RemoteDeploymentResult(
            experiment_name="usability-ca",
            deployed_apps=["db", "api", "ui"],
            api_app="dcs-usability-ca-api",
            ui_app="dcs-usability-ca-ui",
            db_app="dcs-usability-ca-db",
            api_url="https://dcs-usability-ca-api.fly.dev",
            ui_url="https://dcs-usability-ca-ui.fly.dev",
            admin_api_key=requested_key,
            status_command="dcs remote status ...",
            save_command="dcs remote save ...",
            stop_command="dcs remote stop ...",
        )
    )
    monkeypatch.setattr(remote_command, "deploy_remote_experiment", deploy)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "remote",
            "deploy",
            "--config",
            str(config_path),
            "--openrouter-key",
            "or-key",
            "--mongo-seed-path",
            str(seed_path),
            "--admin-key",
            requested_key,
        ],
    )

    assert result.exit_code == 0
    assert deploy.call_args.kwargs["admin_key"] == requested_key


@pytest.mark.unit
def test_remote_deploy_command_retries_regions_on_capacity_errors(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Remote deploy should try later regions when Fly reports capacity exhaustion."""
    config_path = tmp_path / "experiment.yaml"
    seed_path = tmp_path / "seed.json"
    config_path.write_text(
        ("name: usability-ca\nassignment_strategy:\n  strategy: random_unique\n  games: [explore]\n  quota_per_game: 1\n"),
        encoding="utf-8",
    )
    seed_path.write_text("[]", encoding="utf-8")
    deploy_calls: list[str | None] = []
    success_result = RemoteDeploymentResult(
        experiment_name="usability-ca",
        deployed_apps=["db", "api", "ui"],
        api_app="dcs-usability-ca-api",
        ui_app="dcs-usability-ca-ui",
        db_app="dcs-usability-ca-db",
        api_url="https://dcs-usability-ca-api.fly.dev",
        ui_url="https://dcs-usability-ca-ui.fly.dev",
        admin_api_key="admin-key",
        status_command="dcs remote status ...",
        save_command="dcs remote save ...",
        stop_command="dcs remote stop ...",
    )

    def _deploy_side_effect(**kwargs):
        deploy_calls.append(kwargs["region"])
        if kwargs["region"] == "lax":
            raise remote_infra.RemoteLifecycleError(
                "failed to launch VM: aborted: insufficient resources available to fulfill request: "
                "could not reserve resource for machine: insufficient memory available to fulfill request"
            )
        return success_result

    monkeypatch.setattr(remote_command, "deploy_remote_experiment", _deploy_side_effect)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "remote",
            "deploy",
            "--config",
            str(config_path),
            "--openrouter-key",
            "or-key",
            "--mongo-seed-path",
            str(seed_path),
            "--regions",
            "lax",
            "sjc",
            "dfw",
        ],
    )

    assert result.exit_code == 0
    assert "Attempting Fly deploy in region: lax" in result.stdout
    assert "Region lax is out of capacity. Attempting another region." in result.stdout
    assert "Attempting Fly deploy in region: sjc" in result.stdout
    assert deploy_calls == ["lax", "sjc"]


@pytest.mark.unit
def test_remote_status_command_wires_helper(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remote status should print the experiment status payload."""
    fetch_status = MagicMock(
        return_value=RemoteStatusResult(
            api_url="https://dcs-usability-ca-api.fly.dev",
            mode="experiment",
            experiment_name="usability-ca",
            experiment_status={"is_open": True, "total": 4, "completed": 1, "per_game": {}},
        )
    )
    monkeypatch.setattr(remote_command, "fetch_remote_status", fetch_status)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "remote",
            "status",
            "--uri",
            "https://dcs-usability-ca-api.fly.dev",
            "--admin-key",
            "admin-key",
        ],
    )

    assert result.exit_code == 0
    assert '"completed": 1' in result.stdout
    fetch_status.assert_called_once_with(
        uri="https://dcs-usability-ca-api.fly.dev",
        admin_key="admin-key",
    )


@pytest.mark.unit
def test_remote_save_command_wires_helper(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Remote save should delegate to the export downloader helper."""
    save_path = tmp_path / "export.tar.gz"
    save_remote_database = MagicMock(return_value=save_path)
    monkeypatch.setattr(remote_command, "save_remote_database", save_remote_database)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "remote",
            "save",
            "--uri",
            "https://dcs-usability-ca-api.fly.dev",
            "--admin-key",
            "admin-key",
            "--save-db-path",
            str(save_path),
        ],
    )

    assert result.exit_code == 0
    assert str(save_path) in result.stdout
    save_remote_database.assert_called_once_with(
        uri="https://dcs-usability-ca-api.fly.dev",
        admin_key="admin-key",
        save_db_path=save_path,
    )


@pytest.mark.unit
def test_remote_stop_command_wires_helper(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Remote stop should save first, then destroy via the remote stop helper."""
    save_path = tmp_path / "export.tar.gz"
    stop_remote = MagicMock(return_value=save_path)
    monkeypatch.setattr(remote_command, "stop_remote_experiment", stop_remote)
    monkeypatch.delenv("FLY_API_TOKEN", raising=False)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "remote",
            "stop",
            "--uri",
            "https://dcs-usability-ca-api.fly.dev",
            "--admin-key",
            "admin-key",
            "--save-db-path",
            str(save_path),
            "--api-app",
            "dcs-usability-ca-api",
            "--ui-app",
            "dcs-usability-ca-ui",
            "--db-app",
            "dcs-usability-ca-db",
        ],
    )

    assert result.exit_code == 0
    assert "Remote deployment destroyed." in result.stdout
    stop_remote.assert_called_once_with(
        uri="https://dcs-usability-ca-api.fly.dev",
        admin_key="admin-key",
        save_db_path=save_path,
        api_app="dcs-usability-ca-api",
        ui_app="dcs-usability-ca-ui",
        db_app="dcs-usability-ca-db",
        fly_api_token=None,
    )
