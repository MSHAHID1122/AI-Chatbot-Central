# helpers: create_short_link, generate_qr_image, parse_prefill_text, session token
import os
import json
import uuid
import qrcode
import requests
import secrets
from urllib.parse import quote_plus, urlencode
from dotenv import load_dotenv

load_dotenv()

BITLY_TOKEN = os.getenv("BITLY_TOKEN")
SHORT_BASE = os.getenv("SHORT_BASE", "https://go.example.com")
MAPPING_FILE = os.getenv("MAPPING_FILE", "data/short_mapping.json")

def _ensure_mapping_file():
    d = os.path.dirname(MAPPING_FILE)
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)
    if not os.path.exists(MAPPING_FILE):
        json.dump({}, open(MAPPING_FILE, "w"))

def load_mapping():
    _ensure_mapping_file()
    with open(MAPPING_FILE, "r") as f:
        return json.load(f)

def save_mapping(mapping):
    _ensure_mapping_file()
    with open(MAPPING_FILE, "w") as f:
        json.dump(mapping, f, indent=2)

def create_short_link(long_url):
    """
    Create a short URL via Bitly if BITLY_TOKEN supplied,
    otherwise generate a short id and store mapping locally.
    Returns the full short URL.
    """
    if BITLY_TOKEN:
        headers = {
            "Authorization": f"Bearer {BITLY_TOKEN}",
            "Content-Type": "application/json"
        }
        data = {"long_url": long_url}
        r = requests.post("https://api-ssl.bitly.com/v4/shorten", headers=headers, json=data)
        r.raise_for_status()
        return r.json()["link"]
    # fallback: local mapping
    mapping = load_mapping()
    short_id = uuid.uuid4().hex[:8]
    short_url = f"{SHORT_BASE}/{short_id}"
    mapping[short_id] = {"long_url": long_url}
    save_mapping(mapping)
    return short_url

def generate_qr_image(url, filename="qr.png"):
    img = qrcode.make(url)
    img.save(filename)
    return filename

def make_prefill(category=None, product_id=None, utm_source="qr", utm_medium=None, session=None, extra=None):
    """
    Build the prefill text that goes into wa.me?text=...
    Example: qr:category=tshirt|product_id=TSHIRT-123|utm_source=qr|session=abc123
    """
    parts = []
    if category:
        parts.append(f"category={category}")
    if product_id:
        parts.append(f"product_id={product_id}")
    parts.append(f"utm_source={utm_source}")
    if utm_medium:
        parts.append(f"utm_medium={utm_medium}")
    if session:
        parts.append(f"session={session}")
    if extra:
        parts.append(extra)
    return "qr:" + "|".join(parts)

def parse_prefill_text(text):
    """
    Parse the prefill text sent by the user when they tap send.
    Returns dict of key->value for parts after 'qr:'.
    """
    if not text or not text.startswith("qr:"):
        return {}
    data = text[3:]
    parts = data.split("|")
    out = {}
    from urllib.parse import unquote_plus
    for p in parts:
        if "=" in p:
            k, v = p.split("=", 1)
            out[k] = unquote_plus(v)
    return out

def generate_session_token():
    # cryptographically secure short token
    return secrets.token_urlsafe(8)