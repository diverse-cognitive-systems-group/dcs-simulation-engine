"""Docker management."""

from dataclasses import dataclass
from typing import Iterable, Optional

from loguru import logger
from python_on_whales import docker
from python_on_whales.exceptions import DockerException

DOCKER_INSTALL_URL = "https://docs.docker.com/get-docker/"
MONGO_SERVICE_NAME = "mongo"
MONGO_CONTAINER_NAME = "mongodb_container"
MONGO_EXPRESS_SERVICE_NAME = "mongo-express"


class DockerNotInstalled(RuntimeError):
    """Docker CLI is not installed / not found."""


class ServiceManagementError(RuntimeError):
    """Failed to ensure a desired service state (up/down)."""


class ComposeUpFailed(ServiceManagementError):
    """docker compose up failed."""


class ComposeDownFailed(ServiceManagementError):
    """docker compose down failed."""


@dataclass(frozen=True)
class ComposeContext:
    """Compose scope (optional) for -p / -f."""

    project_name: Optional[str] = None
    files: Optional[list[str]] = None


def _compose_kwargs(ctx: ComposeContext) -> dict:
    kw: dict = {}
    if ctx.project_name:
        kw["project_name"] = ctx.project_name
    if ctx.files:
        kw["files"] = ctx.files
    return kw


def check_docker_installed() -> None:
    """Best-effort check that the Docker CLI exists.

    Raises DockerNotInstalled if the docker executable is missing.
    """
    try:
        docker.version()  # lighter than docker.info(), validates CLI availability
    except DockerException as e:
        msg = str(e).lower()
        if "executable file not found" in msg or "no such file or directory" in msg or "not found" in msg:
            raise DockerNotInstalled(str(e)) from e
        # If it's some other failure, we don't block here per desired behavior.


def get_container_ip(container_name: str) -> str:
    """Get the IP address of a running container."""
    c = docker.container.inspect(container_name)
    networks = c.network_settings.networks

    if len(networks) != 1:
        raise RuntimeError(f"Expected exactly 1 network, found {len(networks)}: {list(networks)}")

    return next(iter(networks.values())).ip_address


def get_mongodb_ip() -> str:
    """Get the IP address of the mongo container."""
    return get_container_ip(MONGO_CONTAINER_NAME)


def is_service_running(service: str) -> bool:
    """Return True if the docker compose service has at least one running container."""
    try:
        containers = docker.compose.ps(
            services=[service],
        )

        if not containers:
            logger.debug("docker service '{}' → no containers found", service)
            return False

        for c in containers:
            state = getattr(c, "state", None)
            running = bool(getattr(state, "running", False))
            status = getattr(state, "status", None)
            name = getattr(c, "name", None) or getattr(c, "container_name", None)

            logger.debug(
                "docker service '{}' → container={} running={} status={}",
                service,
                name,
                running,
                status,
            )

            if running:
                return True

        return False

    except DockerException:
        logger.exception("docker service '{}' → DockerException", service)
        return False


def compose_up(services: Iterable[str], *, build: bool = True) -> None:
    """Run `docker compose up` for the given services."""
    try:
        services = list(services)
        logger.info("Starting: {}", ", ".join(services))

        docker.compose.up(
            services=services,
            detach=True,
            build=build,
        )

    except DockerException as e:
        raise ComposeUpFailed(str(e)) from e


def compose_down(services: Iterable[str], *, wipe: bool = False) -> None:
    """Stop docker compose services.

    wipe=False -> stop containers only
    wipe=True  -> down + remove volumes (fresh next start)
    """
    try:
        services = list(services)
        logger.info("Stopping: {}", ", ".join(services))

        if wipe:
            docker.compose.down(
                services=services,
                volumes=True,
                remove_orphans=True,
            )
        else:
            docker.compose.stop(
                services=services,
                timeout=30,
            )

    except DockerException as e:
        raise ComposeDownFailed(str(e)) from e


def ensure_mongo_service_up(*, build: bool = True) -> bool:
    """Ensure mongo + mongo-express are running.

    Returns True if we had to start anything, False if already up.

    Raises ServiceManagementError if we cannot ensure the services are up.
    """
    check_docker_installed()
    services = (MONGO_SERVICE_NAME, MONGO_EXPRESS_SERVICE_NAME)

    to_start = [s for s in services if not is_service_running(s)]
    if to_start:
        try:
            compose_up(to_start, build=build)
        except ComposeUpFailed as e:
            raise ServiceManagementError(f"Failed to start services: {', '.join(to_start)}") from e

    still_down = [s for s in services if not is_service_running(s)]
    if still_down:
        raise ServiceManagementError(f"Services are not running after start attempt: {', '.join(still_down)}")

    return bool(to_start)


def ensure_mongo_service_down(*, wipe: bool = False) -> bool:
    """Ensure mongo + mongo-express are stopped.

    If wipe=True, containers and volumes are removed so next start is fresh.

    Returns True if we had to stop anything, False if already down.
    """
    check_docker_installed()
    services = (MONGO_SERVICE_NAME, MONGO_EXPRESS_SERVICE_NAME)

    to_stop = [s for s in services if is_service_running(s)]
    if to_stop:
        try:
            compose_down(to_stop, wipe=wipe)
        except ComposeDownFailed as e:
            raise ServiceManagementError(f"Failed to stop services: {', '.join(to_stop)}") from e

    still_up = [s for s in services if is_service_running(s)]
    if still_up:
        raise ServiceManagementError(f"Services are still running after stop attempt: {', '.join(still_up)}")

    return bool(to_stop)
