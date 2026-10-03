from __future__ import annotations

import pytest

from app.youtube.content_type import ContentTypeClassifier, classify_by_rules


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Review jujur kopi gula aren, worth it?", "review"),
        ("Resep dan cara bikin seblak rumahan", "resep"),
        ("Ide usaha seblak modal kecil untung besar", "ide_usaha"),
        ("Festival kuliner Bandung 2026", "review"),
        ("Berita ekonomi hari ini", "lainnya"),
    ],
)
def test_rule_classifier(title: str, expected: str) -> None:
    assert classify_by_rules(title) == expected


def test_rule_tie_uses_business_priority() -> None:
    assert classify_by_rules("Resep ide usaha jualan kopi") == "ide_usaha"


@pytest.mark.asyncio
async def test_classifier_falls_back_when_gemini_fails() -> None:
    async def broken(_items: list[tuple[str, str]]) -> dict[str, str]:
        raise RuntimeError("offline")

    classifier = ContentTypeClassifier("auto", broken)
    assert await classifier.classify([("one", "Tutorial cara membuat bakso")]) == {"one": "resep"}


@pytest.mark.asyncio
async def test_classifier_accepts_valid_fake_gemini_result() -> None:
    async def fake(_items: list[tuple[str, str]]) -> dict[str, str]:
        return {"one": "ide_usaha", "two": "tidak-valid"}

    classifier = ContentTypeClassifier("auto", fake)
    result = await classifier.classify([
        ("one", "Video produk baru"),
        ("two", "Cara bikin seblak"),
    ])
    assert result == {"one": "ide_usaha", "two": "resep"}
