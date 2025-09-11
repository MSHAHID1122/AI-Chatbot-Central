import re
from typing import Dict, Any
from pathlib import Path

# Where prompt templates live
PROMPTS_DIR = Path("prompts")  # keep your prompt_en.txt and prompt_ar.txt here

def _load_template(name: str) -> str:
    p = PROMPTS_DIR / name
    if not p.exists():
        raise FileNotFoundError(f"Missing prompt template: {p}")
    return p.read_text(encoding="utf8")

# load once
_PROMPT_EN = _load_template("prompt_en.txt")
_PROMPT_AR = _load_template("prompt_ar.txt")

# PII redaction patterns (basic)
_EMAIL_RE = re.compile(r"([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)")
_CC_RE = re.compile(r"\b(?:\d[ -]*?){13,19}\b")  # crude card-like sequences
_PHONE_RE = re.compile(r"(?:(?:\+?\d{1,3}[-.\s]?)?(?:\(?\d{1,4}\)?[-.\s]?)?\d{3,4}[-.\s]?\d{3,4})")
_NID_RE = re.compile(r"\b\d{6,14}\b")  # generic numeric id pattern (tunable)

def redact_pii(text: str) -> str:
    """Mask common PII in a reply or a retrieved snippet before it's shown to LLM (if desired)."""
    if not text:
        return text
    t = _EMAIL_RE.sub("[REDACTED_EMAIL]", text)
    t = _CC_RE.sub("[REDACTED_CC]", t)
    # Mask phone-looking tokens but avoid masking short numbers like 'M' sizes; be conservative:
    t = _PHONE_RE.sub("[REDACTED_PHONE]", t)
    t = _NID_RE.sub("[REDACTED_ID]", t)
    return t

def build_prompt(user_message: str, retrieved_docs: str, conversation_history: str, user_profile: Dict[str, Any], product_context: Dict[str, Any], lang: str) -> str:
    """
    Build a full prompt (system + user) for the given language.
    This injects an explicit "produce reply in X only" guard at the end of system template.
    """
    # choose template base
    if lang == "ar":
        base = _PROMPT_AR
    else:
        base = _PROMPT_EN

    # enforce final guard to produce only the target language
    guard = ("\n\nNow produce the assistant reply in Arabic only." if lang == "ar" else "\n\nNow produce the assistant reply in English only.")
    system_and_user = base + guard

    # Fill placeholders expected in your prompts (keep keys consistent with your prompt files)
    filled = system_and_user.format(
        user_message=user_message,
        retrieved_docs=retrieved_docs or "",
        conversation_history=conversation_history or "",
        user_profile=user_profile or {},
        product_context=product_context or {}
    )
    # Optionally pre-redact retrieved docs (if you want LLM not to see raw PII)
    # For now we assume prompts instruct redaction, but you can also redact here:
    # filled = redact_pii(filled)
    return filled

def enforce_output_language(response_text: str, expected_lang: str) -> bool:
    """
    Quick check: returns True if response_text is in expected_lang (basic check).
    We use presence of arabic characters as proxy. For 'en' we require no >N Arabic chars.
    """
    if expected_lang == "ar":
        return bool(re.search(r'[\u0600-\u06FF\u0750-\u077F]', response_text))
    else:
        # ensure not predominantly Arabic
        ar_count = len(re.findall(r'[\u0600-\u06FF\u0750-\u077F]', response_text))
        # if contains many arabic chars it's not english; allow some tokens
        return ar_count == 0