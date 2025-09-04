from twilio.rest import Client
from config import TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_FROM
from compliance import record_event

client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

def send_whatsapp_text(to_number: str, text: str) -> str:
    """Send outbound WhatsApp message via Twilio REST API"""
    msg = client.messages.create(
        from_=TWILIO_WHATSAPP_FROM,
        to=f"whatsapp:{to_number}",
        body=text
    )
    # Audit log
    record_event(to_number, "outbound", {"sid": msg.sid, "body": text})
    return msg.sid