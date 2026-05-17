import json
from pathlib import Path
from typing import Any


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "massive"


def load_massive_fixture(name: str) -> dict:
    with (FIXTURE_ROOT / name).open(encoding="utf-8") as fixture_file:
        return json.load(fixture_file)


class FakeMassiveResponse:
    def __init__(
        self,
        payload: Any,
        status_code: int = 200,
        headers: dict | None = None,
    ):
        self.payload = payload
        self.status_code = status_code
        self.headers = headers or {}
        self.text = str(payload)

    def json(self) -> Any:
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


class FakeMassiveSession:
    def __init__(self, responses: FakeMassiveResponse | list[FakeMassiveResponse]):
        self.responses = list(responses) if isinstance(responses, list) else [responses]
        self.calls = []

    def get(self, url: str, params: dict | None = None, timeout: int | float | None = None) -> FakeMassiveResponse:
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        return self.responses.pop(0)
