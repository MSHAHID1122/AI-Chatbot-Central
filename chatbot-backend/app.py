import logging
from flask import Flask, render_template, jsonify

# AI Engine (RAG + LLM)
from ai_engine import generate_reply

# Twilio integrations
import twilio_webhook
import twilio_send

# CRM + Utils
from crm import crm_track_event, crm_update_profile
from utils import detect_language
from config import PORT, DEBUG_MODE

app = Flask(__name__)

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# -----------------------
# Home Page
# -----------------------
@app.route("/")
def index():
    return render_template("index.html")

# -----------------------
# Twilio WhatsApp Routes
# -----------------------
app.add_url_rule(
    "/twilio/whatsapp",
    view_func=twilio_webhook.twilio_whatsapp_webhook,
    methods=["POST"]
)

# Example endpoint to send outbound via Twilio
@app.route("/twilio/send", methods=["POST"])
def send_via_twilio():
    """
    Example API:
    {
        "to": "+1234567890",
        "message": "Hello from Flask!"
    }
    """
    from flask import request
    data = request.get_json()
    to = data.get("to")
    message = data.get("message")
    twilio_send.send_whatsapp_message(to, message)
    return jsonify({"status": "sent"}), 200

# -----------------------
# Website Chat Endpoint
# -----------------------
@app.route("/api/chat", methods=["POST"])
def handle_web_chat():
    from flask import request
    try:
        data = request.get_json()
        logger.info(f"💬 Incoming web chat message: {data}")

        if not data or "message" not in data:
            return jsonify({"error": "Message is required"}), 400

        message_text = data.get("message")
        session_id = data.get("session_id") or "anon-session"
        user_id = data.get("user_id") or session_id
        conversation_history = data.get("history", [])

        language = detect_language(message_text)

        # CRM tracking
        crm_track_event(
            user_id,
            "web_message_received",
            {"message": message_text, "session_id": session_id, "channel": "web"},
        )
        crm_update_profile(user_id, {"opt_in": True, "channel": "web"})

        # Build context for AI engine
        context = {
            "channel": "web",
            "user_id": user_id,
            "session_id": session_id,
            "message": message_text,
            "language": language,
            "conversation_history": conversation_history,
        }

        reply = generate_reply(context)

        return jsonify({
            "status": "success",
            "reply": reply,
            "channel": "web",
            "session_id": session_id
        }), 200

    except Exception as e:
        logger.exception("❌ Error processing web chat")
        return jsonify({"error": "Internal server error"}), 500

# -----------------------
# Health Check
# -----------------------
@app.route("/healthz", methods=["GET"])
def healthz():
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=DEBUG_MODE)