import logging
import hashlib
import time
from flask import Flask, request, Response, jsonify
from twilio.twiml.messaging_response import MessagingResponse
from twilio.request_validator import RequestValidator
from config import TWILIO_AUTH_TOKEN
from compliance import is_replay, record_event
from crm import crm_update_profile, crm_track_event  # ← ADD THIS

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

validator = RequestValidator(TWILIO_AUTH_TOKEN)

@app.route("/twilio/whatsapp", methods=["POST"])
def twilio_whatsapp_webhook():
    # --- Signature validation ---
    signature = request.headers.get("X-Twilio-Signature", "")
    url = request.url
    params = request.form.to_dict()
    if not validator.validate(url, params, signature):
        logger.warning("Invalid Twilio signature")
        return jsonify({"error": "invalid signature"}), 401

    # --- Parse inbound params ---
    from_number = request.form.get("From")
    to_number = request.form.get("To")
    body = request.form.get("Body", "")
    num_media = int(request.form.get("NumMedia", 0))
    message_sid = request.form.get("MessageSid")

    logger.info("Inbound from %s: %s", from_number, body)

    # --- Replay / dedupe protection ---
    if is_replay(message_sid):
        return jsonify({"status": "duplicate ignored"}), 200

    # --- Record event for audit/compliance ---
    record_event(from_number, "inbound", {"body": body, "media": num_media})

    # --- CRM INTEGRATION (YOUR FRIEND'S SUGGESTION) ---
    try:
        # Update user profile in CRM (CleverTap/Braze)
        crm_update_profile(
            phone=from_number, 
            opt_in=True, 
            last_interaction="whatsapp_message"
        )
        
        # Track this event in CRM
        crm_track_event(
            phone=from_number,
            event_name="whatsapp_message_received",
            evt_props={
                "body": body,
                "media_count": num_media,
                "message_sid": message_sid,
                "direction": "inbound"
            }
        )
        logger.info(f"CRM updated for {from_number}")
    except Exception as e:
        logger.error(f"CRM update failed: {e}")
        # DON'T fail the webhook if CRM has issues!
        # WhatsApp still needs a response

    # --- Build TwiML response ---
    resp = MessagingResponse()
    if body.lower().startswith("qr:"):
        item = body.split(":", 1)[1].strip()
        resp.message(f"Thanks for scanning QR for {item}! 🎉 We'll send you more details soon.")
        
        # 🎯 ALSO track QR-specific event in CRM!
        try:
            crm_track_event(
                phone=from_number,
                event_name="qr_message_received",
                evt_props={
                    "qr_content": item,
                    "full_body": body
                }
            )
        except Exception as e:
            logger.error(f"QR CRM tracking failed: {e}")
            
    else:
        resp.message("✅ Message received. We'll follow up shortly.")

    return Response(str(resp), mimetype="application/xml")