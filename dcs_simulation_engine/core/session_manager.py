"""SessionManager: drives new-style Game classes.

A parallel alternative to RunManager for games that subclass Game instead of
implementing build_graph_config(). Presents the same duck-typed interface
(step(), exit(), exited, exit_reason) so widget handlers need no changes.
"""

import asyncio
import importlib
import random
from datetime import datetime
from typing import Any, Dict, Iterator, List, Optional

from dcs_simulation_engine.core.game import Game, GameEvent
from dcs_simulation_engine.core.game_config import (
    GameConfig,
)
from dcs_simulation_engine.dal.base import (
    CharacterRecord,
    DataProvider,
)
from dcs_simulation_engine.helpers.game_helpers import (
    get_game_config,
)
from dcs_simulation_engine.utils.file import safe_timestamp
from loguru import logger


class SessionManager:
    """Manages a single session of a new-style Game.

    External interface mirrors RunManager so the widget layer needs no changes:
    - step(user_input) -> Iterator[dict]
    - exit(reason)
    - exited: bool
    - exit_reason: str
    - player_id: str | None
    - feedback: list
    - turns: int
    - runtime_seconds: int
    """

    def __init__(
        self,
        name: str,
        game: Game,
        game_config: GameConfig,
        provider: DataProvider,
        source: str = "unknown",
        player_id: Optional[str] = None,
        stopping_conditions: Optional[Dict[str, List[str]]] = None,
    ) -> None:
        """Initialise a session. Use SessionManager.create() as the public entry point."""
        self.name = name
        self.game = game
        self.game_config = game_config
        self._provider = provider
        self.source = source
        self.player_id = player_id
        self.feedback: List[Dict[str, Any]] = []
        self.start_ts: datetime = datetime.now()
        self.end_ts: Optional[datetime] = None
        self._exited = False
        self._exit_reason = ""
        self._turn_count = 0
        self._events: List[Dict[str, Any]] = []
        self._saved: bool = False
        self.stopping_conditions: Dict[str, List[str]] = stopping_conditions or {
            "turns": [">500"],
            "runtime_seconds": [">3600"],
        }

    @classmethod
    def create(
        cls,
        game: "str | GameConfig",
        provider: DataProvider,
        source: str = "unknown",
        pc_choice: Optional[str] = None,
        npc_choice: Optional[str] = None,
        player_id: Optional[str] = None,
    ) -> "SessionManager":
        """Create a new SessionManager, mirroring RunManager.create()."""
        if isinstance(game, str):
            game_config_fpath = get_game_config(game)
            game_config = GameConfig.load(game_config_fpath)
        elif isinstance(game, GameConfig):
            game_config = game
        else:
            raise TypeError(f"Invalid game parameter type: {type(game)}")

        if not game_config.is_player_allowed(player_id=player_id, provider=provider):
            raise PermissionError(f"Player '{player_id}' is not allowed to access this game.")

        valid_pcs, valid_npcs = game_config.get_valid_characters(player_id=player_id, provider=provider)
        valid_pc_hids = [hid for _, hid in valid_pcs]
        valid_npc_hids = [hid for _, hid in valid_npcs]

        if not valid_pc_hids:
            raise ValueError("No valid player character choices found.")
        if not valid_npc_hids:
            raise ValueError("No valid non-player character choices found.")

        if pc_choice and pc_choice not in valid_pc_hids:
            raise ValueError(f"Invalid pc_choice: {pc_choice}")
        if npc_choice and npc_choice not in valid_npc_hids:
            raise ValueError(f"Invalid npc_choice: {npc_choice}")

        pc_hid = pc_choice or random.choice(valid_pc_hids)
        npc_hid = npc_choice or random.choice(valid_npc_hids)

        pc: CharacterRecord = provider.get_character(hid=pc_hid)
        npc: CharacterRecord = provider.get_character(hid=npc_hid)

        module_path, class_name = game_config.game_class.rsplit(".", 1)
        module = importlib.import_module(module_path)
        game_cls = getattr(module, class_name)
        game_instance: Game = game_cls.create_from_context(pc=pc, npc=npc)

        name = f"{source}-{game_config.name}-{safe_timestamp()}".lower().replace(" ", "-")
        stopping = dict(game_config.stopping_conditions) if game_config.stopping_conditions else {}

        session = cls(
            name=name,
            game=game_instance,
            game_config=game_config,
            provider=provider,
            source=source,
            player_id=player_id,
            stopping_conditions=stopping or None,
        )
        logger.info(f"SessionManager created: {name}, pc={pc_hid}, npc={npc_hid}")
        return session

    @property
    def exited(self) -> bool:
        """True if the session or its game has ended."""
        return self._exited or self.game.exited

    @property
    def exit_reason(self) -> str:
        """Reason the session ended, or empty string."""
        return self._exit_reason or self.game.exit_reason

    @property
    def turns(self) -> int:
        """Number of completed AI turns."""
        return self._turn_count

    @property
    def runtime_seconds(self) -> int:
        """Elapsed session time in seconds."""
        end = self.end_ts or datetime.now()
        return int((end - self.start_ts).total_seconds())

    def exit(self, reason: str) -> None:
        """Mark the session as ended and propagate to the game."""
        if self._exited:
            return
        self._exited = True
        self._exit_reason = reason
        self.end_ts = datetime.now()
        self.game.exit(reason)
        self.save()
        logger.info(f"Session exited. Reason: {reason}")

    def save(self) -> None:
        """Persist the session to the database if save_runs is enabled."""
        if self._saved:
            return
        if not self.game_config.data_collection_settings.get("save_runs", False):
            logger.debug("save_runs not enabled; skipping persistence.")
            return

        _pc = getattr(self.game, "_pc", None)
        _npc = getattr(self.game, "_npc", None)
        pc_hid = getattr(_pc, "hid", None)
        npc_hid = getattr(_npc, "hid", None)
        context = {
            "pc": _pc._asdict() if _pc is not None else {},
            "npc": _npc._asdict() if _npc is not None else {},
        }
        run_data = {
            "name": self.name,
            "game_name": self.game_config.name,
            "game_config": self.game_config.model_dump(mode="json"),
            "source": self.source,
            "player_id": self.player_id,
            "pc_hid": pc_hid,
            "npc_hid": npc_hid,
            "start_ts": self.start_ts.isoformat(),
            "end_ts": self.end_ts.isoformat() if self.end_ts else None,
            "exit_reason": self.exit_reason,
            "turns": self.turns,
            "runtime_seconds": self.runtime_seconds,
            "feedback": self.feedback,
            "events": self._events,
            "context": context,
        }
        try:
            record = self._provider.save_run(self.player_id, run_data)
            self._saved = True
            logger.info(f"Session saved to database: {record.id}")
        except Exception as exc:
            logger.error(f"Failed to save session to database: {exc}")

    def step(self, user_input: Optional[str] = None) -> Iterator[Dict[str, Any]]:
        """Advance the game one turn, yielding widget-compatible event dicts.

        Mirrors RunManager.step(): handles session-level commands (/exit, /feedback),
        enforces stopping conditions, then delegates to the async game.step().
        Each yielded dict has 'type' and 'content' keys, matching what the
        widget handlers already expect from RunManager.
        """
        # Already ended — emit a single info message and stop.
        if self.exited:
            yield {"type": "info", "content": f"Session has ended. ({self.exit_reason})"}
            return

        # Check time/turn limits before doing any work this turn.
        self._ensure_stopping_conditions()
        if self.exited:
            yield {"type": "info", "content": f"Session ended: {self.exit_reason}"}
            return

        # Session-level command handling (mirrors RunManager.step).
        # Game-specific commands (/help, /abilities, etc.) are handled inside
        # the game class itself.
        if isinstance(user_input, str) and user_input.strip().startswith(("/", "\\")):
            parts = user_input.strip().split(maxsplit=1)
            cmd = parts[0].lower().lstrip("/\\")

            if cmd in ("quit", "stop", "exit"):
                self.exit("received exit command")
                yield {"type": "info", "content": f"Session exited: {self.exit_reason}"}
                return

            if cmd in ("feedback", "fb"):
                fb = parts[1] if len(parts) > 1 else ""
                if fb:
                    self.feedback.append({"timestamp": datetime.now().isoformat(), "content": fb})
                yield {
                    "type": "info",
                    "content": (
                        "Feedback received, thank you."
                        if fb
                        else "No feedback content provided. Type '/feedback <your comments here>'"
                    ),
                }
                return
            # Unrecognised commands fall through to the game so it can handle them.

        # Drive the async game.step() synchronously by collecting all events
        # into a list, then yielding them as plain dicts.
        events: List[GameEvent] = asyncio.run(self._collect_events(user_input))

        yielded_ai = False
        for event in events:
            if event.type == "ai":
                # Count a turn only when the AI has actually responded.
                yielded_ai = True
            self._events.append({"type": event.type, "content": event.content})
            yield {"type": event.type, "content": event.content}

        if yielded_ai:
            self._turn_count += 1

        # Sync exit state from the game in case it ended during this step.
        if self.game.exited and not self._exited:
            self._exited = True
            self._exit_reason = self.game.exit_reason
            self.end_ts = datetime.now()
            self.save()

    async def _collect_events(self, user_input: Optional[str]) -> List[GameEvent]:
        """Collect all events from a single async game.step() call."""
        events: List[GameEvent] = []
        async for event in self.game.step(user_input):
            events.append(event)
        return events

    def _ensure_stopping_conditions(self) -> None:
        """Exit the session if any configured stopping condition is met."""
        for attr, cond_list in self.stopping_conditions.items():
            val = getattr(self, attr, None)
            if val is None:
                continue
            for condition in cond_list:
                condition = condition.strip()
                try:
                    if isinstance(val, (int, float)) and condition[0] in "<>!=":
                        if eval(f"{val}{condition}"):  # noqa: S307
                            self.exit(f"stopping condition met: {attr} {condition}")
                            return
                except Exception as exc:
                    logger.error(f"Error evaluating stopping condition {attr}={condition!r}: {exc}")
