# app.py
import os
import datetime
import logging
from urllib.parse import quote_plus
import twilio_send
from flask import (
    Flask,
    request,
    redirect,
    jsonify,
    render_template,
    Response,
)
from twilio.request_validator import RequestValidator
from twilio.twiml.messaging_response import MessagingResponse

# local modules - adjust import paths to match your project layout if needed
from config import PORT, DEBUG_MODE, TWILIO_AUTH_TOKEN
from ai_engine import generate_reply
from app.i18n import detect_language   # your language detection helper
from qr_utils import parse_prefill_text  # keep load_mapping/save_mapping only if still used
from services.support_tickets import tickets_bp, route_support_ticket

# Database session + models
from database.engine import get_db_session, engine
from database.models import (
    Base,
    Contact,
    MessagingEvent,
    QRLink,
    QRScan,
    Ticket,
    TicketMessage,
)

# ------------ Logging ------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app")

# ------------ Flask app ------------
app = Flask(__name__)

# Register blueprints (support tickets)
app.register_blueprint(tickets_bp)

# Twilio request validator (optional; only if env var present)
validator = None
if TWILIO_AUTH_TOKEN:
    try:
        validator = RequestValidator(TWILIO_AUTH_TOKEN)
    except Exception as e:
        logger.warning("Failed to initialize Twilio RequestValidator: %s", e)
        validator = None
else:
    logger.info("TWILIO_AUTH_TOKEN not provided: Twilio signature validation disabled (dev mode).")

# Ensure DB tables exist (create if missing)
try:
    Base.metadata.create_all(bind=engine)
    logger.info("Ensured DB tables are created.")
except Exception as e:
    logger.exception("Failed to create DB tables (you may need to run migrations separately): %s", e)


# -----------------------
# Helpers
# -----------------------
def _make_twiml_message(text: str) -> Response:
    resp = MessagingResponse()
    resp.message(text)
    return Response(str(resp), mimetype="application/xml")


# -----------------------
# Home / index
# -----------------------
@app.route("/")
def index():
    return render_template("index.html")


# -----------------------
# QR redirect endpoint
# Example: https://yourdomain.com/<short_id>
# -----------------------
@app.route("/<short_id>", methods=["GET"])
def redirect_short(short_id):
    """
    Redirect users to wa.me or web.whatsapp depending on UA, log a QRScan row.
    """
    ua = (request.headers.get("User-Agent") or "").lower()
    is_mobile = any(x in ua for x in ("iphone", "android", "ipad", "mobile"))

    with get_db_session() as db:
        qr = db.query(QRLink).filter(QRLink.short_id == short_id).first()
        if not qr:
            logger.info("QR short_id not found: %s", short_id)
            return "Not found", 404

        # Log scan
        scan = QRScan(
            qr_link_id=qr.id,
            session_token=None,
            ip=request.remote_addr,
            ua=request.headers.get("User-Agent"),
            country=None,
            utm_source=request.args.get("utm_source"),
            utm_medium=request.args.get("utm_medium"),
            matched=False,
            created_at=datetime.datetime.utcnow(),
        )
        db.add(scan)
        db.commit()

        phone = qr.target_phone
        prefill = qr.prefill_text or ""
        wa_url = f"https://wa.me/{phone}?text={quote_plus(prefill)}"
        web_url = f"https://web.whatsapp.com/send?phone={phone}&text={quote_plus(prefill)}"

        logger.info("QR redirect short=%s phone=%s mobile=%s", short_id, phone, is_mobile)
        return redirect(wa_url if is_mobile else web_url, code=302)


# -----------------------
# Twilio WhatsApp webhook
# -----------------------
@app.route("/twilio/whatsapp", methods=["POST"])
def twilio_whatsapp_webhook():
    # Signature validation (if configured)
    if validator:
        signature = request.headers.get("X-Twilio-Signature", "")
        url = request.url
        params = request.form.to_dict()
        if not validator.validate(url, params, signature):
            logger.warning("Invalid Twilio signature for URL=%s", url)
            return jsonify({"error": "invalid signature"}), 401

    from_number = request.form.get("From")
    body = request.form.get("Body", "") or ""
    message_sid = request.form.get("MessageSid")

    parsed = parse_prefill_text(body)

    logger.info("Inbound Twilio message from=%s sid=%s body=%s", from_number, message_sid, (body or "")[:200])

    matched_short = None
    # Persist contact + message event + try to match QR scan
    with get_db_session() as db:
        # find or create contact
        contact = None
        if from_number:
            contact = db.query(Contact).filter(Contact.phone == from_number).first()
        if not contact:
            contact = Contact(phone=from_number, display_name=f"WhatsApp {from_number}")
            db.add(contact)
            db.commit()
            db.refresh(contact)

        # attempt to link by session token (if present in parsed)
        session_token = parsed.get("session")
        if session_token:
            qr = db.query(QRLink).filter(QRLink.session_token == session_token).first()
            if qr:
                matched_short = qr.short_id
                # mark latest unmatched scan for this qr
                scan = (
                    db.query(QRScan)
                    .filter(QRScan.qr_link_id == qr.id, QRScan.matched == False)
                    .order_by(QRScan.created_at.desc())
                    .first()
                )
                if scan:
                    scan.matched = True
                    scan.matched_at = datetime.datetime.utcnow()
                    scan.matched_contact_id = contact.id
                    db.add(scan)

        # record messaging event
        evt = MessagingEvent(
            contact_id=contact.id,
            event_type="inbound",
            payload={
                "body": body,
                "parsed": parsed,
                "short_id": matched_short,
                "message_sid": message_sid,
            },
            created_at=datetime.datetime.utcnow(),
        )
        db.add(evt)
        db.commit()

    # Build response using logic: qr:, support flow, or AI
    try:
        if body.strip().lower().startswith("qr:"):
            item = body.split(":", 1)[1].strip()
            reply_text = f"Thanks for scanning QR for {item}! 🎉 We'll send you more details soon."
        elif any(tok in body.lower() for tok in ("help", "support", "problem", "issue")):
            # create support ticket
            # route_support_ticket returns dict with ticket_id, external_id, provider
            try:
                ticket_res = route_support_ticket(
                    user={
                        "phone": from_number,
                        "display_name": f"WhatsApp User {from_number}",
                        "crm_id": matched_short,
                    },
                    message=body,
                    metadata={"channel": "whatsapp", "product_tag": parsed.get("product_id"), "subject": f"WhatsApp Support: {body[:50]}"},
                )
                reply_text = f"✅ Support ticket #{ticket_res.get('ticket_id')} created! Our team will contact you shortly."
            except Exception as e:
                logger.exception("Support ticket creation failed")
                reply_text = "⚠️ We're experiencing technical difficulties creating a support ticket. Please try again later."
        else:
            # Conversational AI flow
            detect_result = detect_language(body)
            lang = detect_result.get("lang", "en")
            context = {
                "channel": "whatsapp",
                "user_id": from_number,
                "session_id": message_sid,
                "message": body,
                "language": lang,
                "conversation_history": [],
                "user_profile": {"phone": from_number},
                "product_context": {"product_id": parsed.get("product_id")},
            }
            reply_text = generate_reply(context)

        # return TwiML
        return _make_twiml_response(reply_text)
    except Exception as exc:
        logger.exception("Error handling Twilio webhook: %s", exc)
        return _make_twiml_response("⚠️ Internal error processing your message. Please try again later."), 500


def _make_twiml_response(text: str) -> Response:
    resp = MessagingResponse()
    resp.message(text)
    return Response(str(resp), mimetype="application/xml")


# -----------------------
# Send outbound via Twilio (and log)
# -----------------------
@app.route("/twilio/send", methods=["POST"])
def send_via_twilio():
    data = request.get_json() or {}
    to = data.get("to")
    message = data.get("message")
    if not to or not message:
        return jsonify({"error": "to and message required"}), 400

    # log outbound message and ensure contact exists
    with get_db_session() as db:
        contact = db.query(Contact).filter(Contact.phone == to).first()
        if not contact:
            contact = Contact(phone=to, display_name=f"User {to}")
            db.add(contact)
            db.commit()
            db.refresh(contact)

        evt = MessagingEvent(
            contact_id=contact.id,
            event_type="outbound",
            payload={"body": message, "status": "queued"},
            created_at=datetime.datetime.utcnow(),
        )
        db.add(evt)
        db.commit()

    # send using your wrapper (twilio_send should raise on error)
    try:
        twilio_send.send_whatsapp_message(to, message)
    except Exception:
        logger.exception("Failed to send via Twilio")
        # update event payload if desired (left as an exercise)
        return jsonify({"error": "failed to send"}), 500

    return jsonify({"status": "sent"}), 200


# -----------------------
# Website Chat Endpoint (/api/chat)
# Accepts JSON and multipart/form-data (for files)
# -----------------------
@app.route("/api/chat", methods=["POST"])
def handle_web_chat():
    try:
        uploaded_file = None
        if request.is_json:
            data = request.get_json()
        else:
            data = request.form.to_dict()
            uploaded_file = request.files.get("file")  # may be None

        message_text = (data.get("message") or "").strip()
        session_id = data.get("session_id") or f"anon-{datetime.datetime.utcnow().timestamp()}"
        widget_lang = data.get("language") or None
        intent = data.get("intent")

        # detection (use widget hint as client_hint)
        detection_result = detect_language(message_text, client_hint=widget_lang)
        lang = detection_result.get("lang", widget_lang or "en")

        context = {
            "channel": "web",
            "user_id": session_id,
            "session_id": session_id,
            "message": message_text,
            "language": lang,
            "conversation_history": [],
            "intent": intent,
            "user_profile": data.get("user_profile", {}),
            "product_context": data.get("product_context", {}),
        }

        reply = generate_reply(context)

        # Log message (store session id as contact_id if no mapping; optionally create contact rows)
        with get_db_session() as db:
            # Optionally create/associate a Contact for the session (not always desired)
            # For this example, we do not create a contact for every anonymous web session.
            evt = MessagingEvent(
                contact_id=None,
                event_type="web_chat",
                payload={
                    "session_id": session_id,
                    "body": message_text,
                    "reply": reply,
                    "language": lang,
                    "intent": intent,
                },
                created_at=datetime.datetime.utcnow(),
            )
            db.add(evt)
            db.commit()

        return jsonify({"reply": reply, "session_id": session_id, "detected_language": lang, "is_rtl": detection_result.get("is_rtl", False)}), 200

    except Exception as e:
        logger.exception("Error processing web chat: %s", e)
        return jsonify({"error": "Internal server error"}), 500


# -----------------------
# Language detection for frontend
# -----------------------
@app.route("/api/detect-language", methods=["POST"])
def detect_language_endpoint():
    try:
        payload = request.get_json() or {}
        text = payload.get("text", "")
        client_hint = payload.get("hint")
        result = detect_language(text, client_hint=client_hint)
        return jsonify(result), 200
    except Exception as e:
        logger.exception("Language detection failed: %s", e)
        return jsonify({"error": "detection failed"}), 500


# -----------------------
# Health check (DB + app)
# -----------------------
@app.route("/healthz", methods=["GET"])
def healthz():
    try:
        with get_db_session() as db:
            # simple test query
            db.execute("SELECT 1")
        return jsonify({"status": "ok", "database": "connected"}), 200
    except Exception as e:
        logger.exception("Healthcheck DB failed: %s", e)
        return jsonify({"status": "error", "database": "disconnected", "error": str(e)}), 500


# -----------------------
# Run
# -----------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=DEBUG_MODE)