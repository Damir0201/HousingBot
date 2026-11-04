import asyncio
from typing import Protocol

import httpx

from app.config import get_settings
from app.infrastructure.llm.schemas import ChatMessage, ToolDefinition
from app.shared.exceptions import ExternalServiceError
from app.shared.logging import get_logger

log = get_logger(__name__)

RETRY_STATUSES = {408, 409, 429, 500, 502, 503, 504}


class LLMClient(Protocol):
    async def chat(
        self, messages: list[ChatMessage], tools: list[ToolDefinition] | None = None
    ) -> ChatMessage: ...


class OpenAICompatibleClient:
    """Minimal client for any OpenAI-compatible `/chat/completions` endpoint
    (OpenAI, Azure, OpenRouter, vLLM, Ollama, ...)."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        *,
        temperature: float = 0.3,
        timeout: float = 30.0,
        max_retries: int = 3,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._model = model
        self._temperature = temperature
        self._max_retries = max_retries
        self._http = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
            transport=transport,
        )

    async def chat(
        self, messages: list[ChatMessage], tools: list[ToolDefinition] | None = None
    ) -> ChatMessage:
        payload: dict[str, object] = {
            "model": self._model,
            "temperature": self._temperature,
            "messages": [m.to_api() for m in messages],
        }
        if tools:
            payload["tools"] = [t.to_api() for t in tools]
            payload["tool_choice"] = "auto"

        for attempt in range(1, self._max_retries + 1):
            try:
                response = await self._http.post("/chat/completions", json=payload)
                if response.status_code in RETRY_STATUSES and attempt < self._max_retries:
                    raise httpx.HTTPStatusError("retryable", request=response.request, response=response)
                response.raise_for_status()
                data = response.json()
                return ChatMessage.model_validate(data["choices"][0]["message"])
            except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                if attempt >= self._max_retries:
                    log.error("llm.request_failed", error=str(exc))
                    raise ExternalServiceError("LLM request failed") from exc
                await asyncio.sleep(0.5 * 2 ** (attempt - 1))
        raise ExternalServiceError("LLM request failed")  # pragma: no cover

    async def aclose(self) -> None:
        await self._http.aclose()


def build_llm_client() -> OpenAICompatibleClient | None:
    settings = get_settings()
    if not settings.llm_enabled:
        return None
    return OpenAICompatibleClient(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key.get_secret_value(),
        model=settings.llm_model,
        temperature=settings.llm_temperature,
        timeout=settings.llm_timeout,
    )
