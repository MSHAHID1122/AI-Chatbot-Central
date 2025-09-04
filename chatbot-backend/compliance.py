import time

# In-memory stores for demo (replace with DB in production)
SEEN_MESSAGES = {}
EVENT_LOG = []

def is_replay(message_id: str, ttl: int = 300) -> bool:
    """Prevent replay attacks and dedupe by MessageSid"""
    now = int(time.time())
    if message_id in SEEN_MESSAGES and now - SEEN_MESSAGES[message_id] < ttl:
        return True
    SEEN_MESSAGES[message_id] = now
    return False

def record_event(user_id: str, event_type: str, payload: dict):
    """Record inbound/outbound events for compliance audit"""
    EVENT_LOG.append({
        "user": user_id,
        "type": event_type,
        "payload": payload,
        "ts": int(time.time())
    })