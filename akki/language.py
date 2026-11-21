from __future__ import annotations

HINDI_LATIN_MARKERS = frozenset(
    {
        "hai",
        "hain",
        "hoon",
        "hun",
        "kya",
        "nai",
        "nahi",
        "nahin",
        "tum",
        "tumhe",
        "tumhara",
        "tumhare",
        "tumhari",
        "tera",
        "tere",
        "teri",
        "mera",
        "mere",
        "meri",
        "mujhe",
        "tujhe",
        "aap",
        "aapko",
        "aapke",
        "aapka",
        "hum",
        "hume",
        "hamara",
        "hamare",
        "karo",
        "kar",
        "karna",
        "karne",
        "karta",
        "karti",
        "karni",
        "kiya",
        "kiye",
        "rakho",
        "rakhna",
        "chahta",
        "chahti",
        "chahiye",
        "baat",
        "baatein",
        "baad",
        "accha",
        "achha",
        "theek",
        "thik",
        "yaar",
        "bahut",
        "bohot",
        "maza",
        "mazaa",
        "dil",
        "pyaar",
        "pyar",
        "abhi",
        "phir",
        "aaj",
        "kal",
        "le",
        "lo",
        "dena",
        "bhej",
        "aana",
        "jaana",
        "chalein",
        "chalo",
        "lekin",
        "magar",
        "kyunki",
        "kaise",
        "kaisa",
        "kaisi",
        "kitna",
        "kuch",
        "sab",
        "woh",
        "yeh",
        "kyun",
        "kyu",
        "matlab",
        "ka",
        "ke",
        "ki",
        "ko",
        "se",
        "par",
        "pe",
        "liye",
        "ne",
        "batao",
        "bata",
        "suno",
        "dekho",
        "jaan",
        "jaanu",
        "haan",
        "mai",
        "mein",
        "randi",
        "gandu",
        "chut",
        "lund",
        "gaand",
        "kutiya",
    }
)


def is_devanagari(text: str) -> bool:
    return any("\u0900" <= char <= "\u097F" for char in text)


def is_latin_hindi(text: str) -> bool:
    tokens = [token.strip(".,!?;:'\"()").lower() for token in text.split()]
    tokens = [token for token in tokens if token]
    if not tokens:
        return False
    hits = sum(1 for token in tokens if token in HINDI_LATIN_MARKERS)
    if hits >= 2:
        return True
    return hits == 1 and hits / len(tokens) >= 0.15


def reply_language_hint(text: str) -> str:
    if not text.strip():
        return ""
    if is_devanagari(text) or is_latin_hindi(text):
        return "The user's current message is Hindi or Hinglish: reply in Hindi."
    return "The user's current message is English: reply in English only."
