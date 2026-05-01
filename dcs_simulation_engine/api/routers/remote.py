"""Remote deployment bootstrap, status, and export endpoints."""

import asyncio
import secrets
import shutil
import tarfile
import tempfile
import zipfile
from pathlib import Path
from typing import Literal

from dcs_simulation_engine.api.auth import (
    REMOTE_ADMIN_ROLE,
    api_key_from_request,
    get_default_experiment_name_from_request,
    get_provider_from_request,
    has_remote_admin_async,
    require_remote_admin_async,
    require_remote_management_from_request,
    resolve_remote_deployment_mode,
)
from dcs_simulation_engine.api.models import (
    ExperimentGameStatusResponse,
    ExperimentProgressResponse,
    ExperimentStatusResponse,
    RemoteBootstrapResponse,
    RemoteStatusResponse,
)
from dcs_simulation_engine.cli.bootstrap import create_provider_admin
from dcs_simulation_engine.core.engine_run_manager import EngineRunManager
from dcs_simulation_engine.dal.mongo.util import dump_all_collections_to_json_async
from dcs_simulation_engine.utils.async_utils import maybe_await
from dcs_simulation_engine.utils.auth import validate_access_key
from dcs_simulation_engine.utils.time import utc_now
from fastapi import APIRouter, HTTPException, Request, status
from loguru import logger
from starlette.background import BackgroundTask
from starlette.responses import FileResponse

router = APIRouter(prefix="/api/remote", tags=["remote"])


def _require_bootstrap_token(request: Request) -> None:
    """Validate the one-time bootstrap token for remote deployment initialization."""
    configured = getattr(request.app.state, "bootstrap_token", None)
    if not configured:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Remote bootstrap is not enabled for this deployment.",
        )

    provided = request.headers.get("x-dcs-bootstrap-token", "")
    if not provided or not secrets.compare_digest(provided, configured):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bootstrap token")


def _requested_admin_key(request: Request) -> str | None:
    """Return the optional requested admin key after validation."""
    raw_key = request.headers.get("x-dcs-admin-key", "").strip()
    if not raw_key:
        return None
    try:
        return validate_access_key(raw_key)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


def _progress_response(progress: dict) -> ExperimentProgressResponse:
    """Convert raw experiment progress into the API response model."""
    return ExperimentProgressResponse(
        total=int(progress["total"]),
        completed=int(progress["completed"]),
        is_complete=bool(progress["is_complete"]),
    )


def _status_response(status_payload: dict) -> ExperimentStatusResponse:
    """Convert raw experiment status into the API response model."""
    return ExperimentStatusResponse(
        is_open=bool(status_payload["is_open"]),
        total=int(status_payload["total"]),
        completed=int(status_payload["completed"]),
        per_game={
            str(game_name): ExperimentGameStatusResponse(
                total=int(counts["total"]),
                completed=int(counts["completed"]),
                in_progress=int(counts["in_progress"]),
            )
            for game_name, counts in dict(status_payload["per_game"]).items()
        },
    )


def _archive_dump_dir(dump_root: Path, archive_path: Path, archive_format: Literal["tar.gz", "zip"]) -> None:
    """Create an archive from a dump directory."""
    if archive_format == "zip":
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for file_path in dump_root.rglob("*"):
                if file_path.is_file():
                    archive.write(file_path, arcname=file_path.relative_to(dump_root.parent))
        return

    with tarfile.open(archive_path, "w:gz") as archive:
        archive.add(dump_root, arcname=dump_root.name)


def _safe_extract_path(root: Path, member_name: str) -> Path:
    """Return the resolved extraction target and reject path traversal."""
    if not member_name.strip():
        raise ValueError("Seed archive contains an empty path.")

    candidate = (root / member_name).resolve()
    root_resolved = root.resolve()
    if candidate != root_resolved and root_resolved not in candidate.parents:
        raise ValueError("Seed archive contains an unsafe path.")
    return candidate


def _extract_seed_zip(archive_path: Path, extract_root: Path) -> None:
    """Safely extract a zip archive into the given directory."""
    with zipfile.ZipFile(archive_path) as archive:
        for member in archive.infolist():
            target = _safe_extract_path(extract_root, member.filename)
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)


def _extract_seed_tar(archive_path: Path, extract_root: Path) -> None:
    """Safely extract a tar archive into the given directory."""
    with tarfile.open(archive_path) as archive:
        for member in archive.getmembers():
            target = _safe_extract_path(extract_root, member.name)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                raise ValueError("Seed archive may only contain regular files and directories.")
            target.parent.mkdir(parents=True, exist_ok=True)
            src = archive.extractfile(member)
            if src is None:
                raise ValueError(f"Could not read archived file: {member.name}")
            with src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)


def _materialize_uploaded_seed(upload_path: Path, temp_root: Path) -> Path:
    """Return a seed directory ready for import from one uploaded local artifact."""
    seed_root = temp_root / "seed"
    seed_root.mkdir(parents=True, exist_ok=True)
    lower_name = upload_path.name.lower()

    if lower_name.endswith(".zip"):
        _extract_seed_zip(upload_path, seed_root)
        return seed_root
    if lower_name.endswith((".tar.gz", ".tgz", ".tar")):
        _extract_seed_tar(upload_path, seed_root)
        return seed_root
    if upload_path.suffix.lower() in {".json", ".ndjson"}:
        shutil.copy2(upload_path, seed_root / upload_path.name)
        return seed_root

    raise ValueError("mongo_seed must be a .zip/.tar.gz/.tgz/.tar archive, a .json/.ndjson file, or a dumped folder.")


async def _write_bootstrap_payload(request: Request, upload_path: Path) -> None:
    """Persist the raw bootstrap request body to disk."""
    with upload_path.open("wb") as dst:
        async for chunk in request.stream():
            if chunk:
                dst.write(chunk)


def _seed_remote_database(*, mongo_uri: str, seed_dir: Path) -> None:
    """Seed the remote Mongo instance using the selected packaged profile."""
    create_provider_admin(mongo_uri=mongo_uri).seed_database(seed_dir)


@router.post("/bootstrap", response_model=RemoteBootstrapResponse)
async def bootstrap_remote_deployment(request: Request) -> RemoteBootstrapResponse:
    """Seed the uploaded database snapshot and provision the remote admin access key."""
    require_remote_management_from_request(
        request,
        detail="Remote bootstrap is unavailable when the server is not remote-managed.",
    )
    _require_bootstrap_token(request)
    provider = get_provider_from_request(request)
    requested_admin_key = _requested_admin_key(request)

    if await has_remote_admin_async(provider=provider):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Remote deployment has already been bootstrapped.",
        )

    mongo_uri = getattr(request.app.state, "mongo_uri", None)
    if not mongo_uri:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Mongo URI is unavailable for remote bootstrap.",
        )

    filename = Path(request.headers.get("x-dcs-mongo-seed-filename") or "").name
    if not filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing X-DCS-Mongo-Seed-Filename header.",
        )

    temp_root = Path(tempfile.mkdtemp(prefix="dcs-remote-bootstrap-"))
    try:
        upload_path = temp_root / filename
        await _write_bootstrap_payload(request, upload_path)
        try:
            seed_dir = await asyncio.to_thread(_materialize_uploaded_seed, upload_path, temp_root)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

        await asyncio.to_thread(_seed_remote_database, mongo_uri=mongo_uri, seed_dir=seed_dir)
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)

    record, api_key = await maybe_await(
        provider.create_player(
            player_data={
                "display_name": "Remote Admin",
                "role": REMOTE_ADMIN_ROLE,
            },
            issue_access_key=requested_admin_key is None,
            access_key=requested_admin_key,
        )
    )
    if api_key is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to issue admin key")

    experiment_name = get_default_experiment_name_from_request(request)
    if experiment_name:
        await EngineRunManager.ensure_experiment_async(provider=provider, experiment_name=experiment_name)

    return RemoteBootstrapResponse(
        player_id=record.id,
        admin_api_key=api_key,
        experiment_name=experiment_name,
    )


@router.get("/status", response_model=RemoteStatusResponse)
async def remote_status(request: Request) -> RemoteStatusResponse:
    """Return a public status summary for remote-managed experiment deployments."""
    started_at = request.app.state.started_at
    uptime = int((utc_now() - started_at).total_seconds())
    default_experiment_name = get_default_experiment_name_from_request(request)
    provider = get_provider_from_request(request)

    progress = None
    experiment_status = None
    if default_experiment_name:
        try:
            await EngineRunManager.ensure_experiment_async(provider=provider, experiment_name=default_experiment_name)
            progress = _progress_response(
                await EngineRunManager.compute_progress_async(
                    provider=provider,
                    experiment_name=default_experiment_name,
                )
            )
            experiment_status = _status_response(
                await EngineRunManager.compute_status_async(provider=provider, experiment_name=default_experiment_name)
            )
        except Exception as exc:
            logger.exception("Failed to compute remote status for {}", default_experiment_name)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to compute remote status: {exc}",
            ) from exc

    return RemoteStatusResponse(
        mode=resolve_remote_deployment_mode(
            default_experiment_name=default_experiment_name,
        ),
        started_at=started_at,
        uptime=max(uptime, 0),
        experiment_name=default_experiment_name,
        progress=progress,
        experiment_status=experiment_status,
    )


@router.get("/db-export")
async def export_remote_database(
    request: Request,
    format: Literal["tar.gz", "zip"] = "tar.gz",
) -> FileResponse:
    """Stream an archive of the current database state to the remote admin."""
    require_remote_management_from_request(
        request,
        detail="Remote database export is unavailable when the server is not remote-managed.",
    )
    provider = get_provider_from_request(request)
    await require_remote_admin_async(provider=provider, api_key=api_key_from_request(request))

    temp_root = Path(tempfile.mkdtemp(prefix="dcs-remote-export-"))
    dump_root = await dump_all_collections_to_json_async(provider.get_db(), temp_root)
    archive_suffix = ".zip" if format == "zip" else ".tar.gz"
    archive_path = temp_root / f"{dump_root.name}{archive_suffix}"
    await asyncio.to_thread(_archive_dump_dir, dump_root, archive_path, format)

    experiment_name = get_default_experiment_name_from_request(request) or "dcs-db"
    filename = f"{experiment_name}-{utc_now().strftime('%Y%m%d-%H%M%S')}{archive_suffix}"
    return FileResponse(
        archive_path,
        media_type="application/zip" if format == "zip" else "application/gzip",
        filename=filename,
        background=BackgroundTask(shutil.rmtree, temp_root, ignore_errors=True),
    )
