# app/i18n.py
import re
from typing import Dict, Tuple, Optional

# Try optional high-quality detector if installed
try:
    from langdetect import detect_langs
    LANGDETECT_AVAILABLE = True
except Exception:                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 
    LANGDETECT_AVAILABLE = False

# Arabic unicode ranges (includes presentation forms)
ARABIC_RE = re.compile(r'[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]')

def _heuristic_detect(text: str) -> Tuple[str, float]:
    """
    Very fast heuristic: counts Arabic vs Latin letters.
    Returns (lang, confidence) where lang is 'ar'|'en'|'unknown'.
    """
    if not text:
        return "unknown", 0.0
    ar_chars = len(ARABIC_RE.findall(text))
    latin_chars = len(re.findall(r'[A-Za-z]', text))
    total_alpha = ar_chars + latin_chars

    if ar_chars >= 2 and ar_chars >= latin_chars:
        # fairly confident Arabic
        conf = min(0.9, 0.5 + (ar_chars / max(10, len(text))))
        return "ar", conf
    if latin_chars >= 2 and latin_chars >= ar_chars:
        conf = min(0.9, 0.5 + (latin_chars / max(10, len(text))))
        return "en", conf

    # numbers / punctuation / very short -> unknown
    return "unknown", 0.0

def _langdetect_wrapper(text: str) -> Tuple[str, float]:
    """Use langdetect if available. Returns (lang, confidence)."""
    try:
        langs = detect_langs(text)
        if not langs:
            return "unknown", 0.0
        top = langs[0]
        lang = top.lang
        prob = float(top.prob)
        if lang.startswith("ar"):
            return "ar", prob
        if lang.startswith("en"):
            return "en", prob
        # other languages => unknown for our use
        return "unknown", prob
    except Exception:
        return _heuristic_detect(text)

def detect_language(text: str, client_hint: Optional[str] = None) -> Dict:
    """
    Detect language for incoming text. Returns dict:
    { 'lang': 'en'|'ar'|'unknown', 'confidence': float, 'is_rtl': bool, 'method': 'langdetect'|'heuristic'|'client_hint' }
    If client_hint is provided (e.g. frontend sent ui_lang), it is trusted with high confidence but validated.
    """
    if not text and client_hint:
        # no text but client set UI lang
        lang = client_hint if client_hint in ("en", "ar") else "unknown"
        return {"lang": lang, "confidence": 0.9, "is_rtl": lang == "ar", "method": "client_hint"}

    # honor client hint only as hint (but verify if possible)
    if client_hint and client_hint in ("en", "ar"):
        # detect and if mismatch, return both
        base = _langdetect_wrapper(text) if LANGDETECT_AVAILABLE else _heuristic_detect(text)
        detected, conf = base
        # if detection agrees with client_hint or detection is unknown -> trust client hint
        if detected == client_hint or detected == "unknown":
            return {"lang": client_hint, "confidence": max(0.8, conf), "is_rtl": client_hint == "ar", "method": "client_hint"}
        # else return detected but include client hint
        return {"lang": detected, "confidence": conf, "is_rtl": detected == "ar", "method": "auto", "client_hint": client_hint}

    # otherwise auto-detect
    if LANGDETECT_AVAILABLE:
        lang, conf = _langdetect_wrapper(text)
        method = "langdetect"
    else:
        lang, conf = _heuristic_detect(text)
        method = "heuristic"

    # low-confidence short messages -> unknown
    if conf < 0.6 or (len(text or "") < 3 and conf < 0.9):
        return {"lang": "unknown", "confidence": conf, "is_rtl": False, "method": method}

    return {"lang": lang, "confidence": conf, "is_rtl": (lang == "ar"), "method": method}

def should_set_rtl(lang: str) -> bool:
    return lang == "ar"