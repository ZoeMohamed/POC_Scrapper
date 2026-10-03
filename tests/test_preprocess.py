from app.nlp.preprocess import normalize, tokenize


def test_normalize_removes_url_mention_emoji_and_numbers() -> None:
    value = normalize("Hai @toko, cek https://contoh.id/x #Kopi2026 ☕!")
    assert value == "hai cek kopi"


def test_normalize_compacts_repeated_letters_and_expands_slang() -> None:
    value = normalize("Bagusss bgt, tp ongkir gk murah")
    assert value == "bagus banget tapi ongkos kirim tidak murah"


def test_tokenize_returns_normalized_words() -> None:
    assert tokenize("udh bgs dgn promo!!!") == ["sudah", "bagus", "dengan", "promo"]
