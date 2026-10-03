"""Normalisasi ringan untuk komentar media sosial Indonesia."""

from __future__ import annotations

import re

SLANG: dict[str, str] = {
    "gk": "tidak",
    "ga": "tidak",
    "gak": "tidak",
    "nggak": "tidak",
    "ngga": "tidak",
    "enggak": "tidak",
    "tdk": "tidak",
    "yg": "yang",
    "bgt": "banget",
    "tp": "tapi",
    "krn": "karena",
    "udh": "sudah",
    "udah": "sudah",
    "sdh": "sudah",
    "blm": "belum",
    "bgs": "bagus",
    "dgn": "dengan",
    "jg": "juga",
    "aja": "saja",
    "emg": "memang",
    "hrg": "harga",
    "ongkir": "ongkos kirim",
}

_URL_RE = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
_MENTION_RE = re.compile(r"(?<!\w)@[\w.]+", re.UNICODE)
_REPEATED_RE = re.compile(r"([^\W\d_])\1{2,}", re.IGNORECASE | re.UNICODE)
_NON_LETTER_RE = re.compile(r"[^\W\d_]+", re.UNICODE)


def normalize(text: str) -> str:
    """Bersihkan teks dan perluas slang tanpa melakukan stemming."""

    cleaned = _URL_RE.sub(" ", str(text).lower())
    cleaned = _MENTION_RE.sub(" ", cleaned).replace("#", "")
    cleaned = _REPEATED_RE.sub(r"\1", cleaned)
    words = _NON_LETTER_RE.findall(cleaned)
    return " ".join(SLANG.get(word, word) for word in words)


def tokenize(text: str) -> list[str]:
    """Kembalikan token huruf yang sudah dinormalisasi."""

    normalized = normalize(text)
    return normalized.split() if normalized else []
