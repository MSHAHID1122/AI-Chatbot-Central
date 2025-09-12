# app/qr_utils.py
import uuid
import qrcode
import requests
import secrets
from sqlalchemy.orm import Session

# Import from centralized config
from config import BITLY_TOKEN, SHORT_BASE
from db import SessionLocal
from db.models import QRLink


def create_short_link(long_url: str) -> str:
    """
    Create a short URL via Bitly if BITLY_TOKEN supplied,
    otherwise generate and store mapping in the qr_links table.
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

    # fallback: save in DB
    db: Session = SessionLocal()
    try:
        short_id = uuid.uuid4().hex[:8]
        short_url = f"{SHORT_BASE}/{short_id}"

        qr_link = QRLink(short_code=short_id, target_url=long_url)
        db.add(qr_link)
        db.commit()

        return short_url
    finally:
        db.close()


def get_long_url(short_code: str) -> str | None:
    """
    Look up the original long URL from a short_code in DB.
    """
    db: Session = SessionLocal()
    try:
        qr_link = db.query(QRLink).filter_by(short_code=short_code).first()
        return qr_link.target_url if qr_link else None
    finally:
        db.close()


def generate_qr_image(url: str, filename: str = "qr.png") -> str:
    img = qrcode.make(url)
    img.save(filename)
    return filename


def make_prefill(category=None, product_id=None, utm_source="qr",
                 utm_medium=None, session=None, extra=None) -> str:
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


def parse_prefill_text(text: str) -> dict:
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


def generate_session_token() -> str:
    # cryptographically secure short token
    return secrets.token_urlsafe(8)