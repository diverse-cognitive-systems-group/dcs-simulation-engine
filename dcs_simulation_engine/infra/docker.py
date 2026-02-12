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


class ComposeUpFailed(RuntimeError):
    """docker compose up failed (daemon down, compose missing, bad config, etc.)."""


class ServiceNotRunning(RuntimeError):
    """A required compose service is still not running after attempting to start."""


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
        if (
            "executable file not found" in msg
            or "no such file or directory" in msg
            or "not found" in msg
        ):
            raise DockerNotInstalled(str(e)) from e
        # If it's some other failure, we don't block here per desired behavior.


def get_container_ip(container_name: str) -> str:
    """Get the IP address of a running container."""
    c = docker.container.inspect(container_name)
    networks = c.network_settings.networks

    if len(networks) != 1:
        raise RuntimeError(
            f"Expected exactly 1 network, found {len(networks)}: {list(networks)}"
        )

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
    """Run `docker compose up` for the given services in the given context."""
    try:
        logger.info("Starting: {}", ", ".join(services))
        docker.compose.up(
            services=list(services),
            detach=True,
            build=build,
        )
    except DockerException as e:
        raise ComposeUpFailed(str(e)) from e


def ensure_mongo_running() -> bool:
    """Ensure mongo + mongo-express are running.

    Returns:
        True if any services were started, False if everything was already running.

    Raises:
        DockerNotInstalled, ComposeUpFailed, ServiceNotRunning
    """
    check_docker_installed()

    services = (MONGO_SERVICE_NAME, MONGO_EXPRESS_SERVICE_NAME)

    not_running = [s for s in services if not is_service_running(s)]
    if not_running:
        logger.info("Starting docker services: {}", ", ".join(not_running))
        compose_up(not_running)

    still_down = [s for s in services if not is_service_running(s)]
    if still_down:
        raise ServiceNotRunning(", ".join(still_down))

    return bool(not_running)
