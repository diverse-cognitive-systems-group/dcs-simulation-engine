"""HTTP endpoints for listing, creating, updating, and deleting games and characters."""

from dcs_simulation_engine.api.auth import get_provider_from_request
from dcs_simulation_engine.api.models import (
    CharacterSummary,
    CharactersListResponse,
    DeleteCharacterResponse,
    GameSummary,
    GamesListResponse,
    UpsertCharacterRequest,
    UpsertCharacterResponse,
)
from dcs_simulation_engine.helpers.game_helpers import list_games
from fastapi import APIRouter, HTTPException, Request, status

router = APIRouter(prefix="/api", tags=["catalog"])


@router.get("/games/list", response_model=GamesListResponse)
def list_games_endpoint() -> GamesListResponse:
    """List available games."""
    games = [
        GameSummary(name=name, author=author, description=description)
        for name, author, _path, _version, description in list_games()
    ]
    return GamesListResponse(games=games)


@router.get("/characters/list", response_model=CharactersListResponse)
def list_characters_endpoint(request: Request) -> CharactersListResponse:
    """List available characters."""
    provider = get_provider_from_request(request)
    characters = [
        CharacterSummary(hid=c.hid, short_description=c.short_description) for c in provider.list_characters()
    ]
    return CharactersListResponse(characters=characters)


@router.post("/characters", response_model=UpsertCharacterResponse, status_code=status.HTTP_201_CREATED)
def create_character(body: UpsertCharacterRequest, request: Request) -> UpsertCharacterResponse:
    """Create a new character."""
    provider = get_provider_from_request(request)
    character_id = provider.upsert_character(body.data, character_id=body.character_id)
    return UpsertCharacterResponse(character_id=character_id)


@router.put("/characters/{character_id}", response_model=UpsertCharacterResponse)
def update_character(character_id: str, body: UpsertCharacterRequest, request: Request) -> UpsertCharacterResponse:
    """Update an existing character."""
    provider = get_provider_from_request(request)
    updated_id = provider.upsert_character(body.data, character_id=character_id)
    return UpsertCharacterResponse(character_id=updated_id)


@router.delete("/characters/{character_id}", response_model=DeleteCharacterResponse)
def delete_character(character_id: str, request: Request) -> DeleteCharacterResponse:
    """Delete a character by id."""
    provider = get_provider_from_request(request)
    try:
        provider.delete_character(character_id)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    return DeleteCharacterResponse(character_id=character_id)
