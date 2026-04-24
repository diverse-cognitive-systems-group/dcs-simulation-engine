"""Experiment orchestration for assignment-driven study flows."""

from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml
from dcs_simulation_engine.core.assignment_strategies import get_assignment_strategy
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
        strategy = cls._strategy_for(config=config)
        return await maybe_await(strategy.compute_progress_async(provider=provider, config=config))

    @classmethod
    async def compute_status_async(cls, *, provider: Any, experiment_name: str) -> dict[str, Any]:
        """Compute quota-centric status counts for an experiment."""
        config = cls.get_experiment_config_cached(experiment_name)
        strategy = cls._strategy_for(config=config)
        return await maybe_await(strategy.compute_status_async(provider=provider, config=config))

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
        before_form_names = {form.name for form in config.forms_for_phase(before_or_after="before")}
        after_form_names = {form.name for form in config.forms_for_phase(before_or_after="after")}
        player_forms = await maybe_await(provider.get_player_forms(player_id=player_id, experiment_name=experiment_name))
        submitted_before_keys = set((player_forms.data if player_forms else {}).keys())
        has_submitted_before_forms = not before_form_names or before_form_names.issubset(submitted_before_keys)

        def _pending_post_play_items(assignments: list[AssignmentRecord]) -> list[AssignmentRecord]:
            completed = [item for item in assignments if item.status == "completed"]
            return [item for item in completed if not after_form_names.issubset(set(item.data.get(MongoColumns.FORM_RESPONSES, {}).keys()))]

        player_assignments = await maybe_await(provider.list_assignments(experiment_name=experiment_name, player_id=player_id))
        active_assignment = await maybe_await(provider.get_active_assignment(experiment_name=experiment_name, player_id=player_id))
        pending_post_play_items = _pending_post_play_items(player_assignments)
        pending_post_play = pending_post_play_items[-1] if pending_post_play_items else None
        completed_assignments = [item for item in player_assignments if item.status == "completed"]
        strategy = cls._strategy_for(config=config)
        has_finished_experiment = len(completed_assignments) >= strategy.max_assignments_per_player(config=config)

        is_player_choice = config.assignment_strategy.assignment_mode == "player_choice"
        if active_assignment is None and has_submitted_before_forms and not has_finished_experiment and not is_player_choice:
            player_record = await maybe_await(provider.get_player(player_id=player_id))
            if player_record is not None:
                active_assignment = await cls.get_or_create_assignment_async(
                    provider=provider,
                    experiment_name=config.name,
                    player=player_record,
                )
                player_assignments = await maybe_await(provider.list_assignments(experiment_name=experiment_name, player_id=player_id))
                pending_post_play_items = _pending_post_play_items(player_assignments)
                pending_post_play = pending_post_play_items[-1] if pending_post_play_items else None

        return {
            "active_assignment": active_assignment,
            "pending_post_play": pending_post_play,
            "pending_post_play_ids": [item.assignment_id for item in pending_post_play_items],
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
        if assignment is not None and config.assignment_strategy.assignment_mode == "auto":
            strategy = cls._strategy_for(config=config)
            if hasattr(strategy, "generate_remaining_assignments_async"):
                await strategy.generate_remaining_assignments_async(
                    provider=provider,
                    config=config,
                    player=player_record,
                )
        await cls.store_player_form_payloads_async(
            provider=provider,
            player_id=player_id,
            experiment_name=config.name,
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
        strategy = cls._strategy_for(config=config)
        return await maybe_await(strategy.get_or_create_assignment_async(provider=provider, config=config, player=player))

    @classmethod
    async def start_assignment_session_async(
        cls,
        *,
        provider: Any,
        registry: "SessionRegistry",
        experiment_name: str,
        player: PlayerRecord,
        source: str = "experiment",
        assignment_id: str | None = None,
    ) -> tuple["SessionEntry", AssignmentRecord]:
        """Start or resume gameplay for the requested assignment."""
        from dcs_simulation_engine.api.registry import hydrate_session_async

        assignment: AssignmentRecord | None
        if assignment_id is not None:
            assignment = await cls.get_assignment_for_player_async(
                provider=provider,
                experiment_name=experiment_name,
                player_id=player.id,
                assignment_id=assignment_id,
            )
        else:
            assignment = await maybe_await(provider.get_active_assignment(experiment_name=experiment_name, player_id=player.id))
        if assignment is None:
            raise ValueError("No matching assignment is available for this player.")
        if assignment.status == "completed":
            raise ValueError("Completed assignments cannot be resumed.")

        if assignment.status == "in_progress":
            # Check whether the existing session is still resumable before
            # refusing to start.  If it is paused (in registry or in DB),
            # return it instead of creating a duplicate session.
            existing_session_id = assignment.data.get(MongoColumns.ACTIVE_SESSION_ID)
            if existing_session_id:
                existing_entry = registry.get(existing_session_id)
                if existing_entry is None:
                    existing_entry = await hydrate_session_async(
                        session_id=existing_session_id,
                        player_id=player.id,
                        provider=provider,
                        registry=registry,
                    )
                if existing_entry is not None and not existing_entry.manager.exited:
                    return existing_entry, assignment
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
    async def get_assignment_for_player_async(
        cls,
        *,
        provider: Any,
        experiment_name: str,
        player_id: str,
        assignment_id: str,
    ) -> AssignmentRecord | None:
        """Return one assignment if it belongs to the requested player+experiment."""
        assignment = await maybe_await(provider.get_assignment(assignment_id=assignment_id))
        if assignment is None:
            return None
        if assignment.player_id != player_id or assignment.experiment_name != experiment_name:
            return None
        return assignment

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
        assignment_id: str | None = None,
    ) -> AssignmentRecord:
        """Store all after-play forms on one completed assignment."""
        config = cls.get_experiment_config_cached(experiment_name)
        after_forms = config.forms_for_phase(before_or_after="after")
        if assignment_id is not None:
            assignment = await cls.get_assignment_for_player_async(
                provider=provider,
                experiment_name=config.name,
                player_id=player_id,
                assignment_id=assignment_id,
            )
            if assignment is not None and assignment.status != "completed":
                raise ValueError("Post-play feedback can only be submitted for completed assignments.")
            if assignment is not None:
                after_form_keys = set(assignment.data.get(MongoColumns.FORM_RESPONSES, {}).keys())
                required_after_form_names = {form.name for form in after_forms}
                if required_after_form_names.issubset(after_form_keys):
                    raise ValueError("Post-play feedback has already been submitted for this assignment.")
        else:
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
    async def store_player_form_payloads_async(
        cls,
        *,
        provider: Any,
        player_id: str,
        experiment_name: str,
        forms_payload: dict[str, dict[str, Any]],
    ) -> None:
        """Store one or more named before-play form payloads on the player forms record."""
        for form_key, payload in forms_payload.items():
            await maybe_await(
                provider.set_player_form_response(
                    player_id=player_id,
                    experiment_name=experiment_name,
                    form_key=form_key,
                    response=payload,
                )
            )

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
    async def get_eligible_options_async(
        cls,
        *,
        provider: Any,
        experiment_name: str,
        player: PlayerRecord,
    ) -> list[dict[str, str]]:
        """Return eligible {game_name, character_hid} options for a player in player_choice mode."""
        config = cls.get_experiment_config_cached(experiment_name)
        strategy = cls._strategy_for(config=config)
        get_eligible = getattr(strategy, "get_eligible_options_async", None)
        if get_eligible is None:
            return []
        return await maybe_await(get_eligible(provider=provider, config=config, player=player))

    @classmethod
    async def create_player_choice_assignment_async(
        cls,
        *,
        provider: Any,
        experiment_name: str,
        player: PlayerRecord,
        game_name: str,
        character_hid: str,
    ) -> AssignmentRecord:
        """Create a specific assignment for a player who selected game+character manually."""
        config = cls.get_experiment_config_cached(experiment_name)
        eligible = await cls.get_eligible_options_async(
            provider=provider,
            experiment_name=experiment_name,
            player=player,
        )
        eligible_set = {(opt["game_name"], opt["character_hid"]) for opt in eligible}
        if (game_name, character_hid) not in eligible_set:
            raise ValueError("The selected game and character are not available for assignment.")
        assignment = await maybe_await(
            provider.create_assignment(
                assignment_doc={
                    MongoColumns.EXPERIMENT_NAME: config.name,
                    MongoColumns.PLAYER_ID: player.id,
                    MongoColumns.GAME_NAME: game_name,
                    MongoColumns.CHARACTER_HID: character_hid,
                    MongoColumns.STATUS: "assigned",
                    MongoColumns.FORM_RESPONSES: {},
                },
                allow_concurrent=True,
            )
        )
        if assignment is None:
            raise ValueError("Failed to create the assignment.")
        return assignment

    @classmethod
    def _strategy_for(cls, *, config: ExperimentConfig):
        """Resolve the configured assignment strategy for one experiment."""
        return get_assignment_strategy(config.assignment_strategy.strategy)

    @classmethod
    def _is_completion_reason(cls, reason: str) -> bool:
        normalized = reason.strip().lower().replace(" ", "_")
        completion_reasons = {
            "game_completed",
            "game_complete",
            "max_predictions_reached",
            "player_exited",
        }
        return normalized in completion_reasons or normalized.startswith("stopping_condition_met:")
