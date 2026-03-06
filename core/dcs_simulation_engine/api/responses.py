import json
from typing import NamedTuple

from fastapi import WebSocket


class MessageResponse(NamedTuple):
    text: str
    awaiting: str
    type: str = "message"

    def json(self) -> str:
        return json.dumps({"type": self.type, "text": self.text, "awaiting": self.awaiting})


class StatusResponse(NamedTuple):
    session_id: str
    status: str
    type: str = "status"

    def json(self) -> str:
        return json.dumps({"type": self.type, "session_id": self.session_id, "status": self.status})


class ClosedResponse(NamedTuple):
    type: str = "closed"

    def json(self) -> str:
        return json.dumps({"type": self.type})


class ErrorResponse(NamedTuple):
    message: str
    type: str = "error"

    def json(self) -> str:
        return json.dumps({"type": self.type, "message": self.message})


class CreatedResponse(NamedTuple):
    session_id: str
    status: str

    def json(self) -> str:
        return json.dumps({"session_id": self.session_id, "status": self.status})


class APIResponse:
    @staticmethod
    async def message(websocket: WebSocket, *, text: str, awaiting: str) -> None:
        await websocket.send_text(MessageResponse(text=text, awaiting=awaiting).json())

    @staticmethod
    async def status(websocket: WebSocket, *, session_id: str, status: str) -> None:
        await websocket.send_text(StatusResponse(session_id=session_id, status=status).json())

    @staticmethod
    async def closed(websocket: WebSocket) -> None:
        await websocket.send_text(ClosedResponse().json())

    @staticmethod
    async def error(websocket: WebSocket, *, exception: Exception | str) -> None:
        message = str(exception)
        await websocket.send_text(ErrorResponse(message=message).json())
