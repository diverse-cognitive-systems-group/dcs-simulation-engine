"""Unit tests for remote Fly lifecycle helpers."""

from pathlib import Path

import httpx
import pytest
from dcs_simulation_engine.infra import remote as remote_infra


def _write_run_config(path: Path, *, name: str = "usability-ca") -> None:
    """Write a minimal valid run config for remote deployment tests."""
    path.write_text(
        "\n".join(
            [
                f"name: {name}",
                "description: Remote deployment test run",
                "ui:",
                "  registration_required: true",
                "players:",
                "  humans:",
                "    all: true",
                "games:",
                "  - name: Explore",
                "next_game_strategy:",
                "  strategy:",
                "    id: full_character_access",
                "    allow_choice_if_multiple: true",
                "    require_completion: false",
                "forms: []",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


@pytest.mark.unit
def test_derive_remote_app_names_uses_default_prefix() -> None:
    """Remote app names should be derived from the normalized experiment slug."""
    names = remote_infra.derive_remote_app_names(experiment_name="Usability CA")

    assert names.api_app == "dcs-usability-ca-api"
    assert names.ui_app == "dcs-usability-ca-ui"
    assert names.db_app == "dcs-usability-ca-db"


@pytest.mark.unit
def test_ensure_volume_creates_non_interactively(monkeypatch: pytest.MonkeyPatch) -> None:
    """Volume creation should pass Fly's non-interactive confirmation flag."""
    captured: list[tuple[list[str], str | None]] = []

    monkeypatch.setattr(remote_infra, "_flyctl_json", lambda *args, **kwargs: [])

    def _capture_run(args: list[str], *, fly_api_token: str | None = None, **_kwargs) -> str:
        captured.append((args, fly_api_token))
        return ""

    monkeypatch.setattr(remote_infra, "_run_flyctl", _capture_run)

    remote_infra._ensure_volume(
        app_name="dcs-usability-ca-db",
        region="lax",
        fly_api_token="fly-token",
    )

    assert captured == [
        (
            [
                "volumes",
                "create",
                remote_infra.REMOTE_DB_VOLUME_NAME,
                "--app",
                "dcs-usability-ca-db",
                "--size",
                str(remote_infra.REMOTE_DB_VOLUME_SIZE_GB),
                "--yes",
                "--region",
                "lax",
            ],
            "fly-token",
        )
    ]


@pytest.mark.unit
def test_ensure_volume_creates_new_region_specific_volume(monkeypatch: pytest.MonkeyPatch) -> None:
    """Region fallback should provision a new volume when the existing one lives elsewhere."""
    captured: list[tuple[list[str], str | None]] = []

    monkeypatch.setattr(
        remote_infra,
        "_flyctl_json",
        lambda *args, **kwargs: [{"name": remote_infra.REMOTE_DB_VOLUME_NAME, "region": "sjc"}],
    )

    def _capture_run(args: list[str], *, fly_api_token: str | None = None, **_kwargs) -> str:
        captured.append((args, fly_api_token))
        return ""

    monkeypatch.setattr(remote_infra, "_run_flyctl", _capture_run)

    remote_infra._ensure_volume(
        app_name="dcs-free-play-db",
        region="lax",
        fly_api_token="fly-token",
    )

    assert captured == [
        (
            [
                "volumes",
                "create",
                remote_infra.REMOTE_DB_VOLUME_NAME,
                "--app",
                "dcs-free-play-db",
                "--size",
                str(remote_infra.REMOTE_DB_VOLUME_SIZE_GB),
                "--yes",
                "--region",
                "lax",
            ],
            "fly-token",
        )
    ]


@pytest.mark.unit
def test_deploy_remote_experiment_generates_configs_and_commands(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Remote deploy should render temp Fly configs and return concrete follow-up commands."""
    config_path = tmp_path / "experiment.yaml"
    seed_path = tmp_path / "seed.json"
    _write_run_config(config_path)
    seed_path.write_text("[]", encoding="utf-8")
    artifacts_root = tmp_path / "repo"
    artifacts_root.mkdir()
    (artifacts_root / "deployments").mkdir()

    deploy_calls: list[tuple[str, Path, dict[str, str] | None, dict[str, str] | None]] = []

    monkeypatch.setattr(remote_infra, "_repo_root", lambda: artifacts_root)
    monkeypatch.setattr(remote_infra, "_ensure_app_exists", lambda *args, **kwargs: None)
    monkeypatch.setattr(remote_infra, "_ensure_volume", lambda *args, **kwargs: None)
    monkeypatch.setattr(remote_infra, "_wait_for_mongo_ready", lambda **_kwargs: None)
    monkeypatch.setattr(remote_infra, "_wait_for_health", lambda **_kwargs: None)
    monkeypatch.setattr(remote_infra, "_bootstrap_remote_deployment", lambda **_kwargs: "issued-secret-key")
    monkeypatch.setattr(remote_infra.shutil, "rmtree", lambda *args, **kwargs: None)

    def _capture_deploy(
        *,
        config_path: Path,
        app_name: str,
        cwd: Path,
        fly_api_token,
        env_vars=None,
        build_args=None,
    ):
        deploy_calls.append((app_name, config_path, env_vars, build_args))
        assert cwd == artifacts_root
        assert fly_api_token == "fly-token"

    monkeypatch.setattr(remote_infra, "_deploy_from_config", _capture_deploy)

    result = remote_infra.deploy_remote_experiment(
        config=config_path,
        openrouter_key="or-key",
        mongo_seed_path=seed_path,
        fly_api_token="fly-token",
        region="sea",
    )

    assert result.experiment_name == "usability-ca"
    assert result.deployed_apps == ["db", "api", "ui"]
    assert result.api_app == "dcs-usability-ca-api"
    assert result.ui_app == "dcs-usability-ca-ui"
    assert result.db_app == "dcs-usability-ca-db"
    assert "dcs remote status" in result.status_command
    assert f"--admin-key {remote_infra.REMOTE_ADMIN_KEY_PLACEHOLDER}" in result.status_command
    assert f"--admin-key {remote_infra.REMOTE_ADMIN_KEY_PLACEHOLDER}" in result.save_command
    assert "issued-secret-key" not in result.status_command
    assert "issued-secret-key" not in result.save_command
    assert len(deploy_calls) == 3

    api_fly = (artifacts_root / "deployments" / "usability-ca" / "dcs-usability-ca-api.fly.toml").read_text(encoding="utf-8")
    ui_fly = (artifacts_root / "deployments" / "usability-ca" / "dcs-usability-ca-ui.fly.toml").read_text(encoding="utf-8")
    db_fly = (artifacts_root / "deployments" / "usability-ca" / "dcs-usability-ca-db.fly.toml").read_text(encoding="utf-8")
    copied_run_config = (artifacts_root / "deployments" / "usability-ca" / "run_configs" / "run_config.yml").read_text(encoding="utf-8")

    assert 'dockerfile = "../../docker/api.dockerfile"' in api_fly
    assert "--host 0.0.0.0 --port 8000" in api_fly
    assert "--remote-managed" in api_fly
    assert 'dockerfile = "../../docker/ui.fly.dockerfile"' in ui_fly
    assert 'dockerfile = "../../docker/mongo.fly.dockerfile"' in db_fly
    assert "--config /app/deployments/usability-ca/run_configs/run_config.yml" in api_fly
    assert "name: usability-ca" in copied_run_config


@pytest.mark.unit
def test_deploy_remote_experiment_supports_anonymous_demo_run_config(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Remote deploy should support the anonymous demo run config without a custom config."""
    seed_path = tmp_path / "seed.json"
    seed_path.write_text("[]", encoding="utf-8")
    artifacts_root = tmp_path / "repo"
    artifacts_root.mkdir()
    (artifacts_root / "deployments").mkdir()

    deploy_calls: list[tuple[str, Path, dict[str, str] | None, dict[str, str] | None]] = []

    monkeypatch.setattr(remote_infra, "_repo_root", lambda: artifacts_root)
    monkeypatch.setattr(remote_infra, "_ensure_app_exists", lambda *args, **kwargs: None)
    monkeypatch.setattr(remote_infra, "_ensure_volume", lambda *args, **kwargs: None)
    monkeypatch.setattr(remote_infra, "_wait_for_mongo_ready", lambda **_kwargs: None)
    monkeypatch.setattr(remote_infra, "_wait_for_health", lambda **_kwargs: None)
    monkeypatch.setattr(remote_infra, "_bootstrap_remote_deployment", lambda **_kwargs: "issued-secret-key")

    def _capture_deploy(
        *,
        config_path: Path,
        app_name: str,
        cwd: Path,
        fly_api_token,
        env_vars=None,
        build_args=None,
    ):
        deploy_calls.append((app_name, config_path, env_vars, build_args))
        assert cwd == artifacts_root
        assert fly_api_token == "fly-token"

    monkeypatch.setattr(remote_infra, "_deploy_from_config", _capture_deploy)

    result = remote_infra.deploy_remote_experiment(
        config=None,
        free_play=True,
        openrouter_key="or-key",
        mongo_seed_path=seed_path,
        fly_api_token="fly-token",
        region="sjc",
    )

    assert result.experiment_name == "free-play"
    assert result.api_app == "dcs-free-play-api"
    assert result.ui_app == "dcs-free-play-ui"
    assert result.db_app == "dcs-free-play-db"
    assert "free-play.tar.gz" in result.save_command
    assert len(deploy_calls) == 3

    api_fly = (artifacts_root / "deployments" / "free-play" / "dcs-free-play-api.fly.toml").read_text(encoding="utf-8")
    assert "--config /app/examples/run_configs/demo.yml" in api_fly
    assert "--default-experiment" not in api_fly
    assert not (artifacts_root / "deployments" / "free-play" / "run_configs").exists()


@pytest.mark.unit
def test_deploy_remote_experiment_can_target_one_app(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Targeted remote deploys should only redeploy the requested app and skip bootstrap."""
    config_path = tmp_path / "experiment.yaml"
    seed_path = tmp_path / "seed.json"
    _write_run_config(config_path)
    seed_path.write_text("[]", encoding="utf-8")
    artifacts_root = tmp_path / "repo"
    artifacts_root.mkdir()
    (artifacts_root / "deployments").mkdir()

    deploy_calls: list[str] = []
    bootstrap_calls: list[str] = []
    ensured_apps: list[str] = []
    mongo_waits: list[str] = []
    api_health_waits: list[str] = []

    monkeypatch.setattr(remote_infra, "_repo_root", lambda: artifacts_root)
    monkeypatch.setattr(remote_infra, "_ensure_app_exists", lambda app_name, **_kwargs: ensured_apps.append(app_name))
    monkeypatch.setattr(remote_infra, "_ensure_volume", lambda *args, **kwargs: None)
    monkeypatch.setattr(remote_infra, "_wait_for_mongo_ready", lambda **_kwargs: mongo_waits.append("db"))
    monkeypatch.setattr(remote_infra, "_wait_for_health", lambda **_kwargs: api_health_waits.append("api"))
    monkeypatch.setattr(
        remote_infra,
        "_bootstrap_remote_deployment",
        lambda **_kwargs: bootstrap_calls.append("bootstrap") or "admin-key",
    )

    def _capture_deploy(*, config_path: Path, app_name: str, cwd: Path, **_kwargs):
        assert cwd == artifacts_root
        deploy_calls.append(app_name)

    monkeypatch.setattr(remote_infra, "_deploy_from_config", _capture_deploy)

    result = remote_infra.deploy_remote_experiment(
        config=config_path,
        openrouter_key="or-key",
        mongo_seed_path=seed_path,
        fly_api_token="fly-token",
        region="sea",
        deploy_apps={"ui"},
    )

    assert result.deployed_apps == ["ui"]
    assert result.admin_api_key is None
    assert f"--admin-key {remote_infra.REMOTE_ADMIN_KEY_PLACEHOLDER}" in result.status_command
    assert result.save_command is None
    assert result.stop_command is None
    assert deploy_calls == ["dcs-usability-ca-ui"]
    assert ensured_apps == ["dcs-usability-ca-ui"]
    assert bootstrap_calls == []
    assert mongo_waits == []
    assert api_health_waits == []


@pytest.mark.unit
def test_deploy_remote_experiment_api_only_does_not_redeploy_ui(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Targeted API deploys should not implicitly redeploy the UI app."""
    config_path = tmp_path / "experiment.yaml"
    seed_path = tmp_path / "seed.json"
    _write_run_config(config_path)
    seed_path.write_text("[]", encoding="utf-8")
    artifacts_root = tmp_path / "repo"
    artifacts_root.mkdir()
    (artifacts_root / "deployments").mkdir()

    deploy_calls: list[str] = []
    ensured_apps: list[str] = []

    monkeypatch.setattr(remote_infra, "_repo_root", lambda: artifacts_root)
    monkeypatch.setattr(remote_infra, "_ensure_app_exists", lambda app_name, **_kwargs: ensured_apps.append(app_name))
    monkeypatch.setattr(remote_infra, "_ensure_volume", lambda *args, **kwargs: None)
    monkeypatch.setattr(remote_infra, "_wait_for_mongo_ready", lambda **_kwargs: None)
    monkeypatch.setattr(remote_infra, "_wait_for_health", lambda **_kwargs: None)
    monkeypatch.setattr(remote_infra, "_bootstrap_remote_deployment", lambda **_kwargs: "issued-secret-key")

    def _capture_deploy(*, app_name: str, cwd: Path, **_kwargs):
        assert cwd == artifacts_root
        deploy_calls.append(app_name)

    monkeypatch.setattr(remote_infra, "_deploy_from_config", _capture_deploy)

    result = remote_infra.deploy_remote_experiment(
        config=config_path,
        openrouter_key="or-key",
        mongo_seed_path=seed_path,
        fly_api_token="fly-token",
        region="sea",
        deploy_apps={"api"},
    )

    assert result.deployed_apps == ["api"]
    assert result.admin_api_key is None
    assert deploy_calls == ["dcs-usability-ca-api"]
    assert ensured_apps == ["dcs-usability-ca-api"]


@pytest.mark.unit
def test_fetch_remote_status_reports_destroyed_when_api_app_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Remote status should fail cleanly when the remote API cannot be reached."""

    class _FailingClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, path: str, headers=None):
            _ = headers
            request = httpx.Request("GET", f"https://missing-api.fly.dev{path}")
            response = httpx.Response(status_code=503, request=request)
            raise httpx.HTTPStatusError("unavailable", request=request, response=response)

    monkeypatch.setattr(remote_infra.httpx, "Client", _FailingClient)

    with pytest.raises(remote_infra.RemoteLifecycleError, match="Failed to fetch remote deployment status"):
        remote_infra.fetch_remote_status(
            uri="https://missing-api.fly.dev",
            admin_key="admin-key",
        )


@pytest.mark.unit
def test_fetch_remote_status_uses_authenticated_experiment_endpoints(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remote status should use the saved admin key to fetch experiment status payloads."""
    calls: list[tuple[str, dict[str, str] | None]] = []

    class _Response:
        def __init__(self, payload: dict):
            self._payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return self._payload

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, path: str, headers=None):
            calls.append((path, headers))
            if path == "/api/remote/status":
                return _Response(
                    {
                        "mode": "experiment",
                        "experiment_name": "usability-ca",
                    }
                )
            if path == "/api/run/status":
                return _Response({"is_open": True, "total": 4, "completed": 2, "per_game": {}})
            raise AssertionError(f"Unexpected path: {path}")

    monkeypatch.setattr(remote_infra.httpx, "Client", _Client)

    result = remote_infra.fetch_remote_status(
        uri="https://dcs-usability-ca-api.fly.dev",
        admin_key="admin-key",
    )

    assert result.mode == "experiment"
    assert result.experiment_name == "usability-ca"
    assert result.experiment_status == {"is_open": True, "total": 4, "completed": 2, "per_game": {}}
    assert calls[1] == (
        "/api/run/status",
        {"Authorization": "Bearer admin-key"},
    )


@pytest.mark.unit
def test_fetch_remote_status_returns_remote_status_payload_for_free_play(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remote status should fall back to the remote status payload when no experiment is hosted."""

    class _Response:
        def __init__(self, payload: dict):
            self._payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return self._payload

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, path: str, headers=None):
            _ = headers
            if path == "/api/remote/status":
                return _Response(
                    {
                        "status": "ok",
                        "mode": "free_play",
                        "experiment_name": None,
                        "uptime": 12,
                    }
                )
            raise AssertionError(f"Unexpected path: {path}")

    monkeypatch.setattr(remote_infra.httpx, "Client", _Client)

    result = remote_infra.fetch_remote_status(
        uri="https://dcs-free-play-api.fly.dev",
        admin_key="admin-key",
    )

    assert result.mode == "free_play"
    assert result.experiment_name is None
    assert result.experiment_status == {
        "status": "ok",
        "mode": "free_play",
        "experiment_name": None,
        "uptime": 12,
    }


@pytest.mark.unit
def test_save_remote_database_requests_zip_export(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Remote save should request zip exports when the target filename ends with .zip."""
    save_path = tmp_path / "export.zip"
    captured: dict[str, object] = {}

    class _StreamResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def raise_for_status(self) -> None:
            return None

        def iter_bytes(self):
            yield b"zip-bytes"

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def stream(self, method: str, path: str, params=None, headers=None):
            captured["method"] = method
            captured["path"] = path
            captured["params"] = params
            captured["headers"] = headers
            return _StreamResponse()

    monkeypatch.setattr(remote_infra.httpx, "Client", _Client)

    result = remote_infra.save_remote_database(
        uri="https://dcs-usability-ca-api.fly.dev",
        admin_key="admin-key",
        save_db_path=save_path,
    )

    assert result == save_path
    assert save_path.read_bytes() == b"zip-bytes"
    assert captured["params"] == {"format": "zip"}
    assert captured["headers"] == {"Authorization": "Bearer admin-key"}


@pytest.mark.unit
def test_stop_remote_experiment_saves_before_destroying(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Remote stop should not destroy anything until the save step succeeds."""
    save_path = tmp_path / "export.tar.gz"
    call_order: list[str] = []

    def _save(**kwargs):
        call_order.append("save")
        assert kwargs["save_db_path"] == save_path
        return save_path

    def _destroy(app_name: str, **_kwargs):
        call_order.append(app_name)

    monkeypatch.setattr(remote_infra, "save_remote_database", _save)
    monkeypatch.setattr(remote_infra, "_destroy_app", _destroy)

    result = remote_infra.stop_remote_experiment(
        uri="https://dcs-usability-ca-api.fly.dev",
        admin_key="admin-key",
        save_db_path=save_path,
        api_app="api-app",
        ui_app="ui-app",
        db_app="db-app",
        fly_api_token="fly-token",
    )

    assert result == save_path
    assert call_order == ["save", "ui-app", "api-app", "db-app"]


@pytest.mark.unit
def test_bootstrap_remote_deployment_sends_explicit_admin_key(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Remote bootstrap uploads the requested admin key header when provided."""
    seed_path = tmp_path / "seed.json"
    seed_path.write_text("[]", encoding="utf-8")
    requested_key = "dcs-ak-r9kc-B9kmhuyV85tUWIcl8KHrPl_HO7Z3BnAlcgMtJU"
    captured: dict[str, object] = {}

    class _Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, str]:
            return {"admin_api_key": requested_key}

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, path: str, headers=None, content=None):
            captured["path"] = path
            captured["headers"] = headers
            captured["content"] = b"".join(content)
            return _Response()

    monkeypatch.setattr(remote_infra.httpx, "Client", _Client)

    result = remote_infra._bootstrap_remote_deployment(
        api_url="https://dcs-usability-ca-api.fly.dev",
        bootstrap_token="bootstrap-secret",
        mongo_seed_path=seed_path,
        admin_key=requested_key,
    )

    assert result == requested_key
    assert captured["path"] == "/api/remote/bootstrap"
    assert captured["headers"] == {
        "X-DCS-Bootstrap-Token": "bootstrap-secret",
        "X-DCS-Mongo-Seed-Filename": "seed.json",
        "Content-Type": "application/json",
        "X-DCS-Admin-Key": requested_key,
    }
    assert captured["content"] == b"[]"
