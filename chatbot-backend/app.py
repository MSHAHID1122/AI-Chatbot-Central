import os
import json
import datetime
import logging
from flask import Flask, request, redirect, jsonify, render_template
from urllib.parse import quote_plus
from twilio.request_validator import RequestValidator

# Import your existing modules
from ai_engine import generate_reply
import twilio_send
# REPLACE the old utils.detect_language with the new i18n version
from app.i18n import detect_language  # ← CHANGED IMPORT
from config import PORT, DEBUG_MODE, TWILIO_AUTH_TOKEN

# QR code utilities
from qr_utils import load_mapping, save_mapping, parse_prefill_text
from qr_utils import MAPPING_FILE  # from env

# Support tickets blueprint
from services.support_tickets import tickets_bp

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Data directory for storing scans
DATA_DIR = "data"
SCANS_FILE = os.path.join(DATA_DIR, "scans.json")
os.makedirs(DATA_DIR, exist_ok=True)

# Simple file helpers (demo only)
def _load_scans():
    if not os.path.exists(SCANS_FILE):
        json.dump([], open(SCANS_FILE, "w"))
    return json.load(open(SCANS_FILE))

def _save_scans(scans):
    json.dump(scans, open(SCANS_FILE, "w"), indent=2)

app = Flask(__name__)
validator = RequestValidator(TWILIO_AUTH_TOKEN)

# Register Support Tickets Blueprint
app.register_blueprint(tickets_bp)

# -----------------------
# Home Page
# -----------------------
@app.route("/")
def index():
    return render_template("index.html")

# -----------------------
# QR Code Redirect Endpoint
# -----------------------
@app.route("/<short_id>", methods=["GET"])
def redirect_short(short_id):
    mapping = load_mapping()
    entry = mapping.get(short_id)
    if not entry:
        return "Not found", 404

    # Log scan
    scans = _load_scans()
    scan_record = {
        "short_id": short_id,
        "ip": request.remote_addr,
        "ua": request.headers.get("User-Agent"),
        "ts": datetime.datetime.utcnow().isoformat(),
        "matched": False
    }
    scans.append(scan_record)
    _save_scans(scans)

    # Detect mobile user agents roughly
    ua = (request.headers.get("User-Agent") or "").lower()
    is_mobile = any(x in ua for x in ("iphone", "android", "ipad", "mobile"))

    # Build wa.me and web.whatsapp URLs
    phone = entry.get("phone")
    prefill = entry.get("prefill")
    wa_url = f"https://wa.me/{phone}?text={quote_plus(prefill)}"
    web_url = f"https://web.whatsapp.com/send?phone={phone}&text={quote_plus(prefill)}"

    # Redirect based on device
    if not is_mobile:
        return redirect(web_url, code=302)
    return redirect(wa_url, code=302)

# -----------------------
# Twilio WhatsApp Webhook
# -----------------------
@app.route("/twilio/whatsapp", methods=["POST"])
def twilio_whatsapp_webhook():
    # Verify signature
    signature = request.headers.get("X-Twilio-Signature", "")
    url = request.url
    params = request.form.to_dict()
    if not validator.validate(url, params, signature):
        return jsonify({"error": "invalid signature"}), 401

    from_number = request.form.get("From")
    body = request.form.get("Body", "")
    message_sid = request.form.get("MessageSid")

    # Parse prefill text for QR codes
    parsed = parse_prefill_text(body)
    
    # Log the incoming message
    logger.info(f"Inbound from {from_number}: {body}")

    # For tracking: try to find mapping by session token first
    session = parsed.get("session")
    product_id = parsed.get("product_id")
    category = parsed.get("category")

    mapping = load_mapping()
    matched_short = None

    # 1) match by session token (recommended)
    if session:
        for sid, entry in mapping.items():
            if entry.get("session") == session:
                matched_short = sid
                break

    # Log and mark scan matched if found
    scans = _load_scans()
    found = False
    if matched_short:
        # mark latest unmatched scan for matched_short
        for s in reversed(scans):
            if s.get("short_id") == matched_short and not s.get("matched"):
                s["matched"] = True
                s["matched_at"] = datetime.datetime.utcnow().isoformat()
                s["from_number"] = from_number
                s["parsed"] = parsed
                found = True
                break
        _save_scans(scans)

    # Also append inbound message log
    scans.append({
        "short_id": matched_short,
        "message_sid": message_sid,
        "from": from_number,
        "body": body,
        "parsed": parsed,
        "ts": datetime.datetime.utcnow().isoformat()
    })
    _save_scans(scans)

    # Build response based on message content
    if body.lower().startswith("qr:"):
        # Handle QR code messages
        item = body.split(":", 1)[1].strip()
        response_text = f"Thanks for scanning QR for {item}! 🎉 We'll send you more details soon."
    elif "help" in body.lower() or "support" in body.lower() or "problem" in body.lower():
        # Handle support requests
        try:
            from services.support_tickets import route_support_ticket
            result = route_support_ticket(
                user={
                    "phone": from_number,
                    "display_name": f"WhatsApp User {from_number}",
                    "crm_id": matched_short
                },
                message=body,
                metadata={
                    "channel": "whatsapp",
                    "product_tag": parsed.get('product_id'),
                    "category": parsed.get('category'),
                    "subject": f"WhatsApp Support: {body[:50]}..."
                }
            )
            response_text = f"✅ Support ticket #{result['ticket_id']} created! Our team will contact you shortly."
        except Exception as e:
            logger.error(f"Support ticket creation failed: {e}")
            response_text = "⚠️ We're experiencing technical difficulties. Please try again later."
    else:
        # Handle regular messages with AI engine ← UPDATED SECTION
        # Use the NEW detect_language function with proper result handling
        detection_result = detect_language(body)  # ← CHANGED
        lang = detection_result.get('lang', 'en')  # ← CHANGED
        
        context = {
            "channel": "whatsapp",
            "user_id": from_number,
            "session_id": message_sid,
            "message": body,
            "language": lang,  # ← CHANGED: Now passing the detected language string
            "conversation_history": [],
            # Add any other context your AI engine might need
            "user_profile": {},  # You might want to populate this
            "product_context": {}  # You might want to populate this
        }
        response_text = generate_reply(context)

    # Send response back to Twilio
    from twilio.twiml.messaging_response import MessagingResponse
    resp = MessagingResponse()
    resp.message(response_text)
    return str(resp), 200, {'Content-Type': 'application/xml'}

# -----------------------
# Send Outbound Message via Twilio
# -----------------------
@app.route("/twilio/send", methods=["POST"])
def send_via_twilio():
    """
    Example API:
    {
        "to": "+1234567890",
        "message": "Hello from Flask!"
    }
    """
    data = request.get_json()
    to = data.get("to")
    message = data.get("message")
    twilio_send.send_whatsapp_message(to, message)
    return jsonify({"status": "sent"}), 200

# -----------------------
# Website Chat Endpoint ← UPDATED SECTION
# -----------------------
@app.route("/api/chat", methods=["POST"])
def handle_web_chat():
    try:
        # ✅ 1. HANDLE BOTH JSON AND FORM-DATA (FOR FILE UPLOADS)
        if request.is_json:
            data = request.get_json()
        else:
            # This handles form-data requests (e.g., when a file is uploaded)
            data = request.form
            # If a file was sent, get it
            uploaded_file = request.files.get('file')

        logger.info(f"💬 Incoming web chat message: {data}")

        # ✅ 2. EXTRACT DATA THE WIDGET SENDS (session_id, message, language, intent)
        message_text = data.get("message", "")
        session_id = data.get("session_id", "anon-session")
        language = data.get("language", "en")  # Widget sends this
        intent = data.get("intent")            # Widget might send this from quick buttons

        # ✅ 3. USE THE LANGUAGE FROM THE WIDGET AS THE CLIENT HINT
        detection_result = detect_language(message_text, client_hint=language) # Use 'language' from widget
        lang = detection_result.get('lang', language) # Fallback to widget's language if detection fails

        # Build context for AI engine
        context = {
            "channel": "web",
            "user_id": session_id,  # Using session_id as user_id for simplicity with widget
            "session_id": session_id,
            "message": message_text,
            "language": lang,
            "conversation_history": [], # Widget handles history locally, so this can be empty
            "intent": intent, # Pass the intent to your AI engine
            # "user_profile": {},  # Remove or keep if your AI uses it
            # "product_context": {} # Remove or keep if your AI uses it
        }

        # ✅ 4. GENERATE THE REPLY USING YOUR AI ENGINE
        reply = generate_reply(context)

        # ✅ 5. RETURN THE SIMPLE JSON RESPONSE THE WIDGET EXPECTS
        return jsonify({
            "reply": reply,          # The widget looks for this key
            "session_id": session_id, # The widget looks for this key
            # You can keep these for debugging, the widget will ignore them
            "detected_language": lang,
            "is_rtl": detection_result.get('is_rtl', False)
        }), 200

    except Exception as e:
        logger.exception("❌ Error processing web chat")
        return jsonify({"error": "Internal server error"}), 500
# -----------------------
# Optional: Language Detection Endpoint for Frontend
# -----------------------
@app.route("/api/detect-language", methods=["POST"])
def detect_language_endpoint():
    """Endpoint for frontend to detect language in real-time."""
    try:
        data = request.get_json()
        text = data.get("text", "")
        client_hint = data.get("hint")  # Get UI language hint from frontend
        
        detection_result = detect_language(text, client_hint=client_hint)
        
        return jsonify(detection_result), 200
        
    except Exception as e:
        logger.error(f"Language detection error: {e}")
        return jsonify({"error": "Detection failed"}), 500

# -----------------------
# Health Check
# -----------------------
@app.route("/healthz", methods=["GET"])
def healthz():
    return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=DEBUG_MODE)