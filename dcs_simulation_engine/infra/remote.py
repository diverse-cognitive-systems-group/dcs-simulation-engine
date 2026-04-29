"""High-level remote Fly deployment lifecycle helpers."""

from __future__ import annotations

import json
import os
import re
import secrets
import shlex
import shutil
import subprocess
import tarfile
import tempfile
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any, Iterator

import httpx
from dcs_simulation_engine.core.run_config import RunConfig
from dcs_simulation_engine.deployments import templates as deployment_templates
from dcs_simulation_engine.infra.fly import FlyError
from dcs_simulation_engine.utils.auth import validate_access_key
from jinja2 import StrictUndefined
from jinja2.sandbox import SandboxedEnvironment

REMOTE_DB_VOLUME_NAME = "data"
REMOTE_DB_VOLUME_SIZE_GB = 1
REMOTE_UI_PORT = 8080
REMOTE_API_PORT = 8000
REMOTE_API_HOST = "0.0.0.0"
REMOTE_MONGO_PORT = 27017
REMOTE_DEPLOY_TIMEOUT_S = 180
REMOTE_MONGO_READY_TIMEOUT_S = 120
REMOTE_FLY_CONFIG_DOCKER_DIR = "../../docker"
REMOTE_DEPLOYMENTS_DIRNAME = "deployments"
REMOTE_ADMIN_KEY_PLACEHOLDER = "<saved-admin-key>"

_deployment_template_env = SandboxedEnvironment(undefined=StrictUndefined)


class RemoteLifecycleError(RuntimeError):
    """Raised when a remote Fly lifecycle operation fails."""


@dataclass(frozen=True)
class RemoteAppNames:
    """Concrete Fly app names for one remote experiment deployment."""

    api_app: str
    ui_app: str
    db_app: str


@dataclass(frozen=True)
class RemoteDeploymentResult:
    """Structured output returned after a successful remote deployment."""

    experiment_name: str
    deployed_apps: list[str]
    api_app: str
    ui_app: str
    db_app: str
    api_url: str
    ui_url: str
    admin_api_key: str | None
    status_command: str
    save_command: str | None
    stop_command: str | None

    def model_dump(self) -> dict[str, Any]:
        """Return a JSON-serializable dict payload."""
        return asdict(self)


@dataclass(frozen=True)
class BaseFlyTemplateContext:
    """Shared context fields for generated Fly config templates."""

    app_name: str
    region: str | None
    docker_dir: str


@dataclass(frozen=True)
class ApiFlyTemplateContext(BaseFlyTemplateContext):
    """Template context for the API Fly config."""

    process_cmd_json: str
    api_port: int


@dataclass(frozen=True)
class UiFlyTemplateContext(BaseFlyTemplateContext):
    """Template context for the UI Fly config."""

    ui_port: int


@dataclass(frozen=True)
class DbFlyTemplateContext(BaseFlyTemplateContext):
    """Template context for the DB Fly config."""

    db_volume_name: str


@dataclass(frozen=True)
class RemoteRenderedFlyConfigs:
    """Rendered Fly TOML contents for one remote experiment deployment."""

    api_toml: str
    ui_toml: str
    db_toml: str


@dataclass(frozen=True)
class RemoteFlyConfigPaths:
    """Concrete file paths for generated Fly TOML configs."""

    api_path: Path
    ui_path: Path
    db_path: Path


@dataclass(frozen=True)
class RemoteStatusResult:
    """Authenticated experiment status returned for CLI presentation."""

    api_url: str
    mode: str | None
    experiment_name: str | None
    experiment_status: dict[str, Any] | None

    def model_dump(self) -> dict[str, Any]:
        """Return a JSON-serializable dict payload."""
        return asdict(self)


REMOTE_DEPLOY_APP_ORDER = ("db", "api", "ui")


def slugify_experiment_name(value: str) -> str:
    """Normalize an experiment name into a Fly-app-safe slug."""
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    if not slug:
        raise RemoteLifecycleError("Experiment name does not produce a valid Fly app slug.")
    return slug


def derive_remote_app_names(
    *,
    experiment_name: str,
    api_app: str | None = None,
    ui_app: str | None = None,
    db_app: str | None = None,
) -> RemoteAppNames:
    """Return explicit or derived app names for a remote experiment deployment."""
    slug = slugify_experiment_name(experiment_name)
    prefix = f"dcs-{slug}"
    return RemoteAppNames(
        api_app=api_app or f"{prefix}-api",
        ui_app=ui_app or f"{prefix}-ui",
        db_app=db_app or f"{prefix}-db",
    )


def _normalize_deploy_apps(deploy_apps: set[str] | None) -> list[str]:
    """Return validated deploy targets in deployment order."""
    if not deploy_apps:
        return list(REMOTE_DEPLOY_APP_ORDER)

    normalized = {app.strip().lower() for app in deploy_apps if app.strip()}
    invalid = sorted(normalized.difference(REMOTE_DEPLOY_APP_ORDER))
    if invalid:
        raise RemoteLifecycleError(f"deploy_apps must be drawn from {', '.join(REMOTE_DEPLOY_APP_ORDER)}; got {', '.join(invalid)}.")
    return [app for app in REMOTE_DEPLOY_APP_ORDER if app in normalized]


def app_url(app_name: str) -> str:
    """Return the public Fly URL for an app."""
    return f"https://{app_name}.fly.dev"


def _repo_root() -> Path:
    """Return the repository root used for deploy staging and artifacts."""
    return Path(__file__).resolve().parents[2]


def _fly_env(*, fly_api_token: str | None = None) -> dict[str, str]:
    """Return an environment mapping for Fly CLI invocations."""
    env = dict(os.environ)
    if fly_api_token:
        env["FLY_API_TOKEN"] = fly_api_token
    return env


def _run_flyctl(
    args: list[str],
    *,
    fly_api_token: str | None = None,
    cwd: Path | None = None,
    capture_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Run a Fly CLI command and return the completed process."""
    try:
        return subprocess.run(
            ["flyctl", *args],
            check=True,
            cwd=str(cwd) if cwd is not None else None,
            env=_fly_env(fly_api_token=fly_api_token),
            capture_output=capture_output,
            text=True,
        )
    except FileNotFoundError as exc:
        raise FlyError("flyctl not found. Please install Fly CLI and ensure it is on PATH.") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or "").strip() or (exc.stdout or "").strip() or f"flyctl {' '.join(args)} failed"
        raise FlyError(detail) from exc


def _flyctl_json(args: list[str], *, fly_api_token: str | None = None) -> Any:
    """Run a Fly CLI command with JSON output and parse the response."""
    proc = _run_flyctl([*args, "--json"], fly_api_token=fly_api_token, capture_output=True)
    return json.loads(proc.stdout or "{}")


def _app_exists(app_name: str, *, fly_api_token: str | None = None) -> bool:
    """Return True when the named Fly app already exists."""
    apps = _flyctl_json(["apps", "list"], fly_api_token=fly_api_token)
    if not isinstance(apps, list):
        return False
    return any(str(app.get("name") or "") == app_name for app in apps if isinstance(app, dict))


def _ensure_app_exists(app_name: str, *, fly_api_token: str | None = None) -> None:
    """Create the Fly app if it does not already exist."""
    if _app_exists(app_name, fly_api_token=fly_api_token):
        return
    _run_flyctl(["apps", "create", app_name], fly_api_token=fly_api_token)


def _list_machines(app_name: str, *, fly_api_token: str | None = None) -> list[dict[str, Any]]:
    """Return the machine list for one Fly app, or an empty list when unavailable."""
    try:
        payload = _flyctl_json(["machine", "list", "--app", app_name], fly_api_token=fly_api_token)
    except FlyError:
        return []
    return payload if isinstance(payload, list) else []


def _ensure_volume(
    *,
    app_name: str,
    region: str | None,
    fly_api_token: str | None = None,
    volume_name: str = REMOTE_DB_VOLUME_NAME,
    size_gb: int = REMOTE_DB_VOLUME_SIZE_GB,
) -> None:
    """Ensure the Mongo Fly app has a persistent volume before deployment."""
    volumes = _flyctl_json(["volumes", "list", "--app", app_name], fly_api_token=fly_api_token)
    if isinstance(volumes, list):
        for volume in volumes:
            if not isinstance(volume, dict):
                continue
            if str(volume.get("name") or volume.get("Name") or "") != volume_name:
                continue
            volume_region = str(volume.get("region") or volume.get("Region") or "")
            if region is None or volume_region == region:
                return

    cmd = ["volumes", "create", volume_name, "--app", app_name, "--size", str(size_gb), "--yes"]
    if region:
        cmd.extend(["--region", region])
    _run_flyctl(cmd, fly_api_token=fly_api_token)


def _wait_for_mongo_ready(
    *,
    app_name: str,
    fly_api_token: str | None = None,
    timeout_s: int = REMOTE_MONGO_READY_TIMEOUT_S,
) -> None:
    """Wait until the remote Mongo app accepts a local ping inside its Fly machine."""
    deadline = time.monotonic() + timeout_s
    command = 'mongosh --quiet --eval "db.adminCommand({ ping: 1 })"'

    while time.monotonic() < deadline:
        try:
            _run_flyctl(
                ["ssh", "console", "--app", app_name, "-C", command],
                fly_api_token=fly_api_token,
                capture_output=True,
            )
            return
        except FlyError:
            time.sleep(2.0)

    raise RemoteLifecycleError(f"Timed out waiting for Mongo app {app_name!r} to become ready.")


def _deploy_from_config(
    *,
    config_path: Path,
    app_name: str,
    cwd: Path,
    fly_api_token: str | None = None,
    env_vars: dict[str, str] | None = None,
    build_args: dict[str, str] | None = None,
) -> None:
    """Deploy one app from a generated Fly config file."""
    cmd = [
        "deploy",
        "--config",
        str(config_path),
        "--app",
        app_name,
        "--ha=false",
    ]
    for key, value in (env_vars or {}).items():
        cmd.extend(["--env", f"{key}={value}"])
    for key, value in (build_args or {}).items():
        cmd.extend(["--build-arg", f"{key}={value}"])
    _run_flyctl(cmd, fly_api_token=fly_api_token, cwd=cwd)


def _destroy_app(app_name: str, *, fly_api_token: str | None = None) -> None:
    """Destroy a Fly app and all of its resources."""
    _run_flyctl(["apps", "destroy", app_name, "--yes"], fly_api_token=fly_api_token)


def _write_text(path: Path, content: str) -> Path:
    """Write a UTF-8 text file and return its path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _shell_join(parts: list[str]) -> str:
    """Return a shell-safe command string."""
    return " ".join(shlex.quote(part) for part in parts)


def _api_process_command(
    *,
    deployment_name: str,
    bootstrap_token: str,
    ui_url: str,
) -> str:
    """Build the remote-managed API server command string."""
    parts = [
        "dcs",
        "server",
        "--host",
        REMOTE_API_HOST,
        "--port",
        str(REMOTE_API_PORT),
        "--remote-managed",
        "--config",
        "/app/deployments/" + deployment_name + "/run_configs/run_config.yml",
    ]
    parts.extend(
        [
            "--bootstrap-token",
            bootstrap_token,
            "--cors-origin",
            ui_url,
        ]
    )
    return _shell_join(parts)


def _render_deployment_template(
    template_name: str,
    context: ApiFlyTemplateContext | UiFlyTemplateContext | DbFlyTemplateContext,
) -> str:
    """Render one Fly config template from the packaged deployments directory."""
    template_text = files(deployment_templates).joinpath(template_name).read_text(encoding="utf-8")
    return _deployment_template_env.from_string(template_text).render(**asdict(context)).rstrip() + "\n"


def _render_api_fly_toml(*, app_name: str, region: str | None, process_cmd: str) -> str:
    """Render the API Fly config file."""
    return _render_deployment_template(
        "api.fly.toml.j2",
        ApiFlyTemplateContext(
            app_name=app_name,
            region=region,
            docker_dir=REMOTE_FLY_CONFIG_DOCKER_DIR,
            process_cmd_json=json.dumps(process_cmd),
            api_port=REMOTE_API_PORT,
        ),
    )


def _render_ui_fly_toml(*, app_name: str, region: str | None) -> str:
    """Render the UI Fly config file."""
    return _render_deployment_template(
        "ui.fly.toml.j2",
        UiFlyTemplateContext(
            app_name=app_name,
            region=region,
            docker_dir=REMOTE_FLY_CONFIG_DOCKER_DIR,
            ui_port=REMOTE_UI_PORT,
        ),
    )


def _render_db_fly_toml(*, app_name: str, region: str | None) -> str:
    """Render the Mongo Fly config file."""
    return _render_deployment_template(
        "db.fly.toml.j2",
        DbFlyTemplateContext(
            app_name=app_name,
            region=region,
            docker_dir=REMOTE_FLY_CONFIG_DOCKER_DIR,
            db_volume_name=REMOTE_DB_VOLUME_NAME,
        ),
    )


def _deployment_artifact_dir(*, experiment_name: str) -> Path:
    """Return the persistent repo-local directory for generated deploy configs."""
    return _repo_root() / REMOTE_DEPLOYMENTS_DIRNAME / slugify_experiment_name(experiment_name)


def _write_deployment_run_config(*, output_dir: Path, experiment_name: str, source_path: Path) -> Path:
    """Persist the selected run config under the deployment artifact directory."""
    experiment_dir = output_dir / "run_configs"
    experiment_dir.mkdir(parents=True, exist_ok=True)
    destination = experiment_dir / "run_config.yml"
    shutil.copy2(source_path, destination)
    return destination


def _write_remote_fly_configs(
    *,
    output_dir: Path,
    names: RemoteAppNames,
    rendered_configs: RemoteRenderedFlyConfigs,
) -> RemoteFlyConfigPaths:
    """Write all generated Fly configs into one directory and return their paths."""
    return RemoteFlyConfigPaths(
        api_path=_write_text(output_dir / f"{names.api_app}.fly.toml", rendered_configs.api_toml),
        ui_path=_write_text(output_dir / f"{names.ui_app}.fly.toml", rendered_configs.ui_toml),
        db_path=_write_text(output_dir / f"{names.db_app}.fly.toml", rendered_configs.db_toml),
    )


def _wait_for_health(*, base_url: str, timeout_s: int = REMOTE_DEPLOY_TIMEOUT_S) -> None:
    """Poll the remote API health endpoint until it responds or times out."""
    with httpx.Client(base_url=base_url, timeout=10.0) as client:
        start = time.monotonic()
        while time.monotonic() - start < timeout_s:
            try:
                response = client.get("/healthz")
                if response.status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(2.0)
    raise RemoteLifecycleError(f"Timed out waiting for {base_url}/healthz to become ready.")


def _validate_mongo_seed_path(path: Path) -> Path:
    """Return a normalized seed path when the given local source is supported."""
    resolved = path.expanduser().resolve()
    if not resolved.exists():
        raise RemoteLifecycleError(f"Mongo seed path does not exist: {resolved}")
    if resolved.is_dir():
        return resolved

    lower_name = resolved.name.lower()
    if lower_name.endswith((".zip", ".tar.gz", ".tgz", ".tar")):
        return resolved
    if resolved.suffix.lower() in {".json", ".ndjson"}:
        return resolved

    raise RemoteLifecycleError("mongo_seed_path must be a directory, a .zip/.tar.gz/.tgz/.tar archive, or a .json/.ndjson file.")


@contextmanager
def _open_mongo_seed_upload(path: Path) -> Iterator[tuple[str, str, Any]]:
    """Yield a file tuple suitable for the remote bootstrap multipart upload."""
    resolved = _validate_mongo_seed_path(path)
    temp_root: Path | None = None
    upload_path = resolved
    content_type = "application/octet-stream"

    if resolved.is_dir():
        temp_root = Path(tempfile.mkdtemp(prefix="dcs-remote-seed-"))
        upload_path = temp_root / f"{resolved.name or 'mongo-seed'}.tar.gz"
        with tarfile.open(upload_path, "w:gz") as archive:
            archive.add(resolved, arcname=resolved.name)
        content_type = "application/gzip"
    else:
        lower_name = resolved.name.lower()
        if lower_name.endswith(".zip"):
            content_type = "application/zip"
        elif lower_name.endswith((".tar.gz", ".tgz", ".tar")):
            content_type = "application/gzip"
        elif resolved.suffix.lower() in {".json", ".ndjson"}:
            content_type = "application/json"

    try:
        with upload_path.open("rb") as upload_file:
            yield upload_path.name, content_type, upload_file
    finally:
        if temp_root is not None:
            shutil.rmtree(temp_root, ignore_errors=True)


def _iter_file_chunks(upload_file: Any, *, chunk_size: int = 1024 * 1024) -> Iterator[bytes]:
    """Yield a local file handle as fixed-size bytes chunks for streaming uploads."""
    while True:
        chunk = upload_file.read(chunk_size)
        if not chunk:
            break
        yield chunk


def _bootstrap_remote_deployment(
    *,
    api_url: str,
    bootstrap_token: str,
    mongo_seed_path: Path,
    admin_key: str | None = None,
) -> str:
    """Upload the selected Mongo seed source and return the issued admin API key."""
    with httpx.Client(base_url=api_url, timeout=60.0) as client, _open_mongo_seed_upload(mongo_seed_path) as upload:
        filename, content_type, upload_file = upload
        headers = {
            "X-DCS-Bootstrap-Token": bootstrap_token,
            "X-DCS-Mongo-Seed-Filename": filename,
            "Content-Type": content_type,
        }
        if admin_key is not None:
            headers["X-DCS-Admin-Key"] = validate_access_key(admin_key)
        response = client.post(
            "/api/remote/bootstrap",
            headers=headers,
            content=_iter_file_chunks(upload_file),
        )
        response.raise_for_status()
        payload = response.json()

    admin_key = str(payload.get("admin_api_key") or "")
    if not admin_key:
        raise RemoteLifecycleError("Remote bootstrap succeeded but did not return an admin API key.")
    return admin_key


def load_run_config(config: str | Path) -> tuple[Path, RunConfig]:
    """Resolve and load the run config selected for remote deployment."""
    possible_path = Path(config).expanduser()
    if possible_path.is_file():
        resolved = possible_path.resolve()
    else:
        resolved = (_repo_root() / "examples" / "run_configs" / str(config)).with_suffix(".yml").resolve()
    return resolved, RunConfig.load(resolved)


def _resolve_remote_deployment_target(
    *,
    config: str | Path | None,
) -> tuple[str, Path]:
    """Return the deployment name and source run config path."""
    if config is None:
        raise RemoteLifecycleError("config is required.")

    config_path, experiment = load_run_config(config)
    return experiment.name, config_path


def deploy_remote_experiment(
    *,
    config: str | Path | None = None,
    openrouter_key: str,
    mongo_seed_path: str | Path,
    admin_key: str | None = None,
    fly_api_token: str | None = None,
    region: str | None = None,
    api_app: str | None = None,
    ui_app: str | None = None,
    db_app: str | None = None,
    deploy_apps: set[str] | None = None,
) -> RemoteDeploymentResult:
    """Deploy one remote-managed stack and bootstrap its remote admin key."""
    mongo_seed_path = _validate_mongo_seed_path(Path(mongo_seed_path))
    if admin_key is not None:
        admin_key = validate_access_key(admin_key)
    deployment_name, config_path = _resolve_remote_deployment_target(config=config)
    selected_apps = _normalize_deploy_apps(deploy_apps)
    is_full_deploy = selected_apps == list(REMOTE_DEPLOY_APP_ORDER)
    names = derive_remote_app_names(
        experiment_name=deployment_name,
        api_app=api_app,
        ui_app=ui_app,
        db_app=db_app,
    )
    api_url = app_url(names.api_app)
    ui_url = app_url(names.ui_app)
    mongo_uri = f"mongodb://{names.db_app}.internal:{REMOTE_MONGO_PORT}/"
    bootstrap_token = f"dcs-bootstrap-{slugify_experiment_name(deployment_name)}-{secrets.token_urlsafe(12)}"
    rendered_configs = RemoteRenderedFlyConfigs(
        api_toml=_render_api_fly_toml(
            app_name=names.api_app,
            region=region,
            process_cmd=_api_process_command(
                deployment_name=deployment_name,
                bootstrap_token=bootstrap_token,
                ui_url=ui_url,
            ),
        ),
        ui_toml=_render_ui_fly_toml(app_name=names.ui_app, region=region),
        db_toml=_render_db_fly_toml(app_name=names.db_app, region=region),
    )
    artifact_dir = _deployment_artifact_dir(experiment_name=deployment_name)
    fly_configs = _write_remote_fly_configs(
        output_dir=artifact_dir,
        names=names,
        rendered_configs=rendered_configs,
    )
    _write_deployment_run_config(
        output_dir=artifact_dir,
        experiment_name=deployment_name,
        source_path=config_path,
    )

    repo_root = _repo_root()
    if "db" in selected_apps:
        _ensure_app_exists(names.db_app, fly_api_token=fly_api_token)
        _ensure_volume(app_name=names.db_app, region=region, fly_api_token=fly_api_token)
        _deploy_from_config(
            config_path=fly_configs.db_path,
            app_name=names.db_app,
            cwd=repo_root,
            fly_api_token=fly_api_token,
        )
        _wait_for_mongo_ready(app_name=names.db_app, fly_api_token=fly_api_token)

    if "api" in selected_apps:
        _ensure_app_exists(names.api_app, fly_api_token=fly_api_token)
        _deploy_from_config(
            config_path=fly_configs.api_path,
            app_name=names.api_app,
            cwd=repo_root,
            fly_api_token=fly_api_token,
            env_vars={
                "MONGO_URI": mongo_uri,
                "OPENROUTER_API_KEY": openrouter_key,
            },
        )
        _wait_for_health(base_url=api_url)

    admin_api_key: str | None = None
    if is_full_deploy:
        admin_api_key = _bootstrap_remote_deployment(
            api_url=api_url,
            bootstrap_token=bootstrap_token,
            mongo_seed_path=mongo_seed_path,
            admin_key=admin_key,
        )

    if "ui" in selected_apps:
        _ensure_app_exists(names.ui_app, fly_api_token=fly_api_token)
        _deploy_from_config(
            config_path=fly_configs.ui_path,
            app_name=names.ui_app,
            cwd=repo_root,
            fly_api_token=fly_api_token,
            build_args={"VITE_API_ORIGIN": api_url},
        )

    status_command = f"dcs remote status --uri {shlex.quote(api_url)} --admin-key {REMOTE_ADMIN_KEY_PLACEHOLDER}"
    save_command = (
        (
            f"dcs remote save --uri {shlex.quote(api_url)} --admin-key {REMOTE_ADMIN_KEY_PLACEHOLDER} "
            f"--save-db-path {shlex.quote(f'{slugify_experiment_name(deployment_name)}.tar.gz')}"
        )
        if admin_api_key
        else None
    )
    stop_command = (
        (
            f"dcs remote stop --uri {shlex.quote(api_url)} --admin-key {REMOTE_ADMIN_KEY_PLACEHOLDER} "
            f"--save-db-path {shlex.quote(f'{slugify_experiment_name(deployment_name)}.tar.gz')} "
            f"--api-app {shlex.quote(names.api_app)} --ui-app {shlex.quote(names.ui_app)} "
            f"--db-app {shlex.quote(names.db_app)}"
        )
        if admin_api_key
        else None
    )

    return RemoteDeploymentResult(
        experiment_name=deployment_name,
        deployed_apps=selected_apps,
        api_app=names.api_app,
        ui_app=names.ui_app,
        db_app=names.db_app,
        api_url=api_url,
        ui_url=ui_url,
        admin_api_key=admin_api_key,
        status_command=status_command,
        save_command=save_command,
        stop_command=stop_command,
    )


def fetch_remote_status(
    *,
    uri: str,
    admin_key: str,
) -> RemoteStatusResult:
    """Return the authenticated status payload for one remote deployment."""
    try:
        with httpx.Client(base_url=uri.rstrip("/"), timeout=15.0) as client:
            remote_response = client.get("/api/remote/status")
            remote_response.raise_for_status()
            payload = remote_response.json()
            experiment_name = payload.get("experiment_name")
            experiment_status: dict[str, Any]
            if experiment_name:
                headers = {"Authorization": f"Bearer {admin_key}"}
                experiment_response = client.get("/api/run/status", headers=headers)
                experiment_response.raise_for_status()
                experiment_status = experiment_response.json()
            else:
                experiment_status = payload
    except httpx.HTTPError as exc:
        raise RemoteLifecycleError(f"Failed to fetch remote deployment status: {exc}") from exc

    return RemoteStatusResult(
        api_url=uri,
        mode=payload.get("mode"),
        experiment_name=experiment_name,
        experiment_status=experiment_status,
    )


def _archive_format_for_save_path(save_db_path: Path) -> str:
    """Infer the requested remote export format from the local filename."""
    suffixes = [part.lower() for part in save_db_path.suffixes]
    if suffixes[-2:] == [".tar", ".gz"]:
        return "tar.gz"
    if suffixes[-1:] == [".zip"]:
        return "zip"
    raise RemoteLifecycleError("save_db_path must end with .tar.gz or .zip.")


def save_remote_database(*, uri: str, admin_key: str, save_db_path: Path) -> Path:
    """Download the remote database export archive to the requested local path."""
    save_db_path.parent.mkdir(parents=True, exist_ok=True)
    archive_format = _archive_format_for_save_path(save_db_path)
    with httpx.Client(base_url=uri.rstrip("/"), timeout=None) as client:
        with client.stream(
            "GET",
            "/api/remote/db-export",
            params={"format": archive_format},
            headers={"Authorization": f"Bearer {admin_key}"},
        ) as response:
            response.raise_for_status()
            with save_db_path.open("wb") as handle:
                for chunk in response.iter_bytes():
                    handle.write(chunk)
    return save_db_path


def stop_remote_experiment(
    *,
    uri: str,
    admin_key: str,
    save_db_path: Path,
    api_app: str,
    ui_app: str,
    db_app: str,
    fly_api_token: str | None = None,
) -> Path:
    """Save the remote DB archive, then destroy all Fly apps for the experiment."""
    saved_path = save_remote_database(uri=uri, admin_key=admin_key, save_db_path=save_db_path)
    for app_name in (ui_app, api_app, db_app):
        _destroy_app(app_name, fly_api_token=fly_api_token)
    return saved_path
