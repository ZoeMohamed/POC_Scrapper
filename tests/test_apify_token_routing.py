from __future__ import annotations

from app.config import Settings


def test_source_specific_apify_tokens_override_legacy_token() -> None:
    settings = Settings(
        _env_file=None,
        apify_token="legacy",
        apify_maps_token="maps",
        apify_social_token="social",
        apify_marketplace_token="marketplace",
    )

    assert settings.apify_maps_token_value == "maps"
    assert settings.apify_social_token_value == "social"
    assert settings.apify_marketplace_token_value == "marketplace"


def test_legacy_apify_token_remains_the_fallback() -> None:
    settings = Settings(_env_file=None, apify_token="legacy")

    assert settings.apify_maps_token_value == "legacy"
    assert settings.apify_social_token_value == "legacy"
    assert settings.apify_marketplace_token_value == "legacy"
