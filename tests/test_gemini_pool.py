from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.analyzer.gemini_pool import GeminiClientPool
from app.config import Settings


class _Models:
    def __init__(self, *, error: Exception | None = None, value: object = None) -> None:
        self.error = error
        self.value = value
        self.calls = 0

    async def generate_content(self, **kwargs: object) -> object:
        self.calls += 1
        if self.error:
            raise self.error
        return self.value


def _client(models: _Models) -> SimpleNamespace:
    return SimpleNamespace(aio=SimpleNamespace(models=models))


@pytest.mark.asyncio
async def test_pool_rotates_after_quota_error() -> None:
    quota = RuntimeError("RESOURCE_EXHAUSTED quota")
    first = _Models(error=quota)
    second = _Models(value={"ok": True})
    pool = GeminiClientPool(client=_client(first))
    pool._clients = [_client(first), _client(second)]
    pool._cursor = 0

    result = await pool.generate_content(model="fake", contents="test")
    assert result == {"ok": True}
    assert first.calls == 1
    assert second.calls == 1


@pytest.mark.asyncio
async def test_pool_does_not_hide_non_credential_errors() -> None:
    models = _Models(error=RuntimeError("schema response invalid"))
    pool = GeminiClientPool(client=_client(models))
    with pytest.raises(RuntimeError, match="schema response invalid"):
        await pool.generate_content(model="fake", contents="test")


def test_settings_merge_and_deduplicate_gemini_keys() -> None:
    settings = Settings(
        _env_file=None,
        gemini_api_key="primary",
        gemini_api_keys="secondary, primary\nthird;secondary",
    )
    assert settings.gemini_api_key_values == ["primary", "secondary", "third"]
