"""Engine-run orchestration for assignment-driven flows."""

from typing import TYPE_CHECKING, Any

from dcs_simulation_engine.core.assignment_strategies import get_assignment_strategy
from dcs_simulation_engine.core.assignment_strategies.base import AssignmentCandidate
from dcs_simulation_engine.core.forms import (
    Form,
    FormQuestion,
    FormTriggerEvent,
)
from dcs_simulation_engine.core.run_config import RunConfig
from dcs_simulation_engine.core.session_manager import SessionManager
from dcs_simulation_engine.dal.base import (
    AssignmentRecord,
    PlayerRecord,
    RunRecord,
)
from dcs_simulation_engine.dal.mongo.const import MongoColumns
from dcs_simulation_engine.utils.async_utils import maybe_await
from dcs_simulation_engine.utils.time import utc_now

if TYPE_CHECKING:
    from dcs_simulation_engine.api.registry import SessionEntry, SessionRegistry


class EngineRunManager:
    """Resolves assignment workflows for the single configured engine run."""

    _run_config: RunConfig | None = None

    def __init__(self, run_config: RunConfig, provider: Any | None = None) -> None:
        """Initialize the manager with the active run config and optional provider."""
        self.run_config = run_config
        self.provider = provider
        type(self)._run_config = run_config

    @classmethod
    def get_run_config(cls) -> RunConfig:
        """Return the active run config."""
        if cls._run_config is None:
            raise RuntimeError("EngineRunManager has not been configured with a RunConfig.")
        return cls._run_config

    @classmethod
    async def ensure_run_async(cls, *, provider: Any) -> RunRecord:
        """Persist the run config snapshot if it is not already stored."""
        config = cls.get_run_config()
        existing = await maybe_await(provider.get_run())
        progress = await cls.compute_progress_async(provider=provider)
        if existing is not None:
            updated = await maybe_await(provider.set_run_progress(progress=progress))
            return updated or existing
        return await maybe_await(
            provider.upsert_run(
                name=config.name,
                description=config.description,
                config_snapshot=config.model_dump(mode="json"),
                progress=progress,
            )
        )

    @classmethod
    async def compute_progress_async(cls, *, provider: Any) -> dict[str, Any]:
        """Compute finite usability progress from assignment state."""
        config = cls.get_run_config()
        strategy = cls._strategy_for(config=config)
        return await maybe_await(strategy.compute_progress_async(provider=provider, config=config))

    @classmethod
    async def compute_status_async(cls, *, provider: Any) -> dict[str, Any]:
        """Compute quota-centric status counts for a run."""
        config = cls.get_run_config()
        strategy = cls._strategy_for(config=config)
        return await maybe_await(strategy.compute_status_async(provider=provider, config=config))

    @classmethod
    async def get_player_state_async(
        cls,
        *,
        provider: Any,
        player_id: str,
    ) -> dict[str, Any]:
        """Return the assignment state visible to one authenticated player."""
        config = cls.get_run_config()
        player_assignments = await maybe_await(provider.list_assignments(player_id=player_id))
        active_assignment = await maybe_await(provider.get_active_assignment(player_id=player_id))
        completed_assignments = [item for item in player_assignments if item.status == "completed"]
        strategy = cls._strategy_for(config=config)
        has_finished_run = len(completed_assignments) >= strategy.max_assignments_per_player(config=config)
        eligible_assignment_options: list[dict[str, str]] = []
        pending_form_groups = await cls.pending_form_groups_async(
            provider=provider,
            config=config,
            player_id=player_id,
            assignments=player_assignments,
            active_assignment=active_assignment,
            has_finished_run=has_finished_run,
        )

        if not cls._blocks_assignment_resolution(pending_form_groups) and not has_finished_run:
            player_record = await maybe_await(provider.get_player(player_id=player_id))
            if player_record is not None:
                active_assignment, eligible_assignment_options = await cls.resolve_assignment_state_async(
                    provider=provider,
                    player=player_record,
                    player_assignments=player_assignments,
                    active_assignment=active_assignment,
                )
                player_assignments = await maybe_await(provider.list_assignments(player_id=player_id))
                completed_assignments = [item for item in player_assignments if item.status == "completed"]
                has_finished_run = len(completed_assignments) >= strategy.max_assignments_per_player(config=config)
                pending_form_groups = await cls.pending_form_groups_async(
                    provider=provider,
                    config=config,
                    player_id=player_id,
                    assignments=player_assignments,
                    active_assignment=active_assignment,
                    has_finished_run=has_finished_run,
                )

        pending_assignment_form_items = [
            assignment
            for assignment in player_assignments
            if any(
                group["trigger"]["event"] == "after_assignment" and group.get("assignment_id") == assignment.assignment_id
                for group in pending_form_groups
            )
        ]

        return {
            "active_assignment": active_assignment,
            "pending_assignment_form_ids": [item.assignment_id for item in pending_assignment_form_items],
            "has_finished_run": has_finished_run,
            "eligible_assignment_options": eligible_assignment_options,
            "pending_form_groups": pending_form_groups,
            "assignments": await maybe_await(provider.list_assignments(player_id=player_id)),
        }

    @classmethod
    async def pending_form_groups_async(
        cls,
        *,
        provider: Any,
        config: RunConfig,
        player_id: str,
        assignments: list[AssignmentRecord] | None = None,
        active_assignment: AssignmentRecord | None = None,
        has_finished_run: bool | None = None,
    ) -> list[dict[str, Any]]:
        """Return actionable form groups still required for a player."""
        if assignments is None:
            assignments = await maybe_await(provider.list_assignments(player_id=player_id))
        if active_assignment is None:
            active_assignment = await maybe_await(provider.get_active_assignment(player_id=player_id))
        if has_finished_run is None:
            strategy = cls._strategy_for(config=config)
            completed_count = sum(1 for item in assignments if item.status == "completed")
            has_finished_run = completed_count >= strategy.max_assignments_per_player(config=config)

        groups: list[dict[str, Any]] = []
        player_forms = await maybe_await(provider.get_player_forms(player_id=player_id))
        submitted_player_form_names = set((player_forms.data if player_forms else {}).keys())
        groups.extend(
            cls._pending_player_form_group(
                config=config,
                event="before_all_assignments",
                submitted_form_names=submitted_player_form_names,
            )
        )

        for assignment in assignments:
            if assignment.status in {"assigned", "interrupted"}:
                groups.extend(cls._pending_assignment_form_group(config=config, event="before_assignment", assignment=assignment))
            if assignment.status == "completed":
                groups.extend(cls._pending_assignment_form_group(config=config, event="after_assignment", assignment=assignment))

        if has_finished_run:
            groups.extend(
                cls._pending_player_form_group(
                    config=config,
                    event="after_all_assignments",
                    submitted_form_names=submitted_player_form_names,
                )
            )

        return groups

    @classmethod
    def _pending_player_form_group(
        cls,
        *,
        config: RunConfig,
        event: FormTriggerEvent,
        submitted_form_names: set[str],
    ) -> list[dict[str, Any]]:
        forms = config.forms_for_trigger(event=event)
        if not forms:
            return []
        required_names = {form.name for form in forms}
        if required_names.issubset(submitted_form_names):
            return []
        return [
            {
                "group_id": event,
                "trigger": {"event": event, "match": None},
                "forms": forms,
            }
        ]

    @classmethod
    def _pending_assignment_form_group(
        cls,
        *,
        config: RunConfig,
        event: FormTriggerEvent,
        assignment: AssignmentRecord,
    ) -> list[dict[str, Any]]:
        forms = config.forms_for_trigger(event=event)
        if not forms:
            return []
        submitted = set(assignment.data.get(MongoColumns.FORM_RESPONSES, {}).keys())
        required_names = {form.name for form in forms}
        if required_names.issubset(submitted):
            return []
        return [
            {
                "group_id": f"{event}:{assignment.assignment_id}",
                "trigger": {"event": event, "match": None},
                "assignment_id": assignment.assignment_id,
                "forms": forms,
            }
        ]

    @classmethod
    def _blocks_assignment_resolution(cls, pending_form_groups: list[dict[str, Any]]) -> bool:
        blocking_events = {"before_all_assignments", "after_assignment", "after_all_assignments"}
        return any(group["trigger"]["event"] in blocking_events for group in pending_form_groups)

    @classmethod
    def _blocks_assignment_start(cls, *, pending_form_groups: list[dict[str, Any]], assignment_id: str) -> bool:
        for group in pending_form_groups:
            event = group["trigger"]["event"]
            if event in {"before_all_assignments", "after_assignment", "after_all_assignments"}:
                return True
            if event == "before_assignment" and group.get("assignment_id") == assignment_id:
                return True
        return False

    @classmethod
    async def resolve_assignment_state_async(
        cls,
        *,
        provider: Any,
        player: PlayerRecord,
        player_assignments: list[AssignmentRecord] | None = None,
        active_assignment: AssignmentRecord | None = None,
    ) -> tuple[AssignmentRecord | None, list[dict[str, str]]]:
        """Return the current assignment or selectable next options for a player."""
        config = cls.get_run_config()
        strategy = cls._strategy_for(config=config)
        assignments = player_assignments
        if assignments is None:
            assignments = await maybe_await(provider.list_assignments(player_id=player.id))
        pending_groups = await cls.pending_form_groups_async(
            provider=provider,
            config=config,
            player_id=player.id,
            assignments=assignments,
            active_assignment=active_assignment,
        )
        if cls._blocks_assignment_resolution(pending_groups):
            return None, []
        current = cls._current_assignment_from_policy(
            config=config,
            assignments=assignments,
            active_assignment=active_assignment,
        )
        if current is not None:
            return current, []

        completed_count = sum(1 for item in assignments if item.status == "completed")
        if completed_count >= strategy.max_assignments_per_player(config=config):
            return None, []

        candidates = await maybe_await(strategy.list_candidate_assignments_async(provider=provider, config=config, player=player))
        if not candidates:
            return None, []

        if config.assignment_strategy.allow_choice_if_multiple and len(candidates) > 1:
            return None, [cls._candidate_to_option(candidate) for candidate in candidates]

        assignment = await maybe_await(
            provider.create_assignment(
                assignment_doc=cls._assignment_doc_for_candidate(config=config, player=player, candidate=candidates[0]),
                allow_concurrent=cls._allow_concurrent_assignment(config=config, assignments=assignments),
            )
        )
        return assignment, []

    @classmethod
    def _current_assignment_from_policy(
        cls,
        *,
        config: RunConfig,
        assignments: list[AssignmentRecord],
        active_assignment: AssignmentRecord | None,
    ) -> AssignmentRecord | None:
        if config.assignment_strategy.require_completion:
            if active_assignment is not None and active_assignment.status == "in_progress":
                return active_assignment
            for assignment in assignments:
                if assignment.status == "in_progress":
                    return assignment
            if active_assignment is not None:
                return active_assignment
            for assignment in assignments:
                if assignment.status in {"assigned", "interrupted"}:
                    return assignment
            return None
        if active_assignment is not None and active_assignment.status == "assigned":
            return active_assignment
        for assignment in assignments:
            if assignment.status == "assigned":
                return assignment
        return None

    @classmethod
    def _allow_concurrent_assignment(cls, *, config: RunConfig, assignments: list[AssignmentRecord]) -> bool:
        return not config.assignment_strategy.require_completion

    @classmethod
    def _candidate_to_option(cls, candidate: AssignmentCandidate) -> dict[str, str]:
        return {
            "game_name": candidate.game_name,
            "pc_hid": candidate.pc_hid,
            "npc_hid": candidate.npc_hid,
        }

    @classmethod
    async def assignment_display_metadata_async(
        cls,
        *,
        provider: Any,
        game_name: str,
        pc_hid: str,
        npc_hid: str,
    ) -> dict[str, Any]:
        """Return display metadata for an assignment triplet."""
        game_config = SessionManager.get_game_config_cached(game_name)
        pc = await maybe_await(provider.get_character(hid=pc_hid))
        npc = await maybe_await(provider.get_character(hid=npc_hid))
        show_simulator_details = cls._game_shows_simulator_details(game_config=game_config)
        simulator_description = npc.short_description or ""
        if not show_simulator_details:
            simulator_description = "Details hidden"
        return {
            "game_description": game_config.description or "",
            "player_character_name": pc.name or pc.hid,
            "player_character_description": pc.short_description or "",
            "simulator_character_description": simulator_description,
            "simulator_character_details_visible": show_simulator_details,
        }

    @classmethod
    async def enrich_assignment_option_async(
        cls,
        *,
        provider: Any,
        option: dict[str, str],
    ) -> dict[str, Any]:
        """Attach display metadata to an assignment option."""
        metadata = await cls.assignment_display_metadata_async(
            provider=provider,
            game_name=option["game_name"],
            pc_hid=option["pc_hid"],
            npc_hid=option["npc_hid"],
        )
        return {**option, **metadata}

    @classmethod
    def _game_shows_simulator_details(cls, *, game_config: Any) -> bool:
        game_cls = game_config.get_game_class()
        overrides = game_cls.parse_overrides(getattr(game_config, "overrides", {}) or {})
        return bool(getattr(overrides, "show_npc_details", True))

    @classmethod
    def _assignment_doc_for_candidate(
        cls,
        *,
        config: RunConfig,
        player: PlayerRecord,
        candidate: AssignmentCandidate,
    ) -> dict[str, Any]:
        assignment_doc: dict[str, Any] = {
            MongoColumns.PLAYER_ID: player.id,
            MongoColumns.GAME_NAME: candidate.game_name,
            MongoColumns.PC_HID: candidate.pc_hid,
            MongoColumns.NPC_HID: candidate.npc_hid,
            MongoColumns.STATUS: "assigned",
            MongoColumns.FORM_RESPONSES: {},
        }
        if candidate.metadata:
            assignment_doc.update(candidate.metadata)
        return assignment_doc

    @classmethod
    async def submit_form_group_async(
        cls,
        *,
        provider: Any,
        player_id: str,
        group_id: str,
        responses: dict[str, Any],
    ) -> dict[str, Any]:
        """Store responses for one currently pending form group."""
        config = cls.get_run_config()
        pending_groups = await cls.pending_form_groups_async(
            provider=provider,
            config=config,
            player_id=player_id,
        )
        group = next((item for item in pending_groups if item["group_id"] == group_id), None)
        if group is None:
            raise ValueError("No pending form group matches the submitted group_id.")

        forms = list(group["forms"])
        normalized = cls.normalize_form_submissions(forms=forms, responses=responses)
        event = group["trigger"]["event"]
        if event in {"before_all_assignments", "after_all_assignments"}:
            await cls.store_player_form_payloads_async(
                provider=provider,
                player_id=player_id,
                forms_payload=normalized,
            )
            return group

        assignment_id = group.get("assignment_id")
        if not assignment_id:
            raise ValueError("Assignment-scoped form group is missing assignment_id.")
        updated = await cls.store_form_payloads_async(
            provider=provider,
            assignment_id=assignment_id,
            forms_payload=normalized,
        )
        if updated is None:
            raise ValueError("Failed to store the form response.")
        return group

    @classmethod
    async def get_or_create_assignment_async(
        cls,
        *,
        provider: Any,
        player: PlayerRecord,
    ) -> AssignmentRecord | None:
        """Return the active assignment for a player or create one on demand."""
        assignment, _options = await cls.resolve_assignment_state_async(
            provider=provider,
            player=player,
        )
        return assignment

    @classmethod
    async def start_assignment_session_async(
        cls,
        *,
        provider: Any,
        registry: "SessionRegistry",
        player: PlayerRecord,
        source: str = "run",
        assignment_id: str | None = None,
    ) -> tuple["SessionEntry", AssignmentRecord]:
        """Start or resume gameplay for the requested assignment."""
        from dcs_simulation_engine.api.registry import hydrate_session_async

        assignment: AssignmentRecord | None
        if assignment_id is not None:
            assignment = await cls.get_assignment_for_player_async(
                provider=provider,
                player_id=player.id,
                assignment_id=assignment_id,
            )
        else:
            state = await cls.get_player_state_async(provider=provider, player_id=player.id)
            assignment = state["active_assignment"]
        if assignment is None:
            raise ValueError("No matching assignment is available for this player.")
        if assignment.status == "completed":
            raise ValueError("Completed assignments cannot be resumed.")
        config = cls.get_run_config()
        assignments = await maybe_await(provider.list_assignments(player_id=player.id))
        pending_groups = await cls.pending_form_groups_async(
            provider=provider,
            config=config,
            player_id=player.id,
            assignments=assignments,
            active_assignment=assignment,
        )
        if cls._blocks_assignment_start(pending_form_groups=pending_groups, assignment_id=assignment.assignment_id):
            raise ValueError("Required form responses must be submitted before starting this assignment.")

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
            pc_choice=assignment.pc_hid,
            npc_choice=assignment.npc_hid,
            player_id=player.id,
        )
        entry = registry.add(
            player_id=player.id,
            game_name=assignment.game_name,
            manager=manager,
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
            raise ValueError("Failed to mark run assignment as in progress.")
        return entry, updated_assignment

    @classmethod
    async def get_assignment_for_player_async(
        cls,
        *,
        provider: Any,
        player_id: str,
        assignment_id: str,
    ) -> AssignmentRecord | None:
        """Return one assignment if it belongs to the requested player."""
        assignment = await maybe_await(provider.get_assignment(assignment_id=assignment_id))
        if assignment is None:
            return None
        if assignment.player_id != player_id:
            return None
        return assignment

    @classmethod
    async def handle_session_terminal_state_async(
        cls,
        *,
        provider: Any,
        assignment_id: str,
        exit_reason: str,
    ) -> AssignmentRecord | None:
        """Map a gameplay terminal reason onto an assignment lifecycle status."""
        status = "completed" if cls._is_completion_reason(exit_reason) else "interrupted"
        updated = await maybe_await(provider.update_assignment_status(assignment_id=assignment_id, status=status))
        if status == "completed":
            await cls.ensure_run_async(provider=provider)
        return updated

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
        forms_payload: dict[str, dict[str, Any]],
    ) -> None:
        """Store one or more named player-scoped form payloads on the forms record."""
        for form_key, payload in forms_payload.items():
            await maybe_await(
                provider.set_player_form_response(
                    player_id=player_id,
                    form_key=form_key,
                    response=payload,
                )
            )

    @classmethod
    async def get_latest_assignment_for_player_async(cls, *, provider: Any, player_id: str) -> AssignmentRecord | None:
        """Return the latest assignment for a player."""
        getter = getattr(provider, "get_latest_assignment_for_player", None)
        if getter is None:
            return None
        return await maybe_await(getter(player_id=player_id))

    @classmethod
    def normalize_form_submissions(
        cls,
        *,
        forms: list[Form],
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
                "trigger": form.trigger.model_dump(mode="json"),
                "submitted_at": utc_now(),
                "answers": normalized_answers,
            }
        return normalized

    @classmethod
    def _normalize_question_answer(cls, *, question: FormQuestion, raw_value: Any) -> Any:
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
        player: PlayerRecord,
    ) -> list[dict[str, str]]:
        """Return selectable {game_name, pc_hid, npc_hid} options for the player."""
        state = await cls.get_player_state_async(provider=provider, player_id=player.id)
        return list(state.get("eligible_assignment_options", []))

    @classmethod
    async def create_player_choice_assignment_async(
        cls,
        *,
        provider: Any,
        player: PlayerRecord,
        game_name: str,
        pc_hid: str,
        npc_hid: str,
    ) -> AssignmentRecord:
        """Create a specific assignment for a player who selected one explicit candidate."""
        config = cls.get_run_config()
        if not config.assignment_strategy.allow_choice_if_multiple:
            raise ValueError("This run is not configured for participant assignment choice.")
        eligible = await cls.get_eligible_options_async(
            provider=provider,
            player=player,
        )
        eligible_set = {(opt["game_name"], opt["pc_hid"], opt["npc_hid"]) for opt in eligible}
        if (game_name, pc_hid, npc_hid) not in eligible_set:
            raise ValueError("The selected game, PC, and NPC are not available for assignment.")
        player_assignments = await maybe_await(provider.list_assignments(player_id=player.id))
        assignment = await maybe_await(
            provider.create_assignment(
                assignment_doc={
                    MongoColumns.PLAYER_ID: player.id,
                    MongoColumns.GAME_NAME: game_name,
                    MongoColumns.PC_HID: pc_hid,
                    MongoColumns.NPC_HID: npc_hid,
                    MongoColumns.STATUS: "assigned",
                    MongoColumns.FORM_RESPONSES: {},
                },
                allow_concurrent=cls._allow_concurrent_assignment(config=config, assignments=player_assignments),
            )
        )
        if assignment is None:
            raise ValueError("Failed to create the assignment.")
        return assignment

    @classmethod
    def _strategy_for(cls, *, config: RunConfig):
        """Resolve the configured assignment strategy for one run."""
        return get_assignment_strategy(config.assignment_strategy.strategy)

    @classmethod
    def _is_completion_reason(cls, reason: str) -> bool:
        normalized = reason.strip().lower().replace(" ", "_")
        completion_reasons = {
            "game_completed",
            "player_finished",
        }
        return normalized in completion_reasons or normalized.startswith("stopping_condition_met:")
