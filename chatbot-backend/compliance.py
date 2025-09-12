# compliance.py
import time
from sqlalchemy.orm import Session
# Import from your NEW centralized database engine
from database.engine import SessionLocal, get_db_session
from database.models import MessageEvent, Contact
import json

REPLAY_TTL = 300  # 5 minutes

def is_replay(contact_id: int, message_content: str, ttl: int = REPLAY_TTL) -> bool:
    """
    Prevent replay attacks by checking if the same message content
    was received recently for the same contact.
    """
    db: Session = SessionLocal()
    try:
        recent = (
            db.query(MessageEvent)
            .filter(MessageEvent.contact_id == contact_id)
            .order_by(MessageEvent.created_at.desc())
            .first()
        )
        now = int(time.time())

        if recent:
            last_seen = int(recent.created_at.timestamp())
            if recent.content == message_content and (now - last_seen < ttl):
                return True
        return False
    finally:
        db.close()


def record_event(contact_id: int, direction: str, content: str):
    """
    Record inbound/outbound messages for compliance audit into MySQL.
    """
    db: Session = SessionLocal()
    try:
        event = MessageEvent(
            contact_id=contact_id,
            direction=direction,
            content=content
        )
        db.add(event)
        db.commit()
    finally:
        db.close()


# Optional: Better version using the context manager
def record_event_v2(phone_number: str, direction: str, payload: dict):
    """
    Improved version that uses the context manager and accepts phone number instead of contact_id.
    """
    with get_db_session() as db:
        # First find or create the contact
        contact = db.query(Contact).filter(Contact.phone == phone_number).first()
        if not contact:
            contact = Contact(phone=phone_number)
            db.add(contact)
            db.flush()  # Get the ID without committing
        
        # Create the message event
        event = MessageEvent(
            contact_id=contact.id,
            direction=direction,
            content=json.dumps(payload) if isinstance(payload, dict) else str(payload)
        )
        db.add(event)
        # commit happens automatically by the context manager