from app.nlp.keywords import load_stopwords, top_keywords


def test_stopword_corpus_has_at_least_two_hundred_words() -> None:
    assert len(load_stopwords()) >= 200


def test_keywords_exclude_stopwords_and_product_terms() -> None:
    texts = [
        "kopi aren ini rasanya enak dan kemasan rapi",
        "rasa enak, kopi aren enak dengan kemasan cantik",
    ]
    result = top_keywords(texts, exclude=["kopi aren"], n=10)
    words = dict(result)
    assert "kopi" not in words
    assert "aren" not in words
    assert "dan" not in words
    assert result[:2] == [("enak", 3), ("kemasan", 2)]


def test_keywords_tie_breaks_alphabetically_and_counts_bigrams() -> None:
    texts = ["kemasan rapi warna cerah", "warna cerah kemasan rapi"]
    assert top_keywords(texts, exclude=[], n=3) == [
        ("cerah", 2), ("kemasan", 2), ("rapi", 2)
    ]
    assert top_keywords(texts, exclude=[], n=3, ngram=2) == [
        ("kemasan rapi", 2), ("warna cerah", 2), ("cerah kemasan", 1)
    ]


def test_keywords_rejects_unsupported_ngram() -> None:
    try:
        top_keywords(["contoh teks"], exclude=[], ngram=3)
    except ValueError as exc:
        assert "ngram" in str(exc)
    else:  # pragma: no cover - memperjelas kegagalan assertion
        raise AssertionError("ngram=3 seharusnya ditolak")
