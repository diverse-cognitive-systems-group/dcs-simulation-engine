import asyncio
import json
from datetime import datetime
from typing import Any, Callable, Coroutine

import httpx
import websockets
from rich.text import Text
from textual import events
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Header, Label, LoadingIndicator, RichLog, TextArea

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 8000
DEFAULT_MODEL = "gpt-4o"


def _timestamp() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _chat_line(speaker: str, color: str, body: str) -> Text:
    """Build a Rich Text block for a single chat turn.

    Uses Text objects (not markup strings) so whitespace in the message body
    is preserved exactly as-is.
    """
    t = Text()
    t.append(f"{speaker} ", style=f"bold {color}")
    t.append(f"{_timestamp()}\n", style="dim")
    t.append(body)
    return t


class ChatInput(TextArea):
    """Multi-line text input with custom key bindings.

    - Enter   → submit the message
    - Shift+Enter → insert a literal newline (default TextArea behavior
                    is intercepted here to avoid the backslash artifact)

    We override `_on_key` instead of using a keybinding because TextArea
    calls `event.stop()` internally before key events bubble, so app-level
    handlers never fire.
    """

    def __init__(self, on_submit: Callable[[], Coroutine[Any, Any, None]], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._on_submit_cb = on_submit

    async def _on_key(self, event: events.Key) -> None:
        if event.key == "enter":
            # Consume the event so TextArea doesn't insert a newline, then submit.
            event.stop()
            event.prevent_default()
            await self._on_submit_cb()

        elif event.key == "shift+enter":
            # Insert a real newline at the cursor position using the internal
            # keyboard-replacement API (avoids the backslash rendering bug).
            event.stop()
            event.prevent_default()
            start, end = self.selection
            self._replace_via_keyboard("\n", start, end)

        else:
            await super()._on_key(event)


class ChatApp(App):
    CSS = """
    /* Main column fills the whole screen */
    Vertical {
        height: 1fr;
    }

    /* Scrollable chat history */
    RichLog {
        border: solid $primary;
        padding: 0 1;
        height: 1fr;
    }

    /* Loading spinner: hidden by default, shown via the .visible class */
    #loading {
        height: 1;
        margin: 0 1;
        display: none;
    }
    #loading.visible {
        display: block;
    }

    /* Multi-line message input */
    ChatInput {
        height: 6;
        margin: 0;
        border: solid $panel;
    }
    ChatInput:focus {
        border: solid $primary;
    }
    ChatInput:disabled {
        opacity: 0.4;
    }

    /* Bottom action bar: buttons on the left, info labels on the right */
    Horizontal {
        height: 1;
    }
    Button {
        width: 20;
        padding: 0;
        height: 1;
        background: $panel;
        color: $text-muted;
        border: none;
    }
    Button:hover {
        background: $success;
        color: $text;
    }
    Label {
        width: 1fr;
        height: 1;
        color: $text-muted;
        text-align: right;
    }
    """

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        game: str = "explore",
        api_key: str = "",
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
    ) -> None:
        super().__init__()
        self.title = "dcs-simulation-engine"
        self.model = model
        self.game = game
        self.api_key = api_key
        self.host = host
        self.port = port

        # WebSocket state
        self._ws: websockets.ClientConnection | None = None
        self._session_id: str | None = None
        self._receive_task: asyncio.Task | None = None

        # True while waiting for an agent response
        self._waiting = False

        # Cleared to True once the first message arrives, so we can wipe the
        # "Connecting…" splash before showing the opening agent message.
        self._connected = False

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            yield RichLog(id="log", markup=False, wrap=True)
            yield LoadingIndicator(id="loading")
            yield ChatInput(on_submit=self._submit, id="input")
            with Horizontal():
                # Action buttons (left-justified)
                yield Button("Reset", id="reset")
                yield Button("Quit", id="quit")
                # Session info (right-justified via Label CSS above)
                yield Label(f"model={self.model}", id="info-model")
                yield Label(f"game={self.game}", id="info-game")
                yield Label(f"host={self.host}:{self.port}", id="info-host")
                yield Label(f"auth={'set' if self.api_key else 'missing'}", id="info-auth")

    async def on_mount(self) -> None:
        self.query_one(ChatInput).focus()

        # Show connection details while the session is being created
        log = self.query_one(RichLog)
        connection_info = json.dumps(
            {"host": f"http://{self.host}:{self.port}", "game": self.game, "model": self.model},
            indent=2,
        )
        log.write(Text(f"Connecting to simulation engine server...\n{connection_info}", style="green"))

        await self._connect()

    def _set_waiting(self, waiting: bool) -> None:
        """Toggle the loading spinner and enable/disable the input box."""
        self._waiting = waiting
        input_widget = self.query_one(ChatInput)
        loading = self.query_one(LoadingIndicator)

        input_widget.disabled = waiting

        if waiting:
            loading.add_class("visible")
        else:
            loading.remove_class("visible")
            input_widget.focus()

    async def _submit(self) -> None:
        """Send the current input text to the agent as an advance request."""
        input_widget = self.query_one(ChatInput)
        text = input_widget.text.strip()

        # Ignore empty input or submission while a response is in flight
        if not text or self._ws is None or self._waiting:
            return

        input_widget.clear()
        self.query_one(RichLog).write(_chat_line("You", "green", text))
        self._set_waiting(True)
        await self._ws.send(json.dumps({"type": "advance", "text": text}))

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "quit":
            await self._close_session()
            self.exit()

        elif event.button.id == "reset":
            await self._close_session()
            self.query_one(RichLog).clear()
            self._connected = False
            await self._connect()

    async def _connect(self) -> None:
        """Create a new server session and open a WebSocket connection to it."""
        log = self.query_one(RichLog)
        self._set_waiting(True)

        # Step 1: POST /sessions to create a session and get its ID
        try:
            if not self.api_key:
                raise ValueError("missing access key")
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"http://{self.host}:{self.port}/sessions",
                    json={"model": self.model, "game": self.game, "api_key": self.api_key},
                )
                response.raise_for_status()
                self._session_id = response.json()["session_id"]
        except Exception as e:
            log.write(Text(f"Failed to create session: {e}", style="red"))
            self._set_waiting(False)
            return

        # Step 2: Open a WebSocket to the session's streaming endpoint
        try:
            self._ws = await websockets.connect(
                f"ws://{self.host}:{self.port}/sessions/{self._session_id}/ws?api_key={self.api_key}",
                ping_timeout=None,  # disable keep-alive pings; we manage the lifecycle manually
            )
        except Exception as e:
            log.write(Text(f"Failed to connect WebSocket: {e}", style="red"))
            self._set_waiting(False)
            return

        # Step 3: Start the background task that reads incoming messages
        self._receive_task = asyncio.create_task(self._receive_loop())

    async def _receive_loop(self) -> None:
        """Background task: read messages from the WebSocket and update the log."""
        log = self.query_one(RichLog)
        assert self._ws is not None  # always called immediately after a successful _connect
        try:
            async for raw in self._ws:
                self._set_waiting(False)
                msg = json.loads(raw)

                # Clear the "Connecting…" splash on the very first message
                if not self._connected:
                    log.clear()
                    self._connected = True

                match msg.get("type"):
                    case "message":
                        log.write(_chat_line("Agent", "cyan", msg["text"]))
                    case "error":
                        log.write(Text(f"Error: {msg['message']}", style="red"))
                    case "closed":
                        log.write(Text("Session closed.", style="dim"))

        except Exception:
            # Connection dropped unexpectedly; clear the spinner
            self._set_waiting(False)

    async def _close_session(self) -> None:
        """Gracefully close the current session and clean up state."""
        self._set_waiting(False)

        # Cancel the receive loop first so it doesn't race with the close handshake
        if self._receive_task:
            self._receive_task.cancel()
            self._receive_task = None

        if self._ws:
            try:
                # Ask the server to close the session cleanly
                await self._ws.send(json.dumps({"type": "close"}))
                await self._ws.recv()  # consume the server's "closed" acknowledgement
            except Exception:
                pass  # socket may already be gone; that's fine
            finally:
                await self._ws.close()
                self._ws = None
