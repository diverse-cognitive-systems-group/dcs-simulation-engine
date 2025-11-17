"""Run manager module that orchestrates the simulation lifecycle."""

from __future__ import annotations

import json
import random
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Union

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.runnables import RunnableConfig
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from dcs_simulation_engine.core.constants import OUTPUT_FPATH
from dcs_simulation_engine.core.game_config import GameConfig
from dcs_simulation_engine.core.simulation_graph import (
    SimulationGraph,
    SimulationGraphState,
    make_state,
)
from dcs_simulation_engine.core.simulation_graph.context import ContextSchema
from dcs_simulation_engine.helpers import database_helpers as dbh
from dcs_simulation_engine.helpers.game_helpers import get_game_config
from dcs_simulation_engine.utils.chat import ChatOpenRouter
from dcs_simulation_engine.utils.file import safe_timestamp, unique_fpath

# TODO: pre-release - add safety/validation heuristic for overly complex inputs like
# really long actions....length heuristic using tokens or character threshold
# TODO: pre-release - what prevents user from inputting two things
# really fast and flooding the system??

# TODO: pre-release - add step(long_running and timeout and interrupt) support
# to exit step (also consider yield results as generator??

# TODO: if character choices has no qa, warn (playing with characters whose
# represetnational quality has not been assessed by the DCS research group...
# do you wish to submit these characters for assessment so they can be added
# to core characters db (link to open a ticket))


class RunManager(BaseModel):
    """Initialize the run."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    game_config: GameConfig
    state: SimulationGraphState
    context: ContextSchema
    config: RunnableConfig

    source: str = Field(default_factory=lambda: "unknown")

    graph: SimulationGraph = Field(exclude=True)

    start_ts: datetime = Field(default_factory=datetime.now)
    end_ts: Optional[datetime] = None
    output_fpaths: List[Path] = Field(default_factory=list)
    exited: bool = Field(default=False)
    saved: bool = Field(default=False)
    exit_reason: str = Field(default="")
    player_id: Optional[str] = Field(default=None)

    stopping_conditions: Dict[str, List[str]] = Field(
        # Default stopping conditions to prevent runaway simulations
        default_factory=lambda: {
            "turns": [">500"],
            "runtime_seconds": [">3600"],
        }
    )

    @field_validator("stopping_conditions", mode="before")
    @classmethod
    def _validate_stopping_conditions(cls, v):  # type: ignore[no-untyped-def]
        """Validate stopping conditions dict."""
        # pydantic will pass the raw value here; ensure dict and normalize
        if v is None:
            raise ValueError("stopping_conditions cannot be empty.")
        if not isinstance(v, dict):
            raise TypeError(
                "stopping_conditions must be a dict[str, list[str]] or "
                "compatible mapping."
            )
        # use cls.model_fields here (not RunManager) to avoid class-construction issues
        allowed = set(cls.model_fields.keys()) | {
            "runtime_seconds",
            "runtime",
            "total_turns",
        }

        out: Dict[str, List[str]] = {}
        for attr, conds in v.items():
            if attr not in allowed:
                raise ValueError(f"Unknown stopping condition attribute: {attr}")
            if isinstance(conds, str):
                conds = [conds]
            if not isinstance(conds, list) or not conds:
                raise ValueError(
                    f"Conditions for '{attr}' must be a non-empty list of strings."
                )
            for c in conds:
                if not isinstance(c, str) or not c.strip():
                    raise ValueError(
                        f"Condition for '{attr}' must be a non-empty string."
                    )
            out[attr] = conds
        return out

    @computed_field(return_type=int)
    def turns(self) -> int:
        """Get the total number of turns taken."""
        return len(self.state["events"])

    @computed_field(return_type=int)
    def runtime_seconds(self) -> int:
        """Get the runtime in total seconds."""
        end = self.end_ts or datetime.now()
        return int((end - self.start_ts).total_seconds())

    @computed_field(return_type=str)
    def runtime_string(self) -> str:
        """Get the runtime as a formatted string HH:MM:SS."""
        end = self.end_ts or datetime.now()
        dt = end - self.start_ts
        secs = int(dt.total_seconds())
        h, m = divmod(secs, 3600)
        m, s = divmod(m, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    @classmethod
    def create(
        cls,
        game: str | Path | GameConfig,
        source: str = "unknown",
        pc_choice: Optional[str] = None,
        npc_choice: Optional[str] = None,
        access_key: Optional[str] = None,
        player_id: Optional[str] = None,
    ) -> "RunManager":
        """Create a new run with default or provided parameters."""
        # TODO: if course is "unknown", log warning that run saves may be hard to track

        game_config: Optional[GameConfig] = None
        if isinstance(game, str):
            game_config_fpath = Path(get_game_config(game)).resolve()
        elif isinstance(game, Path):
            game_config_fpath = game.resolve()
        elif isinstance(game, GameConfig):
            game_config = game
        else:
            raise TypeError("Invalid game parameter type.")

        logger.debug(f"Create class method called with game={game}")

        # Load game config from YAML
        if not game_config:
            try:
                game_config = GameConfig.from_yaml(game_config_fpath)
            except Exception as e:
                logger.error(
                    f"Loading game config from yaml file {game_config_fpath} \
                        failed. This likely means there is a syntax error \
                            in the YAML file. \n{e}"
                )
                raise

        # Setup player info from access settings
        try:
            if access_key:
                logger.debug("Access key provided; attempting to get player ID.")
                player_id = dbh.get_player_id_from_access_key(access_key)
                logger.debug(f"Retrieved player ID: {player_id}")

            # Make sure the game is open to this player or None if public
            if not game_config.is_player_allowed(player_id):
                raise PermissionError(
                    f"Player with ID '{player_id}' is not allowed to access this game."
                )
        except Exception as e:
            logger.error(f"Failed to setup access settings: {e}")
            raise

        # Load characters based on choice (if any) and character settings
        try:
            valid_pcs, valid_npcs = game_config.get_valid_characters(
                player_id=player_id
            )

            if not valid_pcs:
                raise ValueError(
                    "No valid player character choices found in game config."
                )
            if not valid_npcs:
                raise ValueError(
                    "No valid non-player character choices found in game config."
                )

            if pc_choice and pc_choice not in valid_pcs:
                raise ValueError(
                    f"Invalid pc_choice: {pc_choice}. Valid choices: {valid_pcs}"
                )
            if npc_choice and npc_choice not in valid_npcs:
                raise ValueError(
                    f"Invalid npc_choice: {npc_choice}. Valid choices: {valid_npcs}"
                )
            if pc_choice is None:
                pc_choice = valid_pcs[random.randint(0, len(valid_pcs) - 1)]
            if npc_choice is None:
                npc_choice = valid_npcs[random.randint(0, len(valid_npcs) - 1)]

            if pc_choice is None or npc_choice is None:
                raise ValueError("pc_choice and npc_choice must be set.")

            pc = dbh.get_character_from_hid(hid=pc_choice)
            npc = dbh.get_character_from_hid(hid=npc_choice)
        except Exception as e:
            logger.error(f"Failed to load characters: {e}")
            raise

        # Initialize empty state
        try:
            state: SimulationGraphState = make_state()
            if game_config.graph_config.state_overrides:
                logger.debug(
                    f"Applying state overrides: "
                    f"{game_config.graph_config.state_overrides}"
                )
                state.update(**game_config.graph_config.state_overrides)
            else:
                logger.debug("No state overrides to apply.")

            if game_config.stopping_conditions:
                logger.debug(
                    f"Applying stopping conditions from game config: \
                        {game_config.stopping_conditions}"
                )
            else:
                logger.debug("No stopping conditions to apply from game config.")
        except Exception as e:
            logger.error(f"Failed to create initial state: {e}")
            raise
        logger.debug(f"Initial state created: {state}")

        # Initialize runtime context (llms) and inject them into runtime
        # context at build time
        context = ContextSchema(pc=pc, npc=npc, models={})
        for node in game_config.graph_config.nodes:
            if node.provider:  # only setup nodes with a provider
                if node.additional_kwargs is None:
                    node.additional_kwargs = {}
                if node.provider == "openrouter":
                    llm: BaseChatModel = ChatOpenRouter(
                        model=node.model, **node.additional_kwargs
                    )
                    context["models"][node.model] = llm
                elif node.provider == "huggingface":
                    raise NotImplementedError(
                        f"Provider not implemented yet: {node.provider}"
                    )
                elif node.provider == "local":
                    raise NotImplementedError(
                        f"Provider not implemented yet: {node.provider}"
                    )
                else:
                    raise NotImplementedError(
                        f"Provider not implemented yet: {node.provider}"
                    )
        # Also initialize simulation subgraph model(s)
        context["models"]["simulation_subgraph"] = ChatOpenRouter()

        # Compile the simulation graph
        try:
            sim_graph: SimulationGraph = SimulationGraph.compile(
                config=game_config.graph_config
            )
        except Exception as e:
            logger.error(f"Failed to compile simulation graph: {e}")
            raise

        name = f"{source}-{game_config.name}-{safe_timestamp()}".lower().replace(
            " ", "-"
        )
        cfg = RunnableConfig(configurable={"thread_id": name})
        run = cls(
            name=name,
            game_config=game_config,
            source=source,
            graph=sim_graph,
            state=state,
            config=cfg,
            context=context,
        )
        logger.info(
            f"Created new run of {name} with pc: {pc_choice}, npc: {npc_choice}"
        )
        if player_id:
            logger.debug(f"Setting player_id: {player_id}")
            run.player_id = player_id
        run.state["lifecycle"] = "ENTER"

        return run

    def step(
        self,
        user_input: Optional[Union[str, Mapping[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Advance the simulation one turn.

        - If `user_input` is a string starting with '/', interpret as a command:
            /quit | /stop            -> stop the simulation
            /save [optional_path]    -> save state to OUTPUT_FPATH or given path
            /state                   -> return current state (no graph step)
        - Otherwise, treat as user text, append HumanMessage, and invoke one graph step.

        Returns the updated state (dict).
        """
        # logger.debug(f"RunManager step called with user_input: {user_input!r}")

        if self.start_ts is None:
            self.start_ts = datetime.now()

        self._ensure_stopping_conditions()  # sets self.stopped if needed

        if self.state is None:
            raise ValueError("Internal state is not initialized.")

        if isinstance(user_input, str) and (
            user_input.strip().startswith("/") or user_input.strip().startswith("\\")
        ):
            parts = user_input.strip().split(maxsplit=1)
            cmd = parts[0].lower().lstrip("/\\")

            if cmd in ("quit", "stop", "exit"):
                self.exit(reason="received exit command")
                return self.state  # type: ignore

            elif cmd in ("feedback", "fb"):
                # TODO: pre-release - implement more robust feedback handling
                logger.warning(
                    f"Feedback received: {parts[1] if len(parts) > 1 else ''}"
                )
                # update state with special message "feedback received, thank you."
                self.state["special_user_message"] = {
                    "type": "info",
                    "content": "Feedback received, thank you.",
                }
                return self.state  # type: ignore
            else:
                logger.warning(
                    f"Run manager doesn't recognize this command: {cmd}. Continuing."
                )

        if self.exited:
            logger.info("Simulation is exited; skipping graph invocation.")
            return self.state  # type: ignore

        try:
            # if user input, update message_draft to include it
            if user_input is not None:
                if isinstance(user_input, str):
                    self.state["event_draft"] = {
                        "type": "user",
                        "content": user_input,
                    }
                elif isinstance(user_input, Mapping):
                    self.state["event_draft"] = dict(user_input)
                    self.state["event_draft"]["type"] = "user"
                else:
                    raise TypeError(
                        f"user_input must be str or Mapping, got {type(user_input)}"
                    )
                logger.debug(
                    f"Updated state with event_draft: {self.state['event_draft']}"
                )
            # invoke the graph to get new state
            new_state = self.graph.invoke(
                state=self.state,  # dynamic state
                context=self.context,  # static runtime ctx (n/pc, api connections, etc)
                config=self.config,  # runnable config
            )
            self.state = new_state
        except Exception as e:
            logger.exception(f"Error during graph invocation: {e}")
            raise

        return self.state  # type: ignore

    def play(
        self,
        input_provider: Optional[Callable[[], str]] = None,
    ) -> Dict[str, Any]:
        """Run an interactive loop until stopped or stopping conditions met.

        - `input_provider` (optional): function returning the next user string.
          Defaults to built-in `input`.
        """
        provider = input_provider or (lambda: input("user: "))

        self.start_ts = datetime.now()

        while not self.exited:
            try:
                # check simulation state vars/lifecycle for stopping conditions
                # before calling provider
                self._ensure_stopping_conditions()

                events = self.state["events"]
                if not events or len(events) == 0:
                    logger.debug(
                        "No events in state; taking initial graph step to setup scene."
                    )
                    user_text = None
                elif events[-1].type == "ai":
                    user_text = provider()
                elif events[-1].type == "user":
                    user_text = None
                else:
                    raise ValueError(
                        f"Unknown last event type: {events[-1].type}. Cannot continue."
                    )
            except (EOFError, KeyboardInterrupt):
                logger.error("User input was keyboard interrupted.")
                user_text = "/stop"
                self.exit(reason="user interrupted")

            self.step(user_text)  # update state with new messages
            # Note: stopping conditions are checked in step()
            if self.exited:
                break
        return self.state  # type: ignore

    def exit(self, reason: str) -> None:
        """Mark the simulation as exited."""
        if self.exited:
            logger.info("Simulation already exited; skipping exit call.")
        else:
            self.state["lifecycle"] = "EXIT"
            self.exited = True
            self.exit_reason = reason
            self.end_ts = datetime.now()
            self.save()
            logger.info(f"Simulation stopped. Reason: {reason}")
        return

    def save(self, path: Optional[Union[str, Path]] = None) -> Path:
        """Save the simulation locally or to DBClient if persistence is enabled.

        Returns the path written.
        """
        if self.saved:
            logger.info("Run has already been saved; skipping duplicate save.")
            return Path(self.state.get("output_path", ""))  # type: ignore

        run_data = self.model_dump(
            mode="json",  # use json safe vals for datetimes, paths, etc.
            by_alias=True,  # include field aliases in the output
            exclude_none=True,  # skip any None values
        )
        save_to_db = self.game_config.data_collection_settings.get("save_runs", False)
        if save_to_db:
            logger.info("Saving player run to database.")
            try:
                doc_id = dbh.save_run_data(self.player_id, run_data)
                out_path = Path(f"firestore: {doc_id}")
            except Exception as e:
                logger.error(f"Failed to save simulation to Firestore: {e}")

        else:
            logger.info("Player persistence not enabled; saving locally.")
            out_dir = (
                OUTPUT_FPATH
                if path is None
                else Path(path).parent if Path(path).suffix else Path(path)
            )
            fname = (
                f"{self.name}.json" if self.source else f"run_{safe_timestamp()}.json"
            )
            if path is None:
                out_dir = Path(OUTPUT_FPATH)
                out_dir.mkdir(parents=True, exist_ok=True)
                out_path = unique_fpath(out_dir / fname)
            else:
                p = Path(path)
                if p.suffix:
                    p.parent.mkdir(parents=True, exist_ok=True)
                    out_path = p
                else:
                    p.mkdir(parents=True, exist_ok=True)
                    out_path = unique_fpath(p / fname)

            with out_path.open("w", encoding="utf-8") as f:
                json.dump(run_data, f, indent=2, ensure_ascii=False)

        self.state["output_path"] = str(out_path)  # type: ignore
        self.saved = True
        logger.info(f"Run saved to: {out_path}")
        return out_path

    def _ensure_stopping_conditions(self) -> None:
        """Stop the game if any stopping conditions are met from game config.

        Stopping conditions can is a dict with keys that can \
            be any run manager state attribute followed by a string \
                  representation of a boolean condition \
                      (e.g. "user_turns": [">2"], "runtime": [">500"], etc).

        """
        logger.debug("Checking stopping conditions...")

        # check if graph lifecycle has been set to EXIT
        if self.state["lifecycle"] == "EXIT":
            self.exit(
                reason=self.state["exit_reason"]
                or "Game graph lifecycle is EXIT. No reason given."
            )
            return

        # check all other stopping conditions
        conditions = self.stopping_conditions
        if not conditions:
            raise ValueError("stopping_conditions cannot be empty.")

        for attr, cond_list in conditions.items():
            if not hasattr(self, attr):
                logger.error(f"Unknown stopping condition attribute: {attr}. Skipping.")
                continue
            # FIXME: pre-release - verify that this handles @computed_field @properties
            # too like total turns
            attr_value = getattr(self, attr)

            for condition in cond_list:
                try:
                    # numeric compare (">10", "<=3", etc.)
                    if (
                        isinstance(attr_value, (int, float))
                        and condition.strip()[0] in "<>!="
                    ):
                        expr = f"{attr_value}{condition}"
                        if eval(expr):  # noqa: S307 (unchanged behavior)
                            self.exit(
                                reason=f"stopping condition met: {attr} {condition}"
                            )
                            return

                    # string contains
                    elif isinstance(attr_value, str):
                        if condition in attr_value:
                            self.exit(
                                reason=f"stopping condition met: {attr} contains "
                                f"'{condition}'"
                            )
                            return

                except Exception as e:
                    logger.error(
                        f"Error evaluating stopping condition for {attr}='{condition}':"
                        f" {e}"
                    )

    @staticmethod
    def _normalize_and_check_stopping_conditions(
        v: Dict[str, List[str]],
    ) -> Dict[str, List[str]]:
        """Normalize and validate stopping conditions dict."""
        if not v:
            raise ValueError("stopping_conditions cannot be empty.")

        # allowed attrs = model fields + explicit properties
        # NOTE: we can't access cls here, so this helper is used only after
        # class is defined
        allowed = set(RunManager.model_fields.keys()) | {
            "runtime_seconds",
            "runtime",
            "total_turns",
        }

        out: Dict[str, List[str]] = {}
        for attr, conds in v.items():
            if attr not in allowed:
                raise ValueError(f"Unknown stopping condition attribute: {attr}")
            # allow legacy string → list
            if isinstance(conds, str):
                conds = [conds]
            if not isinstance(conds, list) or not conds:
                raise ValueError(
                    f"Conditions for '{attr}' must be a non-empty list of strings."
                )
            for c in conds:
                if not isinstance(c, str):
                    raise ValueError(
                        f"Condition for '{attr}' must be a string, got {type(c)}"
                    )
                cs = c.strip()
                if not cs:
                    raise ValueError(f"Condition for '{attr}' cannot be blank.")
                # very light check: comparison operator or substring token
                if not (cs[0] in "<>!= " or cs):
                    raise ValueError(f"Condition '{c}' for '{attr}' looks invalid.")
            out[attr] = conds
        return out

    @staticmethod
    def _add_stopping_conditions(
        existing_conditions: Dict[str, List[str]], new_conditions: Dict[str, List[str]]
    ) -> None:
        """Append user-defined stopping conditions while preserving existing ones."""
        # DO NOT call the pydantic validator directly; use the pure helper
        new_conditions = RunManager._normalize_and_check_stopping_conditions(
            new_conditions
        )
        for k, new_list in new_conditions.items():
            if k not in existing_conditions:
                existing_conditions[k] = list(new_list)
            else:
                for c in new_list:
                    if c not in existing_conditions[k]:
                        existing_conditions[k].append(c)
