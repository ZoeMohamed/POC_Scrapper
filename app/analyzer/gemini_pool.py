"""Small server-side Gemini client pool with quota-aware key rotation."""

from __future__ import annotations

import secrets
from typing import Any, Iterable


class GeminiPoolExhaustedError(RuntimeError):
    """All configured credentials were unavailable for the current request."""


def is_retryable_key_error(exc: Exception) -> bool:
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    message = str(exc).casefold()
    return code in {401, 403, 429} or any(
        signal in message
        for signal in (
            "resource exhausted",
            "quota",
            "rate limit",
            "api key not valid",
            "api_key_invalid",
            "permission denied",
        )
    )


class GeminiClientPool:
    def __init__(
        self, keys: Iterable[str] = (), *, client: Any | None = None
    ) -> None:
        if client is not None:
            self._clients = [client]
        else:
            unique = list(dict.fromkeys(key.strip() for key in keys if key.strip()))
            if not unique:
                raise ValueError("GEMINI_API_KEY atau GEMINI_API_KEYS wajib diisi")
            try:
                from google import genai
            except ImportError as exc:  # pragma: no cover - deployment dependency guard
                raise RuntimeError("Paket google-genai belum terpasang") from exc
            self._clients = [genai.Client(api_key=key) for key in unique]
        self._cursor = secrets.randbelow(len(self._clients))

    @property
    def size(self) -> int:
        return len(self._clients)

    async def generate_content(self, **kwargs: Any) -> Any:
        last_error: Exception | None = None
        for offset in range(len(self._clients)):
            index = (self._cursor + offset) % len(self._clients)
            try:
                response = await self._clients[index].aio.models.generate_content(**kwargs)
            except Exception as exc:
                if not is_retryable_key_error(exc):
                    raise
                last_error = exc
                continue
            self._cursor = (index + 1) % len(self._clients)
            return response
        raise GeminiPoolExhaustedError(
            "Semua key Gemini sedang kehabisan kuota atau tidak tersedia"
        ) from last_error
