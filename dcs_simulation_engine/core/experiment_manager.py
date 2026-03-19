"""Experiment orchestration for assignment-driven study flows."""

import random
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml
from dcs_simulation_engine.core.experiment_config import ExperimentConfig
from dcs_simulation_engine.core.forms import (
    ExperimentForm,
    ExperimentFormQuestion,
)
from dcs_simulation_engine.core.session_manager import SessionManager
from dcs_simulation_engine.dal.base import (
    AssignmentRecord,
    ExperimentRecord,
    PlayerRecord,
)
from dcs_simulation_engine.dal.mongo.const import MongoColumns
from dcs_simulation_engine.helpers.experiment_helpers import get_experiment_config
from dcs_simulation_engine.utils.async_utils import maybe_await
from dcs_simulation_engine.utils.time import utc_now
from loguru import logger

if TYPE_CHECKING:
    from dcs_simulation_engine.api.registry import SessionEntry, SessionRegistry


class ExperimentManager:
    """Loads experiment configs and resolves experiment assignment workflows."""

    _experiment_config_cache: dict[str, ExperimentConfig] = {}

    @classmethod
    def _cache_key(cls, experiment: str) -> str:
        return experiment.strip().lower()

    @classmethod
    def _load_experiment_config_into_cache(cls, experiment: str) -> bool:
        cache_key = cls._cache_key(experiment)
        if cache_key in cls._experiment_config_cache:
            return False
        experiment_config_fpath = get_experiment_config(experiment)
        cls._experiment_config_cache[cache_key] = ExperimentConfig.load(experiment_config_fpath)
        return True

    @classmethod
    def get_experiment_config_cached(cls, experiment: str) -> ExperimentConfig:
        """Return a defensive copy of a cached experiment config."""
        cls._load_experiment_config_into_cache(experiment)
        return cls._experiment_config_cache[cls._cache_key(experiment)].model_copy(deep=True)

    @classmethod
    def preload_experiment_configs(cls) -> int:
        """Load all valid experiment configs from disk into the in-memory cache."""
        experiments_dir = Path(__file__).resolve().parents[2] / "experiments"
        if not experiments_dir.exists() or not experiments_dir.is_dir():
            return 0

        discovered_names: set[str] = set()
        for path in experiments_dir.glob("*.y*ml"):
            try:
                with path.open("r", encoding="utf-8") as handle:
                    doc = yaml.safe_load(handle) or {}
                raw_name = doc.get("name")
                if isinstance(raw_name, str) and raw_name.strip():
                    discovered_names.add(raw_name.strip())
            except Exception:
                logger.debug("Skipping unreadable experiment config while preloading: {}", path, exc_info=True)

        loaded = 0
        for name in discovered_names:
            try:
                if cls._load_experiment_config_into_cache(name):
                    loaded += 1
            except Exception:
                logger.debug("Skipping invalid experiment config '{}' during preload", name, exc_info=True)

        if loaded > 0:
            logger.info("Preloaded {} experiment config(s) into ExperimentManager cache.", loaded)
        return loaded

    @classmethod
    async def ensure_experiment_async(cls, *, provider: Any, experiment_name: str) -> ExperimentRecord:
        """Persist the experiment config snapshot if it is not already stored."""
        config = cls.get_experiment_config_cached(experiment_name)
        existing = await maybe_await(provider.get_experiment(experiment_name=config.name))
        progress = await cls.compute_progress_async(provider=provider, experiment_name=config.name)
        if existing is not None:
            updated = await maybe_await(
                provider.set_experiment_progress(
                    experiment_name=config.name,
                    progress=progress,
                )
            )
            return updated or existing
        return await maybe_await(
            provider.upsert_experiment(
                experiment_name=config.name,
                description=config.description,
                config_snapshot=config.model_dump(mode="json"),
                progress=progress,
            )
        )

    @classmethod
    async def compute_progress_async(cls, *, provider: Any, experiment_name: str) -> dict[str, Any]:
        """Compute finite usability progress from assignment state."""
        config = cls.get_experiment_config_cached(experiment_name)
        if config.assignment_protocol.strategy != "usability_random_unique":
            return {
                "total": 0,
                "completed": 0,
                "is_complete": False,
            }

        completed_assignments = await maybe_await(
            provider.list_assignments(experiment_name=config.name, statuses=["completed"])
        )
        per_game_players: dict[str, set[str]] = defaultdict(set)
        for assignment in completed_assignments:
            per_game_players[assignment.game_name].add(assignment.player_id)

        per_game_counts = {game_name: len(per_game_players.get(game_name, set())) for game_name in config.games}
        quota = int(config.assignment_protocol.quota_per_game or 0)
        return {
            "total": quota * len(config.games),
            "completed": len(completed_assignments),
            "is_complete": all(count >= quota for count in per_game_counts.values()),
        }

    @classmethod
    async def compute_status_async(cls, *, provider: Any, experiment_name: str) -> dict[str, Any]:
        """Compute quota-centric status counts for an experiment."""
        config = cls.get_experiment_config_cached(experiment_name)
        quota = int(config.assignment_protocol.quota_per_game or 0)

        completed_assignments = await maybe_await(
            provider.list_assignments(experiment_name=config.name, statuses=["completed"])
        )
        in_progress_assignments = await maybe_await(
            provider.list_assignments(experiment_name=config.name, statuses=["in_progress"])
        )

        completed_players_by_game: dict[str, set[str]] = defaultdict(set)
        in_progress_players_by_game: dict[str, set[str]] = defaultdict(set)

        for assignment in completed_assignments:
            completed_players_by_game[assignment.game_name].add(assignment.player_id)
        for assignment in in_progress_assignments:
            in_progress_players_by_game[assignment.game_name].add(assignment.player_id)

        per_game: dict[str, dict[str, int]] = {}
        for game_name in config.games:
            per_game[game_name] = {
                "total": quota,
                "completed": len(completed_players_by_game.get(game_name, set())),
                "in_progress": len(in_progress_players_by_game.get(game_name, set())),
            }

        completed_total = sum(item["completed"] for item in per_game.values())
        return {
            "is_open": any(item["completed"] < item["total"] for item in per_game.values()),
            "total": quota * len(config.games),
            "completed": completed_total,
            "per_game": per_game,
        }

    @classmethod
    async def get_player_state_async(
        cls,
        *,
        provider: Any,
        experiment_name: str,
        player_id: str,
    ) -> dict[str, Any]:
        """Return the assignment state visible to one authenticated player."""
        config = cls.get_experiment_config_cached(experiment_name)
        active_assignment = await maybe_await(
            provider.get_active_assignment(experiment_name=experiment_name, player_id=player_id)
        )
        player_assignments = await maybe_await(
            provider.list_assignments(experiment_name=experiment_name, player_id=player_id)
        )
        completed_assignments = [item for item in player_assignments if item.status == "completed"]
        before_form_names = {form.name for form in config.forms_for_phase(before_or_after="before")}
        after_form_names = {form.name for form in config.forms_for_phase(before_or_after="after")}
        has_submitted_before_forms = not before_form_names or any(
            before_form_names.issubset(set(item.data.get(MongoColumns.FORM_RESPONSES, {}).keys()))
            for item in player_assignments
        )
        pending_post_play = next(
            (
                item
                for item in reversed(completed_assignments)
                if not after_form_names.issubset(set(item.data.get(MongoColumns.FORM_RESPONSES, {}).keys()))
            ),
            None,
        )
        has_finished_experiment = len(completed_assignments) >= cls._max_assignments_per_player(config=config)

        if (
            active_assignment is None
            and pending_post_play is None
            and has_submitted_before_forms
            and not has_finished_experiment
        ):
            player_record = await maybe_await(provider.get_player(player_id=player_id))
            if player_record is not None:
                active_assignment = await cls.get_or_create_assignment_async(
                    provider=provider,
                    experiment_name=config.name,
                    player=player_record,
                )

        return {
            "active_assignment": active_assignment,
            "pending_post_play": pending_post_play,
            "has_finished_experiment": has_finished_experiment,
            "has_submitted_before_forms": has_submitted_before_forms,
            "assignments": player_assignments,
        }

    @classmethod
    async def submit_before_play_async(
        cls,
        *,
        provider: Any,
        experiment_name: str,
        player_id: str,
        responses: dict[str, Any],
    ) -> AssignmentRecord | None:
        """Store before-play form answers for an authenticated player and return their assignment."""
        config = cls.get_experiment_config_cached(experiment_name)
        if config.assignment_protocol.strategy != "usability_random_unique":
            raise ValueError(
                f"Experiment strategy '{config.assignment_protocol.strategy}' is not executable in this runtime yet."
            )

        player_record = await maybe_await(provider.get_player(player_id=player_id))
        if player_record is None:
            raise ValueError("Authenticated player could not be loaded.")

        progress = await cls.compute_progress_async(provider=provider, experiment_name=config.name)
        if progress["is_complete"]:
            raise ValueError("This experiment is no longer accepting new participants.")

        before_forms = config.forms_for_phase(before_or_after="before")
        normalized_before_forms = cls.normalize_form_submissions(forms=before_forms, responses=responses)
        await cls.ensure_experiment_async(provider=provider, experiment_name=config.name)
        assignment = await cls.get_or_create_assignment_async(
            provider=provider,
            experiment_name=config.name,
            player=player_record,
        )
        if assignment is not None:
            assignment = await cls.store_form_payloads_async(
                provider=provider,
                assignment_id=assignment.assignment_id,
                forms_payload=normalized_before_forms,
            )
        return assignment

    @classmethod
    async def get_or_create_assignment_async(
        cls,
        *,
        provider: Any,
        experiment_name: str,
        player: PlayerRecord,
    ) -> AssignmentRecord | None:
        """Return the active assignment for a player or create one on demand."""
        config = cls.get_experiment_config_cached(experiment_name)
        if config.assignment_protocol.strategy != "usability_random_unique":
            raise ValueError(
                f"Experiment strategy '{config.assignment_protocol.strategy}' is not executable in this runtime yet."
            )

        active_assignment = await maybe_await(
            provider.get_active_assignment(experiment_name=config.name, player_id=player.id)
        )
        if active_assignment is not None:
            return active_assignment

        player_assignments = await maybe_await(
            provider.list_assignments(experiment_name=config.name, player_id=player.id)
        )
        completed_count = sum(1 for item in player_assignments if item.status == "completed")
        if completed_count >= cls._max_assignments_per_player(config=config):
            return None

        completed_assignments = await maybe_await(
            provider.list_assignments(experiment_name=config.name, statuses=["completed"])
        )
        completed_players_by_game: dict[str, set[str]] = defaultdict(set)
        for assignment in completed_assignments:
            completed_players_by_game[assignment.game_name].add(assignment.player_id)

        assigned_games = {item.game_name for item in player_assignments}
        quota = int(config.assignment_protocol.quota_per_game or 0)
        eligible_games = [
            game_name
            for game_name in config.games
            if game_name not in assigned_games and len(completed_players_by_game.get(game_name, set())) < quota
        ]
        if not eligible_games:
            return None

        game_rng = cls._rng_for(config=config, player_id=player.id, salt="game")
        game_candidates = list(eligible_games)
        game_rng.shuffle(game_candidates)

        for game_name in game_candidates:
            game_config = SessionManager.get_game_config_cached(game_name)
            get_valid = getattr(game_config, "get_valid_characters_async", None)
            if get_valid is None:
                valid_pcs, _ = await maybe_await(
                    game_config.get_valid_characters(player_id=player.id, provider=provider)
                )
            else:
                valid_pcs, _ = await maybe_await(get_valid(player_id=player.id, provider=provider))

            valid_pc_hids = [hid for _, hid in valid_pcs]
            if not valid_pc_hids:
                continue

            pc_rng = cls._rng_for(config=config, player_id=player.id, salt=f"pc:{game_name}")
            character_hid = pc_rng.choice(valid_pc_hids)
            return await maybe_await(
                provider.create_assignment(
                    assignment_doc={
                        MongoColumns.EXPERIMENT_NAME: config.name,
                        MongoColumns.PLAYER_ID: player.id,
                        MongoColumns.GAME_NAME: game_name,
                        MongoColumns.CHARACTER_HID: character_hid,
                        MongoColumns.STATUS: "assigned",
                        MongoColumns.FORM_RESPONSES: {},
                    }
                )
            )

        return None

    @classmethod
    async def start_assignment_session_async(
        cls,
        *,
        provider: Any,
        registry: "SessionRegistry",
        experiment_name: str,
        player: PlayerRecord,
        source: str = "experiment",
    ) -> tuple["SessionEntry", AssignmentRecord]:
        """Start a gameplay session for the current assignment."""
        assignment = await maybe_await(
            provider.get_active_assignment(experiment_name=experiment_name, player_id=player.id)
        )
        if assignment is None:
            raise ValueError("No active assignment is available for this player.")
        if assignment.status == "in_progress":
            raise ValueError("This assignment is already in progress.")

        manager = await SessionManager.create_async(
            game=assignment.game_name,
            provider=provider,
            source=source,
            pc_choice=assignment.character_hid,
            npc_choice=None,
            player_id=player.id,
        )
        entry = registry.add(
            player_id=player.id,
            game_name=assignment.game_name,
            manager=manager,
            experiment_name=experiment_name,
            assignment_id=assignment.assignment_id,
        )
        start_hook = getattr(manager, "start_persistence", None)
        if start_hook is not None:
            await maybe_await(start_hook(session_id=entry.session_id))

        updated_assignment = await maybe_await(
            provider.update_assignment_status(
                assignment_id=assignment.assignment_id,
                status="in_progress",
                active_session_id=entry.session_id,
            )
        )
        if updated_assignment is None:
            raise ValueError("Failed to mark experiment assignment as in progress.")
        return entry, updated_assignment

    @classmethod
    async def handle_session_terminal_state_async(
        cls,
        *,
        provider: Any,
        experiment_name: str,
        assignment_id: str,
        exit_reason: str,
    ) -> AssignmentRecord | None:
        """Map a gameplay terminal reason onto an assignment lifecycle status."""
        status = "completed" if cls._is_completion_reason(exit_reason) else "interrupted"
        updated = await maybe_await(provider.update_assignment_status(assignment_id=assignment_id, status=status))
        if status == "completed":
            await cls.ensure_experiment_async(provider=provider, experiment_name=experiment_name)
        return updated

    @classmethod
    async def store_post_play_async(
        cls,
        *,
        provider: Any,
        experiment_name: str,
        player_id: str,
        responses: dict[str, Any],
    ) -> AssignmentRecord:
        """Store all after-play forms on the latest completed assignment."""
        config = cls.get_experiment_config_cached(experiment_name)
        after_forms = config.forms_for_phase(before_or_after="after")
        state = await cls.get_player_state_async(provider=provider, experiment_name=config.name, player_id=player_id)
        assignment = state["pending_post_play"]
        if assignment is None:
            raise ValueError("No completed assignment is waiting for a post-play response.")

        normalized_after_forms = cls.normalize_form_submissions(forms=after_forms, responses=responses)
        stored = await cls.store_form_payloads_async(
            provider=provider,
            assignment_id=assignment.assignment_id,
            forms_payload=normalized_after_forms,
        )
        if stored is None:
            raise ValueError("Failed to store the post-play response.")
        return stored

    @classmethod
    async def store_form_payloads_async(
        cls,
        *,
        provider: Any,
        assignment_id: str,
        forms_payload: dict[str, dict[str, Any]],
    ) -> AssignmentRecord | None:
        """Store one or more named form payloads on an assignment row."""
        updated: AssignmentRecord | None = None
        for form_name, payload in forms_payload.items():
            updated = await maybe_await(
                provider.set_assignment_form_response(
                    assignment_id=assignment_id,
                    form_key=form_name,
                    response=payload,
                )
            )
        return updated

    @classmethod
    async def get_latest_assignment_for_player_async(cls, *, provider: Any, player_id: str) -> AssignmentRecord | None:
        """Return the latest experiment assignment for a player across all experiments."""
        getter = getattr(provider, "get_latest_experiment_assignment_for_player", None)
        if getter is None:
            return None
        return await maybe_await(getter(player_id=player_id))

    @classmethod
    def normalize_form_submissions(
        cls,
        *,
        forms: list[ExperimentForm],
        responses: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        """Validate and normalize submitted answers for one or more named forms."""
        if not isinstance(responses, dict):
            raise ValueError("Form responses must be submitted as a JSON object.")

        normalized: dict[str, dict[str, Any]] = {}
        for form in forms:
            raw_answers = responses.get(form.name, {})
            if raw_answers is None:
                raw_answers = {}
            if not isinstance(raw_answers, dict):
                raise ValueError(f"Responses for form '{form.name}' must be submitted as an object.")

            normalized_answers: dict[str, Any] = {}
            for question in form.questions:
                if question.answer_type is None:
                    continue
                raw_value = raw_answers.get(question.key or "")
                answer = cls._normalize_question_answer(question=question, raw_value=raw_value)
                normalized_answers[question.key or ""] = {
                    "key": question.key,
                    "prompt": question.prompt,
                    "answer_type": question.answer_type,
                    "required": question.required,
                    "answer": answer,
                }

            normalized[form.name] = {
                "form_name": form.name,
                "before_or_after": form.before_or_after,
                "submitted_at": utc_now(),
                "answers": normalized_answers,
            }
        return normalized

    @classmethod
    def _normalize_question_answer(cls, *, question: ExperimentFormQuestion, raw_value: Any) -> Any:
        answer_type = question.answer_type
        if answer_type is None:
            return None

        if raw_value in (None, ""):
            if answer_type == "bool":
                if question.required and raw_value is None:
                    raise ValueError(f"Missing required form field: {question.key}")
                return bool(raw_value)
            if answer_type == "multi_choice":
                if question.required and raw_value in (None, ""):
                    raise ValueError(f"Missing required form field: {question.key}")
                return []
            if question.required:
                raise ValueError(f"Missing required form field: {question.key}")
            return ""

        if answer_type in {"string", "email", "phone"}:
            value = str(raw_value).strip()
            if question.required and not value:
                raise ValueError(f"Missing required form field: {question.key}")
            return value

        if answer_type == "number":
            if isinstance(raw_value, bool):
                raise ValueError(f"Invalid numeric value for form field: {question.key}")
            if isinstance(raw_value, (int, float)):
                return raw_value
            text = str(raw_value).strip()
            if "." in text:
                return float(text)
            return int(text)

        if answer_type == "bool":
            if isinstance(raw_value, bool):
                return raw_value
            text = str(raw_value).strip().lower()
            if text in {"true", "1", "yes", "on"}:
                return True
            if text in {"false", "0", "no", "off"}:
                return False
            raise ValueError(f"Invalid boolean value for form field: {question.key}")

        if answer_type == "single_choice":
            value = str(raw_value).strip()
            options = [str(option) for option in question.options or []]
            if value not in options:
                raise ValueError(f"Invalid option for form field: {question.key}")
            return value

        if answer_type == "multi_choice":
            values = raw_value if isinstance(raw_value, list) else [raw_value]
            normalized_values = [str(item).strip() for item in values if str(item).strip()]
            options = [str(option) for option in question.options or []]
            invalid_values = [item for item in normalized_values if item not in options]
            if invalid_values:
                raise ValueError(f"Invalid option for form field: {question.key}")
            if question.required and not normalized_values:
                raise ValueError(f"Missing required form field: {question.key}")
            return normalized_values

        raise ValueError(f"Unsupported form field type: {answer_type}")

    @classmethod
    def _rng_for(cls, *, config: ExperimentConfig, player_id: str, salt: str) -> random.Random:
        seed_value = config.assignment_protocol.seed or config.name
        return random.Random(f"{seed_value}:{player_id}:{salt}")

    @classmethod
    def _max_assignments_per_player(cls, *, config: ExperimentConfig) -> int:
        configured = config.assignment_protocol.max_assignments_per_player
        if configured is None:
            return len(config.games)
        return min(int(configured), len(config.games))

    @classmethod
    def _is_completion_reason(cls, reason: str) -> bool:
        normalized = reason.strip().lower().replace(" ", "_")
        return normalized in {"game_completed", "game_complete"} or normalized.startswith("stopping_condition_met:")
