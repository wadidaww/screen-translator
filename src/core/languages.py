"""Language metadata shared by OCR, translation and the settings UI."""

from __future__ import annotations

import re
from collections import Counter
from typing import Dict, List, Optional

try:
    from langdetect import DetectorFactory
    from langdetect import detect as _langdetect_detect

    DetectorFactory.seed = 0  # deterministic results
except ImportError:  # pragma: no cover - optional dependency
    _langdetect_detect = None

# code -> (display name, tesseract traineddata name)
LANGUAGES: Dict[str, tuple[str, str]] = {
    "en": ("English", "eng"),
    "id": ("Indonesian", "ind"),
    "ms": ("Malay", "msa"),
    "es": ("Spanish", "spa"),
    "pt": ("Portuguese", "por"),
    "fr": ("French", "fra"),
    "de": ("German", "deu"),
    "it": ("Italian", "ita"),
    "nl": ("Dutch", "nld"),
    "ru": ("Russian", "rus"),
    "uk": ("Ukrainian", "ukr"),
    "pl": ("Polish", "pol"),
    "tr": ("Turkish", "tur"),
    "ar": ("Arabic", "ara"),
    "hi": ("Hindi", "hin"),
    "th": ("Thai", "tha"),
    "vi": ("Vietnamese", "vie"),
    "ja": ("Japanese", "jpn"),
    "ko": ("Korean", "kor"),
    "zh": ("Chinese (Simplified)", "chi_sim"),
    "zt": ("Chinese (Traditional)", "chi_tra"),
}

# Languages written without spaces between words.
NO_SPACE_LANGS = {"ja", "zh", "zt", "th"}

_SCRIPT_PATTERNS = [
    ("ja", re.compile(r"[぀-ヿ]")),  # hiragana / katakana
    ("ko", re.compile(r"[가-힯ᄀ-ᇿ]")),
    ("zh", re.compile(r"[一-鿿]")),
    ("ru", re.compile(r"[Ѐ-ӿ]")),
    ("ar", re.compile(r"[؀-ۿ]")),
    ("hi", re.compile(r"[ऀ-ॿ]")),
    ("th", re.compile(r"[฀-๿]")),
]


def language_name(code: str) -> str:
    if code == "auto":
        return "Auto detect"
    return LANGUAGES.get(code, (code, ""))[0]


def source_language_codes() -> List[str]:
    return ["auto", *LANGUAGES.keys()]


def target_language_codes() -> List[str]:
    return list(LANGUAGES.keys())


def tesseract_languages(source_lang: str, installed: Optional[List[str]] = None) -> str:
    """Return the tesseract ``-l`` argument for a source language.

    English is always added so mixed UI text (menus, buttons) is still read.
    Languages that are not installed are dropped when ``installed`` is given.
    """
    wanted = ["eng"]
    if source_lang != "auto" and source_lang in LANGUAGES:
        code = LANGUAGES[source_lang][1]
        if code != "eng":
            wanted.insert(0, code)
    if installed is not None:
        available = [lang for lang in wanted if lang in installed]
        wanted = available or [lang for lang in installed if lang != "osd"][:1] or ["eng"]
    return "+".join(wanted)


def _script_guess(text: str) -> Optional[str]:
    counts: Counter = Counter()
    for code, pattern in _SCRIPT_PATTERNS:
        found = len(pattern.findall(text))
        if found:
            counts[code] = found
    if not counts:
        return None
    # Japanese text mixes kana with kanji; any kana means Japanese.
    if counts.get("ja"):
        return "ja"
    return counts.most_common(1)[0][0]


def normalize_code(code: str) -> str:
    code = code.lower()
    if code.startswith("zh"):
        return "zt" if code in {"zh-tw", "zh-hk", "zh-hant"} else "zh"
    if code == "in":
        return "id"
    return code.split("-")[0]


def detect_language(text: str, fallback: str = "en") -> str:
    """Best-effort language detection that never raises."""
    guess = _script_guess(text)
    if guess:
        return guess
    if _langdetect_detect is not None and len(text.strip()) >= 3:
        try:
            return normalize_code(_langdetect_detect(text))
        except Exception:
            pass
    return fallback
