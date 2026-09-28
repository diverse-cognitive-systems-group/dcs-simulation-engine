"""CLI commands for managing the local Docker Compose engine stack."""

import json
import os
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from importlib import metadata
from pathlib import Path

import typer
import yaml
from dcs_simulation_engine.api.app import DEFAULT_RUN_CONFIG_PATH
from dcs_simulation_engine.cli.common import echo
from dcs_simulation_engine.utils.assets import DCSAssets, resolve_assets
from dcs_simulation_engine.utils.paths import package_root

_CONTAINER_RUN_CONFIG_PATH = "/app/run_config.yml"
_COMPOSE_PROJECT_NAME = "dcs"
_PACKAGE_ENGINE_CACHE_ENV = "DCS_ENGINE_ASSETS_DIR"
_PACKAGE_DISTRIBUTION_NAME = "dcs-simulation-engine"

engine_app = typer.Typer(help="Manage local engine state (e.g. start, stop, status, etc).")


@engine_app.command("start")
def start(
    ctx: typer.Context,
    config: Path = typer.Option(
        DEFAULT_RUN_CONFIG_PATH,
        "--config",
        envvar="DCS_RUN_CONFIG",
        help="Run config YAML to use for this engine run.",
    ),
    headless: bool = typer.Option(
        False,
        "--headless",
        help="Start only the database and API services.",
    ),
    api_port: int = typer.Option(
        8000,
        "--api-port",
        envvar="DCS_API_PORT",
        help="Host port for the API service.",
    ),
    ui_port: int = typer.Option(
        5173,
        "--ui-port",
        envvar="DCS_UI_PORT",
        help="Host port for the UI service.",
    ),
    db_port: int = typer.Option(
        27017,
        "--db-port",
        envvar="DCS_DB_PORT",
        help="Host port for the database service.",
    ),
    no_build: bool = typer.Option(
        False,
        "--no-build",
        help="Start existing images without rebuilding them.",
    ),
    follow_logs: bool = typer.Option(
        False,
        "--follow-logs",
        help="Follow service logs after startup succeeds. Ctrl-C stops following logs, not the services.",
    ),
    timeout_seconds: int = typer.Option(
        120,
        "--timeout",
        envvar="DCS_ENGINE_TIMEOUT_SECONDS",
        help="Seconds to wait for services to become ready.",
    ),
) -> None:
    """Start the engine."""
    try:
        source_assets = resolve_assets(Path.cwd())
    except FileNotFoundError as exc:
        echo(
            ctx,
            str(exc),
            style="error",
        )
        raise typer.Exit(code=1) from exc

    engine_assets = _materialize_engine_assets(source_assets)
    engine_root = engine_assets.root

    config_path = _resolve_run_config_path(config, assets=engine_assets)
    if not config_path.is_file():
        echo(ctx, f"Run config not found: {config_path}", style="error")
        raise typer.Exit(code=1)

    echo(ctx, "Checking prerequisites...")
    _ensure_openrouter_key(ctx)
    echo(ctx, "✓ API keys provided", style="success")
    _ensure_docker_ready(ctx)
    echo(ctx, "✓ Docker ready", style="success")

    services = ["mongo", "api"]
    display_services = ["db", "api"]
    if not headless:
        services.append("ui")
        display_services.append("ui")

    env = _compose_env(
        engine_root=engine_root,
        assets_mode=engine_assets.mode,
        api_port=api_port,
        ui_port=ui_port,
        db_port=db_port,
    )

    with tempfile.TemporaryDirectory(prefix="dcs-engine-") as temp_dir:
        override_path = Path(temp_dir) / "compose.engine.yml"
        _write_run_config_override(
            override_path=override_path,
            host_config_path=_host_path_for_docker(config_path, engine_root=engine_root, assets_mode=engine_assets.mode),
        )
        compose_command = _compose_command(engine_root=engine_root)
        startup_compose_command = _compose_command(engine_root=engine_root, override_path=override_path)
        up_command = startup_compose_command + ["up"]
        if not no_build:
            up_command.append("--build")
        up_command += ["--detach", *services]

        echo(ctx, "Starting engine locally...")
        try:
            _run_checked(up_command, env=env)
        except subprocess.CalledProcessError as exc:
            echo(ctx, "Docker Compose failed to start the local engine.", style="error")
            echo(ctx, f"Run logs: {' '.join(compose_command)} logs {' '.join(services)}")
            raise typer.Exit(code=1) from exc
        echo(ctx, f"✓ Compose up: {', '.join(display_services)}", style="success")

        try:
            _wait_for_db(compose_command, env=env, timeout_seconds=timeout_seconds)
        except TimeoutError as exc:
            echo(ctx, f"Database did not become ready within {timeout_seconds} seconds.", style="error")
            echo(ctx, f"Run logs: {' '.join(compose_command)} logs mongo")
            raise typer.Exit(code=1) from exc
        echo(ctx, "✓ Database ready", style="success")

        api_url = f"http://localhost:{api_port}"
        try:
            _wait_for_http(f"http://127.0.0.1:{api_port}/healthz", timeout_seconds=timeout_seconds)
        except TimeoutError as exc:
            echo(ctx, f"Engine API did not become ready within {timeout_seconds} seconds.", style="error")
            echo(ctx, f"Run logs: {' '.join(compose_command)} logs api")
            raise typer.Exit(code=1) from exc
        echo(ctx, "✓ Engine API ready", style="success")
        echo(ctx, f"Engine running at {api_url}")

        if headless:
            echo(ctx, "⚠ Headless mode: default UI not started", style="warning")
            echo(ctx, "  • If you need a front-end, install and start your own UI client")
        else:
            ui_url = f"http://localhost:{ui_port}"
            echo(ctx, "Starting UI...")
            try:
                _wait_for_http(f"http://127.0.0.1:{ui_port}", timeout_seconds=timeout_seconds)
            except TimeoutError as exc:
                echo(ctx, f"UI did not become ready within {timeout_seconds} seconds.", style="error")
                echo(ctx, f"Run logs: {' '.join(compose_command)} logs ui")
                raise typer.Exit(code=1) from exc
            echo(ctx, "✓ UI ready", style="success")
            echo(ctx, f"→ Access the app ui at: {ui_url}")

        echo(ctx, f"View logs: {' '.join(compose_command)} logs -f {' '.join(services)}", style="dim")
        echo(ctx, "Stop: dcs engine stop", style="dim")

        if follow_logs:
            _follow_logs(compose_command, services=services, env=env)


@engine_app.command("stop")
def stop(
    ctx: typer.Context,
    clean: bool = typer.Option(
        False,
        "--clean",
        help="Also remove Docker volumes, including local database state. Does not delete ./runs.",
    ),
) -> None:
    """Stop the engine."""
    try:
        engine_assets = _materialize_engine_assets(resolve_assets(Path.cwd()))
    except FileNotFoundError as exc:
        echo(
            ctx,
            str(exc),
            style="error",
        )
        raise typer.Exit(code=1) from exc

    _ensure_docker_ready(ctx)
    compose_command = _compose_command(engine_root=engine_assets.root)
    down_command = compose_command + ["down"]
    if clean:
        down_command.append("--volumes")

    try:
        _run_checked(
            down_command,
            env=_stop_env(engine_root=engine_assets.root, assets_mode=engine_assets.mode),
        )
    except subprocess.CalledProcessError as exc:
        echo(ctx, "Docker Compose failed to stop the local engine.", style="error")
        raise typer.Exit(code=1) from exc
    echo(ctx, "✓ Engine stopped", style="success")


@engine_app.command("status")
def status(
    ctx: typer.Context,
    api_port: int = typer.Option(
        8000,
        "--api-port",
        envvar="DCS_API_PORT",
        help="Host port for the API service.",
    ),
    ui_port: int = typer.Option(
        5173,
        "--ui-port",
        envvar="DCS_UI_PORT",
        help="Host port for the UI service.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Print the status payload as JSON."),
) -> None:
    """Check local engine status (service health and run progress)."""
    try:
        engine_assets = _materialize_engine_assets(resolve_assets(Path.cwd()))
    except FileNotFoundError as exc:
        echo(
            ctx,
            str(exc),
            style="error",
        )
        raise typer.Exit(code=1) from exc

    _ensure_docker_ready(ctx)
    env = _stop_env(engine_root=engine_assets.root, assets_mode=engine_assets.mode)
    compose_command = _compose_command(engine_root=engine_assets.root)
    services = _compose_services(compose_command, env=env)
    payload = _engine_status_payload(
        compose_command=compose_command,
        env=env,
        services=services,
        api_port=api_port,
        ui_port=ui_port,
    )

    if json_output:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
    else:
        _print_status(ctx, payload, api_port=api_port, ui_port=ui_port)

    if payload["status"] != "healthy":
        raise typer.Exit(code=1)


def _ensure_openrouter_key(ctx: typer.Context) -> None:
    if os.getenv("OPENROUTER_API_KEY", "").strip():
        return
    echo(ctx, "OPENROUTER_API_KEY is required to run the DCS engine locally.", style="error")
    echo(ctx, "Set it in your shell or .env file, then rerun dcs engine start.")
    raise typer.Exit(code=1)


def _ensure_docker_ready(ctx: typer.Context) -> None:
    if shutil.which("docker") is None:
        echo(ctx, "Docker is required to run the DCS engine locally.", style="error")
        echo(ctx, "Install and start Docker Desktop: https://www.docker.com/products/docker-desktop/")
        raise typer.Exit(code=1)
    try:
        _run_checked(["docker", "compose", "version"])
        _run_checked(["docker", "info"])
    except subprocess.CalledProcessError as exc:
        echo(ctx, "Docker is installed but not ready.", style="error")
        echo(ctx, "Start Docker Desktop, then rerun dcs engine start.")
        raise typer.Exit(code=1) from exc


def _resolve_run_config_path(config: Path, *, assets: DCSAssets) -> Path:
    expanded = config.expanduser()
    if expanded.is_file():
        return expanded.resolve()

    if config == DEFAULT_RUN_CONFIG_PATH:
        return assets.default_run_config

    if not expanded.is_absolute():
        asset_relative_path = assets.root / expanded
        if asset_relative_path.is_file():
            return asset_relative_path.resolve()

        named_example_path = assets.run_configs_dir / expanded.name
        if expanded.parent == Path(".") and named_example_path.is_file():
            return named_example_path.resolve()

    return expanded.resolve()


def _materialize_engine_assets(assets: DCSAssets) -> DCSAssets:
    if assets.mode == "repo":
        return assets

    target_root = _package_engine_cache_root()
    if target_root.exists():
        shutil.rmtree(target_root)
    target_root.parent.mkdir(parents=True, exist_ok=True)

    _copy_tree(assets.root, target_root)
    _copy_tree(package_root(), target_root / "dcs_simulation_engine", ignore_package_assets=True)
    _write_package_requirements(target_root / "requirements.txt")
    _write_package_api_dockerfile(target_root / "docker" / "api.dockerfile")
    _write_package_ui_dockerfile(target_root / "docker" / "ui.dockerfile")
    _write_package_caddyfile(target_root / "docker" / "Caddyfile")
    _write_package_compose(target_root / "compose.yml")
    return DCSAssets(
        mode="package",
        root=target_root,
        compose_file=target_root / "compose.yml",
        docker_dir=target_root / "docker",
        run_configs_dir=target_root / "examples" / "run_configs",
        default_run_config=target_root / "examples" / "run_configs" / "demo.yml",
        database_seeds_dir=target_root / "database_seeds",
        ui_dist_dir=target_root / "ui_dist",
    )


def _package_engine_cache_root() -> Path:
    configured = os.getenv(_PACKAGE_ENGINE_CACHE_ENV, "").strip()
    base = Path(configured).expanduser() if configured else Path.home() / ".cache" / "dcs-simulation-engine" / "engine-assets"
    return base / _package_version()


def _package_version() -> str:
    try:
        return metadata.version(_PACKAGE_DISTRIBUTION_NAME)
    except metadata.PackageNotFoundError:
        return "local"


def _copy_tree(source: Path, target: Path, *, ignore_package_assets: bool = False) -> None:
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store")
    if ignore_package_assets:
        ignore = shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store", "package_assets")
    shutil.copytree(source, target, ignore=ignore)


def _write_package_requirements(path: Path) -> None:
    requirements = []
    for requirement in metadata.requires(_PACKAGE_DISTRIBUTION_NAME) or []:
        if "extra ==" in requirement:
            continue
        requirements.append(requirement)
    path.write_text("\n".join(requirements) + "\n", encoding="utf-8")


def _write_package_api_dockerfile(path: Path) -> None:
    path.write_text(
        """# syntax=docker/dockerfile:1

FROM python:3.13-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV MONGO_URI="mongodb://mongo:27017/"
ENV DCS_SERVER_HOST="0.0.0.0"
ENV DCS_SERVER_PORT="8000"

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY dcs_simulation_engine/ ./dcs_simulation_engine/
COPY examples/run_configs/ ./examples/run_configs/
COPY database_seeds/ ./database_seeds/

EXPOSE 8000

CMD ["python", "-m", "dcs_simulation_engine.cli.app", "server"]
""",
        encoding="utf-8",
    )


def _write_package_ui_dockerfile(path: Path) -> None:
    path.write_text(
        """# syntax=docker/dockerfile:1

FROM caddy:2-alpine

WORKDIR /srv

COPY docker/Caddyfile /etc/caddy/Caddyfile
COPY ui_dist/ /srv/

EXPOSE 8080
""",
        encoding="utf-8",
    )


def _write_package_caddyfile(path: Path) -> None:
    path.write_text(
        """:8080 {
    handle /api/* {
        reverse_proxy api:8000
    }

    handle {
        root * /srv
        try_files {path} /index.html
        file_server
    }
}
""",
        encoding="utf-8",
    )


def _write_package_compose(path: Path) -> None:
    compose = {
        "services": {
            "mongo": {
                "build": {"context": ".", "dockerfile": "docker/db.dockerfile"},
                "container_name": "dcs-mongo",
                "restart": "unless-stopped",
                "ports": ["${DCS_DB_PORT:-27017}:27017"],
                "volumes": ["mongo_data:/data/db"],
                "healthcheck": {
                    "test": [
                        "CMD",
                        "mongosh",
                        "--quiet",
                        "mongodb://127.0.0.1:27017/admin",
                        "--eval",
                        "quit(db.runCommand({ ping: 1 }).ok ? 0 : 2)",
                    ],
                    "interval": "10s",
                    "timeout": "5s",
                    "retries": 10,
                    "start_period": "10s",
                },
            },
            "api": {
                "build": {"context": ".", "dockerfile": "docker/api.dockerfile"},
                "container_name": "dcs-api",
                "restart": "unless-stopped",
                "depends_on": {"mongo": {"condition": "service_healthy"}},
                "command": [
                    "/bin/sh",
                    "-c",
                    (
                        "exec python -m dcs_simulation_engine.cli.app server "
                        "--mongo-seed-dir /app/database_seeds/dev "
                        "--config ${DCS_RUN_CONFIG:-/app/examples/run_configs/demo.yml} "
                        "--dump ./runs"
                    ),
                ],
                "environment": {
                    "MONGO_URI": "mongodb://mongo:27017/",
                    "DCS_SERVER_HOST": "0.0.0.0",
                    "DCS_SERVER_PORT": "8000",
                    "OPENROUTER_API_KEY": "${OPENROUTER_API_KEY:?OPENROUTER_API_KEY must be set before running docker compose}",
                },
                "volumes": ["${DCS_RUNS_DIR:-./runs}:/app/runs"],
                "ports": ["${DCS_API_PORT:-8000}:8000"],
                "healthcheck": {
                    "test": [
                        "CMD",
                        "python",
                        "-c",
                        "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz').read()",
                    ],
                    "interval": "10s",
                    "timeout": "5s",
                    "retries": 10,
                    "start_period": "10s",
                },
            },
            "ui": {
                "build": {"context": ".", "dockerfile": "docker/ui.dockerfile"},
                "container_name": "dcs-ui",
                "restart": "unless-stopped",
                "depends_on": {"api": {"condition": "service_healthy"}},
                "ports": ["${DCS_UI_PORT:-5173}:8080"],
            },
        },
        "volumes": {"mongo_data": {"driver": "local"}},
    }
    path.write_text(yaml.safe_dump(compose, sort_keys=False), encoding="utf-8")


def _compose_env(*, engine_root: Path, assets_mode: str, api_port: int, ui_port: int, db_port: int) -> dict[str, str]:
    env = os.environ.copy()
    env["DCS_RUN_CONFIG"] = _CONTAINER_RUN_CONFIG_PATH
    env["DCS_API_PORT"] = str(api_port)
    env["DCS_UI_PORT"] = str(ui_port)
    env["DCS_DB_PORT"] = str(db_port)
    runs_dir = engine_root / "runs" if assets_mode == "repo" else Path.cwd() / "runs"
    env.setdefault("DCS_RUNS_DIR", str(runs_dir))
    return env


def _stop_env(*, engine_root: Path, assets_mode: str) -> dict[str, str]:
    env = os.environ.copy()
    runs_dir = engine_root / "runs" if assets_mode == "repo" else Path.cwd() / "runs"
    env.setdefault("DCS_RUNS_DIR", str(runs_dir))
    env.setdefault("OPENROUTER_API_KEY", "unused-for-engine-stop")
    return env


def _host_path_for_docker(config_path: Path, *, engine_root: Path, assets_mode: str = "repo") -> Path:
    if assets_mode != "repo":
        return config_path

    runs_dir = os.getenv("DCS_RUNS_DIR", "").strip()
    if not runs_dir:
        return config_path

    host_runs_dir = Path(runs_dir).expanduser()
    if not host_runs_dir.is_absolute():
        return config_path

    try:
        relative_path = config_path.relative_to(engine_root)
    except ValueError:
        return config_path

    return host_runs_dir.parent / relative_path


def _write_run_config_override(*, override_path: Path, host_config_path: Path) -> None:
    override = {
        "services": {
            "api": {
                "environment": {
                    "DCS_RUN_CONFIG": _CONTAINER_RUN_CONFIG_PATH,
                },
                "volumes": [
                    {
                        "type": "bind",
                        "source": str(host_config_path),
                        "target": _CONTAINER_RUN_CONFIG_PATH,
                        "read_only": True,
                    }
                ],
            }
        }
    }
    override_path.write_text(yaml.safe_dump(override, sort_keys=False), encoding="utf-8")


def _compose_command(*, engine_root: Path, override_path: Path | None = None) -> list[str]:
    command = [
        "docker",
        "compose",
        "-f",
        str(engine_root / "compose.yml"),
        "--project-directory",
        str(engine_root),
        "-p",
        _COMPOSE_PROJECT_NAME,
    ]
    if override_path is not None:
        command[4:4] = ["-f", str(override_path)]
    return command


def _wait_for_db(compose_command: list[str], *, env: dict[str, str], timeout_seconds: int) -> None:
    deadline = time.monotonic() + timeout_seconds
    command = compose_command + [
        "exec",
        "-T",
        "mongo",
        "mongosh",
        "--quiet",
        "mongodb://127.0.0.1:27017/admin",
        "--eval",
        "quit(db.runCommand({ ping: 1 }).ok ? 0 : 2)",
    ]
    while time.monotonic() < deadline:
        result = subprocess.run(command, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        if result.returncode == 0:
            return
        time.sleep(1)
    raise TimeoutError("database did not become ready")


def _wait_for_http(url: str, *, timeout_seconds: int) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if 200 <= response.status < 500:
                    return
        except (OSError, urllib.error.URLError):
            pass
        time.sleep(1)
    raise TimeoutError(f"{url} did not become ready")


def _run_checked(command: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, env=env, text=True, check=True)


def _run_capture(command: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, env=env, text=True, capture_output=True, check=True)


def _follow_logs(compose_command: list[str], *, services: list[str], env: dict[str, str]) -> None:
    try:
        subprocess.run(compose_command + ["logs", "--follow", *services], env=env, check=False)
    except KeyboardInterrupt:
        pass


def _compose_services(compose_command: list[str], *, env: dict[str, str]) -> dict[str, dict]:
    try:
        result = _run_capture(compose_command + ["ps", "--format", "json"], env=env)
    except subprocess.CalledProcessError:
        return {}
    return _parse_compose_services(result.stdout)


def _parse_compose_services(raw: str) -> dict[str, dict]:
    raw = raw.strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        records = [json.loads(line) for line in raw.splitlines() if line.strip()]
    else:
        records = data if isinstance(data, list) else [data]

    services = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        service = str(record.get("Service") or record.get("service") or "")
        if service:
            services[service] = record
    return services


def _engine_status_payload(
    *,
    compose_command: list[str],
    env: dict[str, str],
    services: dict[str, dict],
    api_port: int,
    ui_port: int,
) -> dict:
    db_state = _service_status(services.get("mongo"))
    api_state = _service_status(services.get("api"))
    ui_state = _service_status(services.get("ui"))

    db_ready = db_state["running"] and _db_is_ready(compose_command, env=env)
    api_ready = api_state["running"] and _http_is_ready(f"http://127.0.0.1:{api_port}/healthz")
    ui_ready = ui_state["running"] and _http_is_ready(f"http://127.0.0.1:{ui_port}") if ui_state["exists"] else None

    run_status = _fetch_json(f"http://127.0.0.1:{api_port}/api/remote/status") if api_ready else None

    stopped = not any(state["exists"] for state in (db_state, api_state, ui_state))
    healthy = db_ready and api_ready and (ui_ready is not False)
    status_value = "stopped" if stopped else "healthy" if healthy else "errored"

    return {
        "status": status_value,
        "project": _COMPOSE_PROJECT_NAME,
        "services": {
            "db": {**db_state, "ready": db_ready},
            "api": {**api_state, "ready": api_ready},
            "ui": {**ui_state, "ready": ui_ready},
        },
        "run": run_status,
    }


def _service_status(record: dict | None) -> dict:
    if record is None:
        return {"exists": False, "running": False, "state": "missing", "health": ""}
    state = str(record.get("State") or record.get("state") or "").lower()
    health = str(record.get("Health") or record.get("health") or "")
    return {
        "exists": True,
        "running": state == "running",
        "state": state or "unknown",
        "health": health,
    }


def _db_is_ready(compose_command: list[str], *, env: dict[str, str]) -> bool:
    command = compose_command + [
        "exec",
        "-T",
        "mongo",
        "mongosh",
        "--quiet",
        "mongodb://127.0.0.1:27017/admin",
        "--eval",
        "quit(db.runCommand({ ping: 1 }).ok ? 0 : 2)",
    ]
    result = subprocess.run(command, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    return result.returncode == 0


def _http_is_ready(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            return 200 <= response.status < 500
    except (OSError, urllib.error.URLError):
        return False


def _fetch_json(url: str) -> dict | None:
    try:
        with urllib.request.urlopen(url, timeout=3) as response:
            if not 200 <= response.status < 300:
                return None
            return json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return None


def _print_status(ctx: typer.Context, payload: dict, *, api_port: int, ui_port: int) -> None:
    echo(ctx, f"Engine status: {payload['status']}")
    echo(ctx, f"Project: {payload['project']}")
    echo(ctx, "")

    services = payload["services"]
    _print_service_status(ctx, label="Database", service=services["db"], ready_label="running and ready")
    _print_service_status(ctx, label=f"Engine API at http://localhost:{api_port}", service=services["api"], ready_label="ready")
    _print_service_status(ctx, label=f"UI at http://localhost:{ui_port}", service=services["ui"], ready_label="ready")

    run_payload = payload.get("run")
    if not run_payload:
        return

    echo(ctx, "")
    echo(ctx, f"Run: {run_payload.get('run_name', 'unknown')}")
    uptime = run_payload.get("uptime")
    if isinstance(uptime, int):
        echo(ctx, f"Uptime: {_format_duration(uptime)}")

    run_status = run_payload.get("run_status") or {}
    total = run_status.get("total")
    completed = run_status.get("completed")
    if isinstance(total, int) and isinstance(completed, int):
        errored_total = sum(game.get("errored", 0) for game in (run_status.get("per_game") or {}).values())
        error_summary = f" ({errored_total} errored)" if errored_total > 0 else ""
        echo(ctx, f"Assignments: {completed} / {total} completed{error_summary}")
    if "is_open" in run_status:
        echo(ctx, f"Open: {'yes' if run_status['is_open'] else 'no'}")

    per_game = run_status.get("per_game") or {}
    if per_game:
        echo(ctx, "")
        echo(ctx, "Per game:")
        for game_name, counts in sorted(per_game.items()):
            errored = counts.get("errored", 0)
            error_msg = f", {errored} errored" if errored > 0 else ""
            echo(
                ctx,
                f"  {game_name}: {counts.get('completed', 0)} / {counts.get('total', 0)} completed, "
                f"{counts.get('in_progress', 0)} in progress{error_msg}",
            )


def _print_service_status(ctx: typer.Context, *, label: str, service: dict, ready_label: str) -> None:
    if service["ready"] is True:
        echo(ctx, f"✓ {label} {ready_label}", style="success")
    elif not service["exists"]:
        echo(ctx, f"- {label} not running")
    else:
        echo(ctx, f"✖ {label} {service['state']}", style="error")


def _format_duration(seconds: int) -> str:
    minutes, sec = divmod(max(seconds, 0), 60)
    hours, minute = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minute}m {sec}s"
    if minute:
        return f"{minute}m {sec}s"
    return f"{sec}s"
