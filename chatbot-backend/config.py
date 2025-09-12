"""
config.py

Central configuration loader for the project. Loads environment variables from
a .env file located next to this file and exposes typed constants for the rest
of the application to import.

Usage:
    from config import OPENAI_API_KEY, DATABASE_URL, CHROMA_PERSIST_DIR, PORT, DEBUG_MODE, ...

Notes:
 - The .env file should contain raw KEY=VALUE pairs (no Python expressions).
 - This module creates some directories (data folders) if they don't exist.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# -------------------------
# Basic helpers
# -------------------------
BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
load_dotenv(dotenv_path=str(ENV_PATH))

def _get_bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return str(v).lower() in ("1", "true", "yes", "on")

def _get_int(name: str, default: int) -> int:
    v = os.getenv(name)
    try:
        return int(v) if v is not None else default
    except ValueError:
        return default

def _get_str(name: str, default: str = "") -> str:
    v = os.getenv(name)
    return str(v) if v is not None else default

# -------------------------
# App basic settings
# -------------------------
API_KEY = _get_str("API_KEY", "dev-secret")
VERIFY_TOKEN = _get_str("WHATSAPP_VERIFY_TOKEN", "verify-me")

PORT = _get_int("PORT", 5000)
DEBUG_MODE = _get_bool("DEBUG", False)

# Logging level (optional)
LOG_LEVEL = _get_str("LOG_LEVEL", "INFO").upper()

# -------------------------
# Twilio
# -------------------------
TWILIO_ACCOUNT_SID = _get_str("TWILIO_ACCOUNT_SID", None)
TWILIO_AUTH_TOKEN = _get_str("TWILIO_AUTH_TOKEN", None)
TWILIO_WHATSAPP_FROM = _get_str("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")

# -------------------------
# OpenAI / LLM / Embeddings
# -------------------------
OPENAI_API_KEY = _get_str("OPENAI_API_KEY", None)
if not OPENAI_API_KEY:
    raise ValueError("Missing OPENAI_API_KEY in .env — set your OpenAI key or adjust config.py behavior.")

EMBEDDING_MODEL = _get_str("EMBEDDING_MODEL", "text-embedding-3-small")
BATCH_SIZE = _get_int("BATCH_SIZE", 8)
TOP_K = _get_int("TOP_K", 3)
MAX_TOKENS = _get_int("MAX_TOKENS", 512)

# -------------------------
# MySql / SQLAlchemy
# -------------------------
DATABASE_URL = _get_str("DATABASE_URL", "")
if not DATABASE_URL:
    DATABASE_URL = f"sqlite:///{str(BASE_DIR / 'data' / 'local_app.db')}"
DB_POOL_SIZE = _get_int("DB_POOL_SIZE", 10)
DB_MAX_OVERFLOW = _get_int("DB_MAX_OVERFLOW", 20)
# -------------------------
# Chroma (vector DB)
# -------------------------
DEFAULT_CHROMA_DIR = BASE_DIR / "data" / "chroma_db"
CHROMA_PERSIST_DIR = Path(_get_str("CHROMA_PERSIST_DIR", str(DEFAULT_CHROMA_DIR))).resolve()
CHROMA_COLLECTION_NAME = _get_str("CHROMA_COLLECTION_NAME", "content_hub")

# -------------------------
# Content ingest state (SQLite)
# -------------------------
DEFAULT_CONTENT_DIR = BASE_DIR / "content_ingest" / "datasets"
DATA_DIR = Path(_get_str("DATA_DIR", str(DEFAULT_CONTENT_DIR))).resolve()
STATE_DB = Path(_get_str("STATE_DB", str(BASE_DIR / "content_ingest" / "state.db"))).resolve()

# -------------------------
# Bitly URL Shortener & QR
# -------------------------
BITLY_TOKEN = _get_str("BITLY_TOKEN", None)
SHORT_BASE = _get_str("SHORT_BASE", "https://go.example.com")
MAPPING_FILE = Path(_get_str("MAPPING_FILE", str(BASE_DIR / "data" / "short_mapping.json"))).resolve()

# -------------------------
# Support tickets & local SQLite (fallback)
# -------------------------
TICKET_PROVIDER = _get_str("TICKET_PROVIDER", "zendesk").lower()

ZENDESK_SUBDOMAIN = _get_str("ZENDESK_SUBDOMAIN", "")
ZENDESK_EMAIL = _get_str("ZENDESK_EMAIL", "")
ZENDESK_API_TOKEN = _get_str("ZENDESK_API_TOKEN", "")

FRESHDESK_DOMAIN = _get_str("FRESHDESK_DOMAIN", "")
FRESHDESK_API_KEY = _get_str("FRESHDESK_API_KEY", "")

SQLITE_DB = Path(_get_str("SQLITE_DB", str(BASE_DIR / "support_tickets.db"))).resolve()

# -------------------------
# Widget / Session / Misc
# -------------------------
CHAT_WIDGET_SESSION_KEY = _get_str("CHAT_WIDGET_SESSION_KEY", "chat_widget_session")
MAX_UPLOAD_SIZE_MB = _get_int("MAX_UPLOAD_SIZE_MB", 10)

# -------------------------
# Ensure folders exist (safe to call multiple times)
# -------------------------
def _ensure_dirs():
    try:
        (BASE_DIR / "data").mkdir(parents=True, exist_ok=True)
        CHROMA_PERSIST_DIR.mkdir(parents=True, exist_ok=True)
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if STATE_DB.parent:
            STATE_DB.parent.mkdir(parents=True, exist_ok=True)
        if SQLITE_DB.parent:
            SQLITE_DB.parent.mkdir(parents=True, exist_ok=True)
        if MAPPING_FILE.parent:
            MAPPING_FILE.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

_ensure_dirs()

# -------------------------
# Exported list of important config for convenience
# -------------------------
__all__ = [
    "BASE_DIR",
    "API_KEY",
    "VERIFY_TOKEN",
    "PORT",
    "DEBUG_MODE",
    "LOG_LEVEL",
    "TWILIO_ACCOUNT_SID",
    "TWILIO_AUTH_TOKEN",
    "TWILIO_WHATSAPP_FROM",
    "OPENAI_API_KEY",
    "EMBEDDING_MODEL",
    "BATCH_SIZE",
    "TOP_K",
    "MAX_TOKENS",
    "DATABASE_URL",
    "DB_POOL_SIZE",
    "DB_MAX_OVERFLOW",
    "CHROMA_PERSIST_DIR",
    "CHROMA_COLLECTION_NAME",
    "DATA_DIR",
    "STATE_DB",
    # New QR/Bitly variables:
    "BITLY_TOKEN",
    "SHORT_BASE",
    "MAPPING_FILE",
    # Continue with existing:
    "TICKET_PROVIDER",
    "ZENDESK_SUBDOMAIN",
    "ZENDESK_EMAIL",
    "ZENDESK_API_TOKEN",
    "FRESHDESK_DOMAIN",
    "FRESHDESK_API_KEY",
    "SQLITE_DB",
    "CHAT_WIDGET_SESSION_KEY",
    "MAX_UPLOAD_SIZE_MB",
]