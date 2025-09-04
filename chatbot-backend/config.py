import os
from dotenv import load_dotenv

# Load .env file from same folder as config.py
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(BASE_DIR, ".env")
load_dotenv(dotenv_path=ENV_PATH)

# Core app configs
API_KEY = os.getenv("API_KEY", "dev-secret")
VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "verify-me")
PORT = int(os.getenv("PORT", 5000))
DEBUG_MODE = os.getenv("DEBUG", "false").lower() == "true"


# Twilio credentials
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_FROM = os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")  # Twilio Sandbox number


# OpenAI key for LangChain
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("❌ Missing OPENAI_API_KEY in .env file!")