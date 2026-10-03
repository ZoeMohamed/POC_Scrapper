from types import SimpleNamespace

import pytest

from app.analyzer.base import AnalyzerError
from app.analyzer.gemini import GeminiAnalyzer, SYSTEM_PROMPT, parse_response


def test_parse_valid_response_maps_short_ids_and_cleans_values() -> None:
    raw = '[{"i":"c1","s":"positif","sc":1.8,"tp":[" Harga ","RASA","promo","lebih"]}]'
    result = parse_response(raw, {"c1": "rp_original"})
    assert result[0].id == "rp_original"
    assert result[0].score == 1.0
    assert result[0].topics == ["harga", "rasa", "promo"]


def test_parse_rejects_broken_json() -> None:
    with pytest.raises(AnalyzerError):
        parse_response("bukan json", {"c1": "rp_1"})


def test_parse_ignores_foreign_id_and_leaves_missing_id_absent() -> None:
    raw = [
        {"i": "c1", "s": "netral", "sc": 0, "tp": []},
        {"i": "asing", "s": "negatif", "sc": -1, "tp": []},
    ]
    result = parse_response(raw, {"c1": "rp_1", "c2": "rp_2"})
    assert [item.id for item in result] == ["rp_1"]


def test_gemini_prompt_explains_indonesian_rhetorical_negation() -> None:
    assert "Siapa sih yang nggak suka" in SYSTEM_PROMPT
    assert "positif" in SYSTEM_PROMPT
    assert "pernah gagal" in SYSTEM_PROMPT


class _FakeModels:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def generate_content(self, **kwargs: object) -> SimpleNamespace:
        self.calls.append(kwargs)
        return SimpleNamespace(parsed=[{"i": "c1", "s": "positif", "sc": 0.7, "tp": []}])


@pytest.mark.asyncio
async def test_analyzer_batches_items_in_one_sdk_request() -> None:
    models = _FakeModels()
    client = SimpleNamespace(aio=SimpleNamespace(models=models))
    analyzer = GeminiAnalyzer(client=client, model="fake-model")
    result = await analyzer.analyze([("long-id-1", "bagus"), ("long-id-2", "biasa")])
    assert len(models.calls) == 1
    assert models.calls[0]["contents"] == '[{"i":"c1","t":"bagus"},{"i":"c2","t":"biasa"}]'
    assert [item.id for item in result] == ["long-id-1"]
