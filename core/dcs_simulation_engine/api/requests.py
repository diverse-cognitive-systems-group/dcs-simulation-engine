import json
from typing import NamedTuple


class AdvanceRequest(NamedTuple):
    text: str
    type: str = "advance"


class StatusRequest(NamedTuple):
    type: str = "status"


class CloseRequest(NamedTuple):
    type: str = "close"


type AnyRequest = AdvanceRequest | StatusRequest | CloseRequest


class APIRequest:
    @staticmethod
    def parse(raw: str) -> AnyRequest:
        data = json.loads(raw)
        kind = data.get("type")
        if kind == "advance":
            return AdvanceRequest(text=data.get("text", ""))
        if kind == "status":
            return StatusRequest()
        if kind == "close":
            return CloseRequest()
        raise ValueError(f"Unknown request type: {kind!r}")
