def detect_language(text: str) -> str:
    """ Very basic demo language detection (English/Arabic). """
    arabic_chars = set("ابتثجحخدذرزسشصضطظعغفقكلمنهوي")
    if any(c in arabic_chars for c in text):
        return "ar"
    return "en"