import asyncio
import json
import sys
import threading

import gradio as gr
import httpx
import websockets

API_BASE = "http://localhost:8000"
WS_BASE = "ws://localhost:8000"

GAME_TYPES = ["explore", "rpg-chat"]

# A single background event loop shared across all sessions
_loop = asyncio.new_event_loop()
threading.Thread(target=_loop.run_forever, daemon=True).start()


def run(coro):
    """Run a coroutine on the background loop and block until done."""
    return asyncio.run_coroutine_threadsafe(coro, _loop).result()


def _create_session_http(game: str, model: str, api_key: str | None) -> str:
    resp = httpx.post(
        f"{API_BASE}/sessions",
        json={"game": game, "model": model, "api_key": api_key},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["session_id"]


async def _open_ws(sid: str, api_key: str):
    ws = await websockets.connect(f"{WS_BASE}/sessions/{sid}/ws?api_key={api_key}")
    opening_raw = await ws.recv()
    opening = json.loads(opening_raw)
    return ws, opening.get("text", "")


async def _send(ws, text: str) -> dict:
    await ws.send(json.dumps({"type": "advance", "text": text}))
    raw = await ws.recv()
    return json.loads(raw)


async def _close_ws(ws) -> None:
    try:
        await ws.send(json.dumps({"type": "close"}))
        await ws.recv()
    except Exception:
        pass
    finally:
        await ws.close()


def open_session(game: str, model: str, state: dict, auth: dict) -> tuple[list[dict], dict]:
    """Close any existing session, create a new one, return opening message."""
    if state.get("ws"):
        run(_close_ws(state["ws"]))

    try:
        api_key = auth.get("api_key")
        if not api_key:
            raise ValueError("Please login first to get an access key.")
        sid = _create_session_http(game, model, api_key)
        ws, opening_text = run(_open_ws(sid, api_key))
    except Exception as e:
        return [{"role": "assistant", "content": f"Error: {e}"}], {}

    new_state = {"session_id": sid, "ws": ws}
    history = [{"role": "assistant", "content": opening_text}]
    return history, new_state


def chat(
    user_message: str,
    history: list[dict],
    state: dict,
    game: str,
    model: str,
    auth: dict,
) -> tuple[list[dict], dict]:
    if not user_message.strip():
        return history, state

    ws = state.get("ws")

    if ws is None:
        history, state = open_session(game, model, state, auth)
        ws = state.get("ws")
        if ws is None:
            return history, state

    new_history = list(history)
    new_history.append({"role": "user", "content": user_message})

    try:
        msg = run(_send(ws, user_message))
        if msg.get("type") == "message":
            new_history.append({"role": "assistant", "content": msg["text"]})
        elif msg.get("type") == "error":
            new_history.append({"role": "assistant", "content": f"Error: {msg['message']}"})
    except Exception as e:
        new_history.append({"role": "assistant", "content": f"Connection error: {e}"})
        state = {k: v for k, v in state.items() if k != "ws"}

    return new_history, state


def reset_session(state: dict) -> tuple[list, dict]:
    ws = state.get("ws")
    if ws:
        run(_close_ws(ws))
    return [], {}


def login_user(email: str, password: str, auth: dict) -> tuple[str, dict, gr.update]:
    try:
        resp = httpx.post(
            f"{API_BASE}/users/login",
            json={"email": email, "password": password},
            timeout=10,
        )
        if resp.status_code == 401:
            return "Invalid email or password.", auth, gr.update(visible=False)
        resp.raise_for_status()
        data = resp.json()
        new_auth = {"user_id": data["user_id"], "api_key": data["api_key"]}
        return (
            f"Logged in! User ID: {data['user_id']}\nAccess key: {data['api_key']}",
            new_auth,
            gr.update(visible=True),
        )
    except Exception as e:
        return f"Error: {e}", auth, gr.update(visible=False)


def register_user(
    password: str,
    full_name: str,
    email: str,
    phone_number: str,
    prior_experience: str,
    additional_comments: str,
    consent_email: bool,
    consent_phone: bool,
    consent_signature: bool,
) -> str:
    
    follow_up = []
    if consent_email:
        follow_up.append("email")
    if consent_phone:
        follow_up.append("phone")


    payload = {
        "password": password or None,
        "full_name": full_name or None,
        "email": email or None,
        "phone_number": phone_number or None,
        "prior_experience": prior_experience or None,
        "additional_comments": additional_comments or None,
        "consent_to_followup": follow_up or None,
        "consent_signature": consent_signature,
    }
    try:
        resp = httpx.post(f"{API_BASE}/users/register", json=payload, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return f"Registered!\nuser_id: {data['user_id']}"
    except Exception as e:
        return f"Error: {e}"


with gr.Blocks(title="DCS Simulation Engine") as demo:
    gr.Markdown("## DCS Simulation Engine")

    # Persists user_id and api_key across tabs after login
    auth = gr.State({})

    with gr.Tabs():
        with gr.Tab("Game", visible=False) as game_tab:
            state = gr.State({})

            with gr.Row():
                game_dropdown = gr.Dropdown(choices=GAME_TYPES, value="rpg-chat", label="Game type", scale=1)
                model_input = gr.Textbox(value="gpt-4o", label="Model", scale=2)
                start_btn = gr.Button("Start / New session", variant="primary", scale=1)

            chatbot = gr.Chatbot(height=500, label="Chat")
            msg_input = gr.Textbox(placeholder="Type your message and press Enter…", label="Your message", scale=4)

            with gr.Row():
                send_btn = gr.Button("Send", variant="primary")
                reset_btn = gr.Button("Reset session")

            start_btn.click(
                fn=open_session,
                inputs=[game_dropdown, model_input, state, auth],
                outputs=[chatbot, state],
            )

            send_inputs = [msg_input, chatbot, state, game_dropdown, model_input, auth]
            send_outputs = [chatbot, state]

            msg_input.submit(fn=chat, inputs=send_inputs, outputs=send_outputs).then(lambda: "", outputs=msg_input)
            send_btn.click(fn=chat, inputs=send_inputs, outputs=send_outputs).then(lambda: "", outputs=msg_input)
            reset_btn.click(fn=reset_session, inputs=[state], outputs=[chatbot, state])

        with gr.Tab("Login"):
            login_email = gr.Textbox(label="Email")
            login_password = gr.Textbox(label="Password", type="password")
            login_btn = gr.Button("Login", variant="primary")
            login_result = gr.Textbox(label="Result", interactive=False)

            login_btn.click(
                fn=login_user,
                inputs=[login_email, login_password, auth],
                outputs=[login_result, auth, game_tab],
            )

        with gr.Tab("Register"):
            reg_full_name = gr.Textbox(label="Full name")
            reg_email = gr.Textbox(label="Email")
            reg_phone = gr.Textbox(label="Phone number")
            reg_password = gr.Textbox(label="Password", type="password")
            reg_experience = gr.Textbox(label="Prior experience", lines=3)
            reg_comments = gr.Textbox(label="Additional comments", lines=3)
            reg_consent_email = gr.Checkbox(label="Consent to followup by email")
            reg_consent_phone = gr.Checkbox(label="Consent to followup by phone")
            reg_signature = gr.Checkbox(label="Consent signature")
            reg_btn = gr.Button("Register", variant="primary")
            reg_result = gr.Textbox(label="Result", interactive=False)

            reg_btn.click(
                fn=register_user,
                inputs=[reg_password, reg_full_name, reg_email, reg_phone,
                        reg_experience, reg_comments, reg_consent_email, reg_consent_phone, reg_signature],
                outputs=reg_result,
            )


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 7860
    demo.launch(server_port=port)


if __name__ == "__main__":
    main()
