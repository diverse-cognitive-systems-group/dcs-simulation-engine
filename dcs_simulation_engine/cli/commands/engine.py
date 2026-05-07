"""CLI commands for managing the local Docker Compose engine stack."""

import json
import os
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

import typer
import yaml
from dcs_simulation_engine.api.app import DEFAULT_RUN_CONFIG_PATH
from dcs_simulation_engine.cli.common import echo

_CONTAINER_RUN_CONFIG_PATH = "/app/run_config.yml"
_COMPOSE_PROJECT_NAME = "dcs"

engine_app = typer.Typer(help="Start, stop, and inspect the local DCS engine stack.")


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
    """Start the local DCS engine with Docker Compose."""
    repo_root = _find_repo_root(Path.cwd())
    if repo_root is None:
        echo(
            ctx,
            "dcs engine start currently requires a repository checkout with compose.yml. Installed-package runs are coming later.",
            style="error",
        )
        raise typer.Exit(code=1)

    config_path = config.expanduser().resolve()
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
        repo_root=repo_root,
        api_port=api_port,
        ui_port=ui_port,
        db_port=db_port,
    )

    with tempfile.TemporaryDirectory(prefix="dcs-engine-") as temp_dir:
        override_path = Path(temp_dir) / "compose.engine.yml"
        _write_run_config_override(
            override_path=override_path,
            host_config_path=_host_path_for_docker(config_path, repo_root=repo_root),
        )
        compose_command = _compose_command(repo_root=repo_root)
        startup_compose_command = _compose_command(repo_root=repo_root, override_path=override_path)
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
    """Stop the local DCS engine Docker Compose stack."""
    repo_root = _find_repo_root(Path.cwd())
    if repo_root is None:
        echo(
            ctx,
            "dcs engine stop currently requires a repository checkout with compose.yml. Installed-package runs are coming later.",
            style="error",
        )
        raise typer.Exit(code=1)

    _ensure_docker_ready(ctx)
    compose_command = _compose_command(repo_root=repo_root)
    down_command = compose_command + ["down"]
    if clean:
        down_command.append("--volumes")

    try:
        _run_checked(
            down_command,
            env=_stop_env(repo_root=repo_root),
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
    """Show local engine service health and run progress."""
    repo_root = _find_repo_root(Path.cwd())
    if repo_root is None:
        echo(
            ctx,
            "dcs engine status currently requires a repository checkout with compose.yml. Installed-package runs are coming later.",
            style="error",
        )
        raise typer.Exit(code=1)

    _ensure_docker_ready(ctx)
    env = _stop_env(repo_root=repo_root)
    compose_command = _compose_command(repo_root=repo_root)
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


def _find_repo_root(start: Path) -> Path | None:
    for path in [start, *start.parents]:
        if (path / "compose.yml").is_file() and (path / "docker").is_dir():
            return path
    return None


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


def _compose_env(*, repo_root: Path, api_port: int, ui_port: int, db_port: int) -> dict[str, str]:
    env = os.environ.copy()
    env["DCS_RUN_CONFIG"] = _CONTAINER_RUN_CONFIG_PATH
    env["DCS_API_PORT"] = str(api_port)
    env["DCS_UI_PORT"] = str(ui_port)
    env["DCS_DB_PORT"] = str(db_port)
    env.setdefault("DCS_RUNS_DIR", str(repo_root / "runs"))
    return env


def _stop_env(*, repo_root: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("DCS_RUNS_DIR", str(repo_root / "runs"))
    env.setdefault("OPENROUTER_API_KEY", "unused-for-engine-stop")
    return env


def _host_path_for_docker(config_path: Path, *, repo_root: Path) -> Path:
    runs_dir = os.getenv("DCS_RUNS_DIR", "").strip()
    if not runs_dir:
        return config_path

    host_runs_dir = Path(runs_dir).expanduser()
    if not host_runs_dir.is_absolute():
        return config_path

    try:
        relative_path = config_path.relative_to(repo_root)
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


def _compose_command(*, repo_root: Path, override_path: Path | None = None) -> list[str]:
    command = [
        "docker",
        "compose",
        "-f",
        str(repo_root / "compose.yml"),
        "--project-directory",
        str(repo_root),
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
        echo(ctx, f"Assignments: {completed} / {total} completed")
    if "is_open" in run_status:
        echo(ctx, f"Open: {'yes' if run_status['is_open'] else 'no'}")

    per_game = run_status.get("per_game") or {}
    if per_game:
        echo(ctx, "")
        echo(ctx, "Per game:")
        for game_name, counts in sorted(per_game.items()):
            echo(
                ctx,
                f"  {game_name}: {counts.get('completed', 0)} / {counts.get('total', 0)} completed, "
                f"{counts.get('in_progress', 0)} in progress",
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
