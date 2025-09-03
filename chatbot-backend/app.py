import os
import logging
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from ai_engine import generate_reply
from crm import crm_track_event, crm_update_profile
from utils import detect_language

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

API_KEY = os.getenv("API_KEY", "dev-secret")
VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "verify-me")


def validate_api_key(req):
    return req.headers.get("x-api-key") == API_KEY


# WhatsApp webhook verification
@app.route("/webhook/whatsapp", methods=["GET"])
def verify_webhook():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode and token:
        if mode == "subscribe" and token == VERIFY_TOKEN:
            logger.info("Webhook verified successfully")
            return challenge, 200
        else:
            logger.error("Webhook verification failed")
            return jsonify({"error": "Verification failed"}), 403
    return jsonify({"error": "Missing parameters"}), 400


# Handle WhatsApp messages
@app.route("/webhook/whatsapp", methods=["POST"])
def handle_whatsapp_message():
    try:
        data = request.get_json()
        logger.info(f"Incoming WhatsApp message: {data}")

        if not data or "object" not in data:
            return jsonify({"error": "Invalid request"}), 400

        entry = data.get("entry", [{}])[0]
        changes = entry.get("changes", [{}])[0]
        value = changes.get("value", {})
        messages = value.get("messages", [])

        if not messages:
            return jsonify({"error": "No message found"}), 400

        message = messages[0]
        from_number = message.get("from")
        message_type = message.get("type")
        timestamp = message.get("timestamp")

        if message_type != "text":
            return jsonify({"error": "Only text messages supported"}), 400

        message_text = message.get("text", {}).get("body", "")

        # Check QR context
        qr_context = None
        if message_text.startswith("qr:"):
            qr_context = message_text[3:].strip()
            logger.info(f"QR context detected: {qr_context}")

        # Track in CRM
        crm_track_event(
            from_number,
            "whatsapp_message_received",
            {"message": message_text, "qr_context": qr_context, "timestamp": timestamp},
        )
        crm_update_profile(from_number, {"opt_in": True, "channel": "whatsapp"})

        # Build context
        context = {
            "channel": "whatsapp",
            "user_id": from_number,
            "message": message_text,
            "qr_context": qr_context,
            "language": detect_language(message_text),
        }

        reply = generate_reply(context)

        return (
            jsonify(
                {
                    "status": "success",
                    "reply": reply,
                    "channel": "whatsapp",
                    "user_id": from_number,
                }
            ),
            200,
        )

    except Exception as e:
        logger.exception("Error processing WhatsApp message")
        return jsonify({"error": "Internal server error"}), 500


# Handle website chat
@app.route("/api/chat", methods=["POST"])
def handle_web_chat():
    if not validate_api_key(request):
        return jsonify({"error": "Unauthorized"}), 401

    try:
        data = request.get_json()
        logger.info(f"Incoming web chat message: {data}")

        if not data or "message" not in data:
            return jsonify({"error": "Message is required"}), 400

        message_text = data.get("message")
        session_id = data.get("session_id") or "anon-session"
        user_id = data.get("user_id") or session_id

        crm_track_event(
            user_id,
            "web_message_received",
            {"message": message_text, "session_id": session_id, "channel": "web"},
        )
        crm_update_profile(user_id, {"opt_in": True, "channel": "web"})

        context = {
            "channel": "web",
            "user_id": user_id,
            "session_id": session_id,
            "message": message_text,
            "language": detect_language(message_text),
        }

        reply = generate_reply(context)

        return (
            jsonify(
                {
                    "status": "success",
                    "reply": reply,
                    "channel": "web",
                    "session_id": session_id,
                }
            ),
            200,
        )

    except Exception as e:
        logger.exception("Error processing web chat")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/healthz", methods=["GET"])
def healthz():
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    debug_mode = os.getenv("DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug_mode)