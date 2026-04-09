"""SessionManager: drives new-style Game classes."""

import importlib
import inspect
import random
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from dcs_simulation_engine.core.game import Game, GameEvent
from dcs_simulation_engine.core.game_config import GameConfig
from dcs_simulation_engine.core.session_event_recorder import SessionEventRecorder
from dcs_simulation_engine.dal.base import CharacterRecord, DataProvider
from dcs_simulation_engine.dal.mongo.const import MongoColumns
from dcs_simulation_engine.helpers.game_helpers import get_game_config
from dcs_simulation_engine.utils.async_utils import maybe_await
from dcs_simulation_engine.utils.time import utc_now
from loguru import logger


def _parse_command_input(text: str | None) -> tuple[str, str] | None:
    """Parse a slash-prefixed input into (command_name, args)."""
    if not isinstance(text, str):
        return None

    stripped = text.strip()
    if not stripped.startswith("/"):
        return None

    parts = stripped[1:].split(maxsplit=1)
    command_name = parts[0].lower() if parts else ""
    command_args = parts[1] if len(parts) > 1 else ""
    return (command_name, command_args)


class SessionManager:
    """Manages a single session of a Game."""

    _game_config_cache: dict[str, GameConfig] = {}

    @classmethod
    def _cache_key(cls, game: str) -> str:
        """Normalize cache lookup key for one exact game name."""
        return game.strip()

    @classmethod
    def _load_game_config_into_cache(cls, game: str) -> bool:
        """Load and cache one game config by name if it's not already cached."""
        cache_key = cls._cache_key(game)
        if cache_key in cls._game_config_cache:
            return False
        game_config_fpath = get_game_config(game)
        cls._game_config_cache[cache_key] = GameConfig.load(game_config_fpath)
        return True

    @classmethod
    def get_game_config_cached(cls, game: str) -> GameConfig:
        """Return a defensive copy of a cached game config, loading it on first use."""
        cls._load_game_config_into_cache(game)
        return cls._game_config_cache[cls._cache_key(game)].model_copy(deep=True)

    def __init__(
        self,
        name: str,
        game: Game,
        game_config: GameConfig,
        provider: DataProvider | Any,
        source: str = "unknown",
        player_id: Optional[str] = None,
        stopping_conditions: Optional[Dict[str, List[str]]] = None,
    ) -> None:
        """Initialize session state, runtime counters, and persistence hooks."""
        self.name = name
        self.game = game
        self.game_config = game_config
        self._provider = provider
        self.source = source
        self.player_id = player_id
        self.start_ts: datetime = utc_now()
        self.end_ts: Optional[datetime] = None
        self._exited = False
        self._exit_reason = ""
        self._turn_count = 0
        self._events: List[Dict[str, Any]] = []
        self._saved: bool = False
        self._session_id: str | None = None
        self._recorder: SessionEventRecorder | None = None
        self._recorder_open = False
        self._finalized = False
        self.stopping_conditions: Dict[str, List[str]] = stopping_conditions or {
            "turns": [">500"],
            "runtime_seconds": [">3600"],
        }

    @classmethod
    async def create_async(
        cls,
        game: "str | GameConfig",
        provider: Any,
        source: str = "unknown",
        pc_choice: Optional[str] = None,
        npc_choice: Optional[str] = None,
        player_id: Optional[str] = None,
        is_llm_player: bool = False,
    ) -> "SessionManager":
        """Create a session for async runtime paths."""
        if isinstance(game, str):
            game_config = cls.get_game_config_cached(game)
        elif isinstance(game, GameConfig):
            game_config = game
        else:
            raise TypeError(f"Invalid game parameter type: {type(game)}")

        get_valid = getattr(game_config, "get_valid_characters_async", None)
        if get_valid is None:
            valid_pcs, valid_npcs = await maybe_await(game_config.get_valid_characters(player_id=player_id, provider=provider))
        else:
            valid_pcs, valid_npcs = await maybe_await(get_valid(player_id=player_id, provider=provider))
        valid_pc_hids = [hid for _, hid in valid_pcs]
        valid_npc_hids = [hid for _, hid in valid_npcs]
        pc_hid, npc_hid = cls._validate_choices(
            valid_pc_hids=valid_pc_hids,
            valid_npc_hids=valid_npc_hids,
            pc_choice=pc_choice,
            npc_choice=npc_choice,
        )

        pc: CharacterRecord = await maybe_await(provider.get_character(hid=pc_hid))
        npc: CharacterRecord = await maybe_await(provider.get_character(hid=npc_hid))
        game_instance = cls._build_game_instance(
            game_config=game_config, pc=pc, npc=npc, is_llm_player=is_llm_player,
        )
        session = cls._build_session(
            game_config=game_config,
            game_instance=game_instance,
            provider=provider,
            source=source,
            player_id=player_id,
        )
        logger.info("SessionManager created: {}, pc={}, npc={}", session.name, pc_hid, npc_hid)
        return session

    @classmethod
    def preload_game_configs(cls) -> int:
        """Load all valid game configs from disk into the in-memory cache."""
        games_dir = Path(__file__).resolve().parents[2] / "games"
        if not games_dir.exists() or not games_dir.is_dir():
            return 0

        discovered_names: set[str] = set()
        for path in games_dir.glob("*.y*ml"):
            try:
                with path.open("r", encoding="utf-8") as f:
                    doc = yaml.safe_load(f) or {}
                raw_name = doc.get("name")
                if isinstance(raw_name, str) and raw_name.strip():
                    discovered_names.add(raw_name.strip())
            except Exception:
                logger.debug("Skipping unreadable game config while preloading: {}", path, exc_info=True)

        loaded = 0
        for name in discovered_names:
            try:
                if cls._load_game_config_into_cache(name):
                    loaded += 1
            except Exception:
                logger.debug("Skipping invalid game config '{}' during preload", name, exc_info=True)

        if loaded > 0:
            logger.info("Preloaded {} game config(s) into SessionManager cache.", loaded)
        return loaded

    @classmethod
    def _build_game_instance(
        cls,
        *,
        game_config: GameConfig,
        pc: CharacterRecord,
        npc: CharacterRecord,
        is_llm_player: bool = False,
    ) -> Game:
        module_path, class_name = game_config.game_class.rsplit(".", 1)
        module = importlib.import_module(module_path)
        game_cls = getattr(module, class_name)
        return game_cls.create_from_context(
            pc=pc, npc=npc, game_name=game_config.name, is_llm_player=is_llm_player,
        )

    @classmethod
    def _build_session(
        cls,
        *,
        game_config: GameConfig,
        game_instance: Game,
        provider: Any,
        source: str,
        player_id: str | None,
    ) -> "SessionManager":
        # Use a deterministic name format for easier testing and indexing, but include a timestamp for uniqueness.
        time_str = utc_now().strftime("%Y%m%d-%H%M%S")
        name = f"{source}-{game_config.name}-{time_str}".lower().replace(" ", "-")
        stopping = dict(game_config.stopping_conditions) if game_config.stopping_conditions else {}
        return cls(
            name=name,
            game=game_instance,
            game_config=game_config,
            provider=provider,
            source=source,
            player_id=player_id,
            stopping_conditions=stopping or None,
        )

    @classmethod
    def _validate_choices(
        cls,
        *,
        valid_pc_hids: list[str],
        valid_npc_hids: list[str],
        pc_choice: str | None,
        npc_choice: str | None,
    ) -> tuple[str, str]:
        if not valid_pc_hids:
            raise ValueError("No valid player character choices found.")
        if not valid_npc_hids:
            raise ValueError("No valid non-player character choices found.")
        if pc_choice and pc_choice not in valid_pc_hids:
            raise ValueError(f"Invalid pc_choice: {pc_choice}")
        if npc_choice and npc_choice not in valid_npc_hids:
            raise ValueError(f"Invalid npc_choice: {npc_choice}")
        return (pc_choice or random.choice(valid_pc_hids), npc_choice or random.choice(valid_npc_hids))

    @property
    def exited(self) -> bool:
        """Return True when the session or game lifecycle is finished."""
        return self._exited or self.game.exited

    @property
    def exit_reason(self) -> str:
        """Return the terminal reason string, if available."""
        return self._exit_reason or self.game.exit_reason

    @property
    def turns(self) -> int:
        """Return completed AI turns."""
        return self._turn_count

    @property
    def runtime_seconds(self) -> int:
        """Return elapsed runtime in seconds."""
        end = self.end_ts or utc_now()
        return int((end - self.start_ts).total_seconds())

    async def start_persistence(self, *, session_id: str) -> None:
        """Initialize session + event persistence once session_id is assigned."""
        if self._recorder_open:
            return

        get_db = getattr(self._provider, "get_db", None)
        if get_db is None:
            return
        db = get_db()
        insert_one = getattr(db[MongoColumns.SESSIONS], "insert_one", None)
        if insert_one is None or not inspect.iscoroutinefunction(insert_one):
            # Transcript persistence requires async collection methods.
            return

        self._session_id = session_id
        pc = getattr(self.game, "_pc", None)
        npc = getattr(self.game, "_npc", None)

        session_doc: dict[str, Any] = {
            MongoColumns.SESSION_ID: session_id,
            MongoColumns.NAME: self.name,
            MongoColumns.PLAYER_ID: self.player_id,
            MongoColumns.GAME_NAME: self.game_config.name,
            MongoColumns.SOURCE: self.source,
            MongoColumns.PC_HID: getattr(pc, "hid", None),
            MongoColumns.NPC_HID: getattr(npc, "hid", None),
            MongoColumns.SESSION_STARTED_AT: self.start_ts,
            MongoColumns.SESSION_ENDED_AT: None,
            MongoColumns.TERMINATION_REASON: None,
            MongoColumns.STATUS: "active",
            MongoColumns.TURNS_COMPLETED: 0,
            MongoColumns.MODEL_PROFILE: {
                "updater_model": getattr(getattr(self.game, "_updater", None), "_model", None),
                "validator_model": getattr(getattr(self.game, "_validator", None), "_model", None),
                "scorer_model": getattr(getattr(self.game, "_scorer", None), "_model", None),
            },
            MongoColumns.GAME_CONFIG_SNAPSHOT: self.game_config.model_dump(mode="json"),
            MongoColumns.LAST_SEQ: 0,
            MongoColumns.CREATED_AT: utc_now(),
            MongoColumns.UPDATED_AT: utc_now(),
        }

        self._recorder = SessionEventRecorder(db=db, session_doc=session_doc)
        await self._recorder.__aenter__()
        self._recorder_open = True
        await self._recorder.record_internal(event_type="session_start", detail="created", turn_index=0)

    def _begin_exit(self, reason: str) -> None:
        """Mark local exit state before persistence finalization."""
        if self._exited:
            return
        self._exited = True
        self._exit_reason = reason
        self.end_ts = utc_now()
        self.game.exit(reason)

    async def exit_async(self, reason: str) -> None:
        """Mark session ended, finalize persistence, and close recorder."""
        self._begin_exit(reason)

        if self._finalized:
            return

        if self._recorder_open and self._recorder is not None:
            normalized = self._normalize_termination_reason(reason)
            status = "error" if normalized == "server_error" else "closed"
            await self._recorder.finalize(
                termination_reason=normalized,
                status=status,
                turns_completed=self.turns,
            )
            await self._recorder.__aexit__(None, None, None)
            self._recorder_open = False
        self._finalized = True
        logger.info("Session exited. Reason: {}", reason)

    async def flush_persistence_async(self) -> None:
        """Flush any queued transcript events so follow-on writes can target them safely."""
        if self._recorder_open and self._recorder is not None:
            await self._recorder.flush_pending()

    def save(self) -> None:
        """Compatibility no-op; session transcript writes now use session_events."""
        self._saved = True
        logger.debug("SessionManager.save() is a no-op; persistence is event-sourced.")

    async def step_async(self, user_input: Optional[str] = None) -> List[Dict[str, Any]]:
        """Advance one turn asynchronously and return normalized event dicts."""
        if self.exited:
            return [{"type": "info", "content": f"Session has ended. ({self.exit_reason})"}]

        stopping_reason = self._check_stopping_conditions()
        if stopping_reason is not None:
            await self.exit_async(stopping_reason)
            return [{"type": "info", "content": f"Session ended: {self.exit_reason}"}]

        turn_index = self._turn_count + 1
        parsed_command = _parse_command_input(user_input)

        events = await self._collect_events(user_input)
        recognized_game_command = parsed_command is not None and any(event.command_response for event in events)
        if isinstance(user_input, str) and user_input != "" and self._recorder_open and self._recorder is not None:
            inbound_event_type = "command" if recognized_game_command else "message"
            inbound_command_name = parsed_command[0] if recognized_game_command and parsed_command is not None else None
            inbound_command_args = parsed_command[1] if recognized_game_command and parsed_command is not None else None
            await self._recorder.record_inbound(
                content=user_input,
                turn_index=turn_index,
                event_type=inbound_event_type,
                command_name=inbound_command_name,
                command_args=inbound_command_args,
            )

        emitted: List[Dict[str, Any]] = []
        yielded_ai = False
        for event in events:
            if event.type == "ai":
                yielded_ai = True
            payload = {"type": event.type, "content": event.content}
            self._events.append(payload)
            if self._recorder_open and self._recorder is not None:
                persisted_event_type, persisted_event_source = self._classify_persisted_outbound_event(event)
                outbound_command_name = parsed_command[0] if event.command_response and parsed_command is not None else None
                outbound_command_args = parsed_command[1] if event.command_response and parsed_command is not None else None
                recorded = await self._recorder.record_outbound(
                    event_type=persisted_event_type,
                    event_source=persisted_event_source,
                    content=event.content,
                    turn_index=turn_index,
                    command_name=outbound_command_name,
                    command_args=outbound_command_args,
                    event_ts=event.event_ts,
                )
                payload["event_id"] = recorded.event_id
            emitted.append(payload)

        if yielded_ai:
            self._turn_count += 1

        if self.game.exited and not self._exited:
            await self.exit_async(self.game.exit_reason or "game_completed")
        return emitted

    async def _collect_events(self, user_input: Optional[str]) -> List[GameEvent]:
        events: List[GameEvent] = []
        async for event in self.game.step(user_input):
            events.append(event)
        return events

    def _classify_persisted_outbound_event(self, event: GameEvent) -> tuple[str, str]:
        event_type = str(event.type or "info").lower()
        if event.command_response:
            return ("command", "system")
        if event_type == "ai":
            return ("message", "npc")
        if event_type == "error":
            return ("error", "system")
        return ("info", "system")

    def _check_stopping_conditions(self) -> str | None:
        for attr, cond_list in self.stopping_conditions.items():
            val = getattr(self, attr, None)
            if val is None:
                continue
            for condition in cond_list:
                condition = condition.strip()
                try:
                    if isinstance(val, (int, float)) and condition[0] in "<>!=":
                        if eval(f"{val}{condition}"):  # noqa: S307
                            return f"stopping condition met: {attr} {condition}"
                except Exception as exc:
                    logger.error("Error evaluating stopping condition {}={!r}: {}", attr, condition, exc)
        return None

    def _normalize_termination_reason(self, reason: str) -> str:
        reason_l = reason.strip().lower().replace(" ", "_")
        if reason_l in {"received_close_request", "user_close_button"}:
            return "user_close_button"
        if reason_l in {"received_exit_command", "user_exit_command"}:
            return "user_exit_command"
        if reason_l in {"game_completed", "game_complete"}:
            return "game_completed"
        if reason_l in {"session_ttl_expired"} or "ttl" in reason_l:
            return "session_ttl_expired"
        if reason_l in {"websocket_disconnect"}:
            return "websocket_disconnect"
        if reason_l in {"retry_budget_exhausted", "validation_retry_exhausted"}:
            return "validation_retry_exhausted"
        if reason_l in {"server_error", "internal_server_error"}:
            return "server_error"
        return reason_l
