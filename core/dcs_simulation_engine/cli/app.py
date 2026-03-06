import asyncio
import json

import httpx
import typer
import websockets

app = typer.Typer()

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 8000
# DEFAULT_MODEL = "qwen/qwen3-4b-thinking-2507"
DEFAULT_MODEL = "gpt-4o"
DEFAULT_api_key = ""


@app.command()
def start(
    model: str = typer.Option(DEFAULT_MODEL, help="Model ID to use"),
    game: str = typer.Option("explore", help="Game type: explore, rpg-chat"),
    api_key: str = typer.Option(DEFAULT_api_key, envvar="DCS_api_key", help="User access key"),
    host: str = typer.Option(DEFAULT_HOST, help="API server host"),
    port: int = typer.Option(DEFAULT_PORT, help="API server port"),
) -> None:
    """Start a new game session and enter an interactive loop."""
    asyncio.run(_start(model, game, api_key, host, port))


async def _start(model: str, game: str, api_key: str, host: str, port: int) -> None:
    if not api_key:
        raise typer.BadParameter("Provide --access-key or set DCS_api_key")

    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"http://{host}:{port}/sessions",
            json={"model": model, "game": game, "api_key": api_key},
        )
        r.raise_for_status()
        session_id = r.json()["session_id"]

    typer.echo(f"Session: {session_id}")

    async with websockets.connect(
        f"ws://{host}:{port}/sessions/{session_id}/ws?api_key={api_key}",
        ping_timeout=None,
    ) as ws:
        while True:
            raw = await ws.recv()
            msg = json.loads(raw)

            if msg["type"] == "message":
                typer.echo(f"\n{msg['text']}\n")
                if msg.get("awaiting") == "user_input":
                    text = typer.prompt(">>")
                    await ws.send(json.dumps({"type": "advance", "text": text}))

            elif msg["type"] == "closed":
                typer.echo("Session closed.")
                break

            elif msg["type"] == "error":
                typer.echo(f"Error: {msg['message']}", err=True)
                break


@app.command()
def tui(
    model: str = typer.Option(DEFAULT_MODEL, help="Model ID to use"),
    game: str = typer.Option("explore", help="Game type: explore, rpg-chat"),
    api_key: str = typer.Option(DEFAULT_api_key, envvar="DCS_api_key", help="User access key"),
    host: str = typer.Option(DEFAULT_HOST, help="API server host"),
    port: int = typer.Option(DEFAULT_PORT, help="API server port"),
) -> None:
    """Launch the Textual TUI chat interface."""
    from dcs_simulation_engine.cli.tui import ChatApp

    ChatApp(model=model, game=game, api_key=api_key, host=host, port=port).run()


@app.command()
def status(
    session_id: str = typer.Argument(..., help="Session ID to check"),
    api_key: str = typer.Option(DEFAULT_api_key, envvar="DCS_api_key", help="User access key"),
    host: str = typer.Option(DEFAULT_HOST),
    port: int = typer.Option(DEFAULT_PORT),
) -> None:
    """Check the status of an existing session."""
    asyncio.run(_status(session_id, api_key, host, port))


async def _status(session_id: str, api_key: str, host: str, port: int) -> None:
    if not api_key:
        raise typer.BadParameter("Provide --access-key or set DCS_api_key")
    async with websockets.connect(
        f"ws://{host}:{port}/sessions/{session_id}/ws?api_key={api_key}",
        ping_timeout=None,
    ) as ws:
        await ws.recv()  # discard opening message
        await ws.send(json.dumps({"type": "status"}))
        msg = json.loads(await ws.recv())
        typer.echo(f"Session {msg['session_id']}: {msg['status']}")


@app.command()
def close(
    session_id: str = typer.Argument(..., help="Session ID to close"),
    api_key: str = typer.Option(DEFAULT_api_key, envvar="DCS_api_key", help="User access key"),
    host: str = typer.Option(DEFAULT_HOST),
    port: int = typer.Option(DEFAULT_PORT),
) -> None:
    """Close an existing session."""
    asyncio.run(_close(session_id, api_key, host, port))


async def _close(session_id: str, api_key: str, host: str, port: int) -> None:
    if not api_key:
        raise typer.BadParameter("Provide --access-key or set DCS_api_key")
    async with websockets.connect(
        f"ws://{host}:{port}/sessions/{session_id}/ws?api_key={api_key}",
        ping_timeout=None,
    ) as ws:
        await ws.recv()  # discard opening message
        await ws.send(json.dumps({"type": "close"}))
        msg = json.loads(await ws.recv())
        if msg["type"] == "closed":
            typer.echo(f"Session {session_id} closed.")
