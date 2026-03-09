"""Python client wrapper for the DCS Simulation Engine Gradio API.

Provides DCSClient and SimulationRun for ergonomic use in research scripts.

Typical usage::

    from dcs_simulation_engine.client import DCSClient

    client = DCSClient("http://localhost:8080")

    with client.create_run(game="explore", pc="human-non-hearing", npc="thermostat") as run:
        run.step()                          # initial step, empty input
        run.step("You smell the thermostat")
        print(run.simulator_output)         # content string
        run.save()
    # run is automatically deleted on context exit
"""

from typing import Any, Dict, Optional, Self

from dcs_simulation_engine.errors import DCSError
from gradio_client import Client


def _check_error(result: Dict[str, Any]) -> Dict[str, Any]:
    """Raise DCSError if the API returned an error dict.

    Args:
        result: The raw dict returned by a Gradio predict call.

    Returns:
        The same result dict if no error key is present.

    Raises:
        DCSError: If the result contains an "error" key.
    """
    if "error" in result:
        raise DCSError(result["error"])
    return result


class SimulationRun:
    """Lightweight wrapper around an active simulation run.

    Holds the run_id and the most recent state/meta returned by the API.
    All API calls are delegated back to the parent DCSClient.

    Supports use as a context manager. On exit it automatically calls delete_run
    to clean up the server-side registry entry.

    Example::

        with client.create_run(game="explore", pc="human-non-hearing", npc="thermostat") as run:
            run.step()
            run.step("You smell the thermostat")
            print(run.simulator_output)
            run.save()
    """

    def __init__(
        self,
        client: "DCSClient",
        run_id: str,
        game_name: str,
        pc: Dict[str, Any],
        npc: Dict[str, Any],
        state: Dict[str, Any],
        meta: Dict[str, Any],
    ) -> None:
        """Initialize a SimulationRun instance."""
        self._client = client
        self.run_id = run_id
        self.game_name = game_name
        self.pc = pc
        self.npc = npc
        self._state: Dict[str, Any] = state
        self._meta: Dict[str, Any] = meta

    def __enter__(self) -> Self:
        """Enter the runtime context related to this object."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit the runtime context and clean up the run on the server."""
        try:
            self._client.delete_run(self.run_id)
        except Exception:
            pass  # don't mask the original exception with a cleanup error

    def step(self, user_input: str = "") -> Self:
        """Advance the simulation by one step.

        Args:
            user_input: Text input from the user. Pass an empty string (default)
                for the initial step or any step that requires no user input.

        Returns:
            self, enabling optional method chaining.

        Raises:
            DCSError: If the server returns an error response.
        """
        result = self._client._predict_step(self.run_id, user_input)
        self._state = result["state"]
        self._meta = result["meta"]
        return self

    def get_state(self) -> Self:
        """Fetch the current server-side state without advancing the simulation.

        Useful when you need to verify state without triggering a step, or after
        out-of-band operations.

        Returns:
            self, with state and meta updated from the server.

        Raises:
            DCSError: If the server returns an error response.
        """
        result = self._client._predict_get_state(self.run_id)
        self._state = result["state"]
        self._meta = result["meta"]
        return self

    def save(self, output_dir: Optional[str] = None) -> str:
        """Save the run outputs to the server's configured destination.

        The server decides where to save (local filesystem path or Firestore
        document, depending on game configuration). The returned string is the
        server-reported output path or document ID.

        Args:
            output_dir: Optional path hint passed to the server. If None, the
                server uses its configured default output directory.

        Returns:
            The output path string as reported by the server.

        Raises:
            DCSError: If the server returns an error response.
        """
        result = self._client._predict_save(self.run_id, output_dir)
        return result.get("output_path", "")

    @property
    def raw_state(self) -> Dict[str, Any]:
        """The full SimulationGraphState dict from the last API call.

        Use this when you need fields not exposed by convenience properties,
        such as forms, scratchpad, or validator/updater responses.
        """
        return self._state

    @property
    def meta(self) -> Dict[str, Any]:
        """The meta dict from the last API call.

        Contains: name, turns, runtime_seconds, runtime_string,
        exited, exit_reason, saved, output_path.
        """
        return self._meta

    @property
    def lifecycle(self) -> str:
        """The current lifecycle stage: INIT, ENTER, UPDATE, EXIT, or COMPLETE."""
        return self._state.get("lifecycle", "")

    @property
    def is_complete(self) -> bool:
        """True if the simulation has exited or reached the COMPLETE lifecycle."""
        return self._meta.get("exited", False) or self.lifecycle in ("EXIT", "COMPLETE")

    @property
    def simulator_output(self) -> Optional[str]:
        """The content of the simulator's last output message, or None.

        Returns just the content string. Access raw_state["simulator_output"]
        if you also need the message type field.
        """
        msg = self._state.get("simulator_output")
        return msg.get("content") if msg else None

    @property
    def user_input(self) -> Optional[str]:
        """The content of the last user input echoed in state, or None."""
        msg = self._state.get("user_input")
        return msg.get("content") if msg else None

    @property
    def history(self) -> list[dict[str, Any]]:
        """The full message history from state.

        Each entry is a LangChain message dict with at minimum "type" and
        "content" keys.
        """
        return self._state.get("history", [])

    @property
    def turns(self) -> int:
        """Number of completed turns as reported by the server meta."""
        return self._meta.get("turns", 0)

    @property
    def exit_reason(self) -> str:
        """The exit reason string, or empty string if not exited."""
        return self._meta.get("exit_reason", "")


class DCSClient:
    """Client for the DCS Simulation Engine Gradio API.

    Wraps raw gradio_client.Client calls with a clean interface. Use
    create_run() to get a SimulationRun, preferably as a context manager.

    Example::

        client = DCSClient("http://localhost:8080")

        with client.create_run(game="explore", pc="human-non-hearing", npc="thermostat") as run:
            run.step()
            run.step("You smell the thermostat")
            print(run.simulator_output)
            run.save()

    Args:
        url: Base URL of the running DCS Gradio server.
    """

    def __init__(self, url: str = "http://localhost:8080") -> None:
        """Initialize the DCSClient with the given server URL."""
        self._gradio = Client(url)

    def create_run(
        self,
        game: str,
        pc: Optional[str] = None,
        npc: Optional[str] = None,
        source: str = "api",
        access_key: str = "",
        player_id: str = "",
    ) -> SimulationRun:
        """Create a new simulation run and return a SimulationRun wrapper.

        Args:
            game: Game name (e.g. "explore", "Foresight", "Goal Horizon").
            pc: Player character HID (e.g. "human-non-hearing"). If None, the
                server selects randomly from valid choices.
            npc: Non-player character HID (e.g. "thermostat"). If None, the
                server selects randomly from valid choices.
            source: Run source tag for naming/tracking. Defaults to "api".
            access_key: Access key for player identity resolution. Required for
                consent-gated games.
            player_id: Explicit player ID. Takes precedence over access_key if
                the server resolves both.

        Returns:
            A SimulationRun instance. Use as a context manager for auto-cleanup.

        Raises:
            DCSError: If the server returns an error (e.g. invalid game name,
                invalid pc/npc choice, player not authorized).
        """
        result = self._gradio.predict(
            game=game,
            source=source,
            pc_choice=pc or "",
            npc_choice=npc or "",
            access_key=access_key,
            player_id=player_id,
            api_name="/create_run",
        )
        _check_error(result)
        # create_run returns no state snapshot; state is populated on first step()
        return SimulationRun(
            client=self,
            run_id=result["run_id"],
            game_name=result["game_name"],
            pc=result["pc"],
            npc=result["npc"],
            state={},
            meta=result["meta"],
        )

    def delete_run(self, run_id: str) -> None:
        """Delete a run from the server registry.

        Called automatically by SimulationRun.__exit__. May also be called
        manually when not using the context manager.

        Args:
            run_id: The run identifier to delete.

        Raises:
            DCSError: If the server returns an error response.
        """
        result = self._gradio.predict(run_id=run_id, api_name="/delete_run")
        _check_error(result)

    def _predict_step(self, run_id: str, user_input: str) -> Dict[str, Any]:
        result = self._gradio.predict(
            run_id=run_id,
            user_input=user_input,
            api_name="/step_run",
        )
        return _check_error(result)

    def _predict_get_state(self, run_id: str) -> Dict[str, Any]:
        result = self._gradio.predict(run_id=run_id, api_name="/get_state")
        return _check_error(result)

    def _predict_save(self, run_id: str, output_dir: Optional[str]) -> Dict[str, Any]:
        kwargs: Dict[str, Any] = {"run_id": run_id, "api_name": "/save_run"}
        if output_dir is not None:
            kwargs["output_dir"] = output_dir
        result = self._gradio.predict(**kwargs)
        return _check_error(result)
