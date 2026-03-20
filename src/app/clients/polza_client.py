from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential


def _polza_retry_predicate(exc: BaseException) -> bool:
    if isinstance(exc, (httpx.TimeoutException, httpx.NetworkError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        return status in {429, 500, 502, 503, 504}
    return False


@dataclass(frozen=True)
class PolzaChatResult:
    content: str
    annotations: list[dict[str, Any]]
    raw: dict[str, Any]


class PolzaChatClient:
    def __init__(self, api_key: str, base_url: str) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._http = httpx.AsyncClient(timeout=120)

    async def aclose(self) -> None:
        self._http.close()

    @retry(
        retry=retry_if_exception(_polza_retry_predicate),
        wait=wait_exponential(min=1, max=20),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    async def chat_completions(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        plugins: list[dict[str, Any]] | None = None,
        temperature: float = 0.2,
        max_tokens: int = 900,
    ) -> PolzaChatResult:
        url = f"{self._base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if plugins:
            body["plugins"] = plugins

        resp = await self._http.post(url, headers=headers, json=body)
        resp.raise_for_status()
        data = resp.json()

        msg = data["choices"][0]["message"]
        content = msg.get("content") or ""
        annotations = msg.get("annotations") or []
        if annotations is None:
            annotations = []
        return PolzaChatResult(content=content, annotations=annotations, raw=data)

