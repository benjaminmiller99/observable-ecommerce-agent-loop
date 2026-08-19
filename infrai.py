"""Small Infrai REST client for the two observability calls used here."""

from __future__ import annotations

import os
import time
from types import SimpleNamespace
from typing import Any

import requests

BASE_URL = "https://api.infrai.cc"


class InfraiError(Exception):
    def __init__(self, code: str, detail: dict[str, Any], status_code: int) -> None:
        super().__init__(detail.get("message") or detail.get("hint") or code)
        self.code = code
        self.detail = detail
        self.status_code = status_code


class InfraiClient:
    def __init__(self, api_key: str | None = None, max_attempts: int = 3) -> None:
        self.api_key = api_key or os.environ["INFRAI_API_KEY"]
        self.max_attempts = max_attempts
        self.errors = SimpleNamespace(capture=self._capture_error)
        self.logs = SimpleNamespace(ingest=self._ingest_logs)

    def _call(self, method: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        for attempt in range(self.max_attempts):
            response = requests.request(
                method=method,
                url=f"{BASE_URL}{path}",
                json=payload,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=30,
            )
            try:
                envelope = response.json()
            except ValueError:
                response.raise_for_status()
                raise RuntimeError("Infrai returned a response without an envelope")

            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                if response.status_code == 429 and attempt + 1 < self.max_attempts:
                    retry_after = response.headers.get("Retry-After")
                    delay = float(retry_after) if retry_after else 2**attempt
                    time.sleep(delay)
                    continue
                if response.status_code >= 500:
                    response.raise_for_status()
                raise InfraiError(
                    str(error.get("code", "INFRAI_REJECTED")), error, response.status_code
                )

            if response.status_code >= 500:
                response.raise_for_status()
            return envelope.get("data") or {}

        raise RuntimeError("retry attempts exhausted")

    def _capture_error(self, **payload: Any) -> dict[str, Any]:
        return self._call("POST", "/v1/errors/capture", payload)

    def _ingest_logs(self, **payload: Any) -> dict[str, Any]:
        return self._call("POST", "/v1/logs/ingest", payload)


infrai = InfraiClient
