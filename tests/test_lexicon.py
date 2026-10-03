import pytest

from app.analyzer.lexicon import LexiconAnalyzer


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("rasanya mantul bgt", "positif"),
        ("barang rusak dan pengiriman telat", "negatif"),
        ("barangnya sudah sampai", "netral"),
    ],
)
async def test_lexicon_basic_sentiment(text: str, expected: str) -> None:
    result = (await LexiconAnalyzer().analyze([("c1", text)]))[0]
    assert result.sentiment == expected


@pytest.mark.asyncio
async def test_negation_flips_polarity_up_to_two_tokens() -> None:
    analyzer = LexiconAnalyzer()
    negative, positive = await analyzer.analyze([
        ("c1", "harganya gak murah"),
        ("c2", "barangnya tidak terlalu jelek"),
    ])
    assert negative.sentiment == "negatif"
    assert positive.sentiment == "positif"


@pytest.mark.asyncio
async def test_indonesian_rhetorical_and_launch_context() -> None:
    analyzer = LexiconAnalyzer()
    rhetorical, launch = await analyzer.analyze([
        ("c1", "Siapa sih yang nggak suka es satu ini?"),
        ("c2", "Akhirnya mulai menunjukkan rasa pertamanya, es cappuccino cincau bisa kamu nikmati"),
    ])
    assert rhetorical.sentiment == "positif"
    assert launch.sentiment == "positif"


@pytest.mark.asyncio
async def test_topics_are_lowercase_and_limited_to_three() -> None:
    result = (await LexiconAnalyzer().analyze([(
        "c1", "Harga, rasa, kemasan, pengiriman dan pelayanan bagus"
    )]))[0]
    assert result.topics == ["harga", "rasa", "kemasan"]


def test_each_lexicon_contains_at_least_eighty_words() -> None:
    analyzer = LexiconAnalyzer()
    assert len(analyzer.positive) >= 80
    assert len(analyzer.negative) >= 80
