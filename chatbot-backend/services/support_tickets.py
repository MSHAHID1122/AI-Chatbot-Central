# support_tickets.py
#!/usr/bin/env python3
"""
Support tickets blueprint for Flask.

Provides:
- route_support_ticket(user, message, metadata)
- REST endpoints for create / claim / messages / notes / transfer / close
- SQLite local fallback + tenacity retry for Zendesk/Freshdesk
- Agent console route to render agent_console.html
"""

import json
import logging
import sqlite3
from datetime import datetime
from typing import Optional, Dict, Any, List

import requests
from tenacity import retry, stop_after_attempt, wait_exponential
from flask import Blueprint, current_app, request, jsonify, render_template

# import centralized configuration
from config import (
    TICKET_PROVIDER,
    ZENDESK_SUBDOMAIN,
    ZENDESK_EMAIL,
    ZENDESK_API_TOKEN,
    FRESHDESK_DOMAIN,
    FRESHDESK_API_KEY,
    SQLITE_DB,
    PORT,
    DEBUG_MODE,
)

logger = logging.getLogger("support_tickets")
logger.setLevel(logging.INFO)

tickets_bp = Blueprint("tickets", __name__, template_folder="templates", static_folder="static")

# -----------------------
# Database helpers
# -----------------------
def init_db():
    with sqlite3.connect(SQLITE_DB) as conn:
        cur = conn.cursor()
        cur.execute(
            """
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            external_id TEXT,
            provider TEXT,
            status TEXT,
            user_phone TEXT,
            product_tag TEXT,
            crm_id TEXT,
            channel TEXT,
            created_at TEXT,
            updated_at TEXT,
            payload TEXT
        );
        """
        )
        cur.execute(
            """
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER,
            sender TEXT,
            text TEXT,
            metadata TEXT,
            created_at TEXT
        );
        """
        )
        conn.commit()


# Initialize DB on import (safe for dev)
init_db()


def _now_iso():
    return datetime.utcnow().isoformat()


def db_insert_ticket_local(payload: dict) -> int:
    now = _now_iso()
    with sqlite3.connect(SQLITE_DB) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO tickets (external_id, provider, status, user_phone, product_tag, crm_id, channel, created_at, updated_at, payload)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.get("external_id"),
                payload.get("provider", "local"),
                payload.get("status", "open"),
                payload.get("user_phone"),
                payload.get("product_tag"),
                payload.get("crm_id"),
                payload.get("channel"),
                now,
                now,
                json.dumps(payload),
            ),
        )
        ticket_id = cur.lastrowid
        conn.commit()
        return ticket_id


def db_append_message(ticket_id: int, sender: str, text: str, metadata: Optional[dict] = None):
    now = _now_iso()
    with sqlite3.connect(SQLITE_DB) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO messages (ticket_id, sender, text, metadata, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (ticket_id, sender, text, json.dumps(metadata or {}), now),
        )
        conn.commit()
        return cur.lastrowid


def db_get_messages(ticket_id: int, limit: int = 50) -> List[Dict[str, Any]]:
    with sqlite3.connect(SQLITE_DB) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, sender, text, metadata, created_at FROM messages
            WHERE ticket_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (ticket_id, limit),
        )
        rows = cur.fetchall()
        return [
            {"id": r[0], "sender": r[1], "text": r[2], "metadata": json.loads(r[3]), "created_at": r[4]}
            for r in rows
        ]


def db_update_ticket_status(ticket_id: int, status: str, external_id: Optional[str] = None):
    now = _now_iso()
    with sqlite3.connect(SQLITE_DB) as conn:
        cur = conn.cursor()
        if external_id:
            cur.execute("UPDATE tickets SET status=?, external_id=?, updated_at=? WHERE id=?", (status, external_id, now, ticket_id))
        else:
            cur.execute("UPDATE tickets SET status=?, updated_at=? WHERE id=?", (status, now, ticket_id))
        conn.commit()


def db_get_ticket(ticket_id: int) -> Optional[dict]:
    with sqlite3.connect(SQLITE_DB) as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, external_id, provider, status, user_phone, product_tag, crm_id, channel, created_at, updated_at, payload FROM tickets WHERE id=?", (ticket_id,))
        row = cur.fetchone()
        if not row:
            return None
        return {
            "id": row[0],
            "external_id": row[1],
            "provider": row[2],
            "status": row[3],
            "user_phone": row[4],
            "product_tag": row[5],
            "crm_id": row[6],
            "channel": row[7],
            "created_at": row[8],
            "updated_at": row[9],
            "payload": json.loads(row[10]) if row[10] else {},
        }


# -----------------------
# External provider helpers (with retry)
# -----------------------
@retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=2, max=20))
def zendesk_create_ticket(payload: dict) -> dict:
    if not (ZENDESK_SUBDOMAIN and ZENDESK_EMAIL and ZENDESK_API_TOKEN):
        raise RuntimeError("Zendesk credentials not configured")
    url = f"https://{ZENDESK_SUBDOMAIN}.zendesk.com/api/v2/tickets.json"
    auth = (f"{ZENDESK_EMAIL}/token", ZENDESK_API_TOKEN)
    headers = {"Content-Type": "application/json"}
    resp = requests.post(url, auth=auth, headers=headers, json={"ticket": payload}, timeout=10)
    if resp.status_code >= 400:
        logger.warning("Zendesk create failed: %s %s", resp.status_code, resp.text)
        resp.raise_for_status()
    return resp.json()


@retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=2, max=20))
def freshdesk_create_ticket(payload: dict) -> dict:
    if not (FRESHDESK_DOMAIN and FRESHDESK_API_KEY):
        raise RuntimeError("Freshdesk credentials not configured")
    url = f"https://{FRESHDESK_DOMAIN}/api/v2/tickets"
    headers = {"Content-Type": "application/json"}
    auth = (FRESHDESK_API_KEY, "X")
    resp = requests.post(url, auth=auth, headers=headers, json=payload, timeout=10)
    if resp.status_code >= 400:
        logger.warning("Freshdesk create failed: %s %s", resp.status_code, resp.text)
        resp.raise_for_status()
    return resp.json()


# -----------------------
# Core function: create ticket (external or fallback)
# -----------------------
def route_support_ticket(user: Dict[str, Any], message: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Create a ticket in configured provider (Zendesk/Freshdesk) with metadata,
    fallback to local DB if external fails.
    Returns: { ticket_id: local_id, external_id: str|None, provider: str, error: str|None }
    """
    metadata = metadata or {}
    product_tag = metadata.get("product_tag")
    crm_id = user.get("crm_id")
    user_phone = user.get("phone", "unknown")
    channel = metadata.get("channel", "whatsapp")
    subject = metadata.get("subject") or f"Support request from {user_phone} - {product_tag or 'general'}"

    try:
        if TICKET_PROVIDER == "zendesk":
            zd_payload = {
                "subject": subject,
                "comment": {"body": message},
                "requester": {"name": user.get("display_name") or user_phone, "phone": user_phone},
                "tags": [t for t in ([product_tag, channel] if product_tag else [channel]) if t],
                "external_id": crm_id,
            }
            logger.info("Creating Zendesk ticket...")
            resp = zendesk_create_ticket(zd_payload)
            external_id = str(resp.get("ticket", {}).get("id"))
            local_payload = {
                "external_id": f"zendesk:{external_id}",
                "provider": "zendesk",
                "status": "open",
                "user_phone": user_phone,
                "product_tag": product_tag,
                "crm_id": crm_id,
                "channel": channel,
                "raw_response": resp,
            }
            local_id = db_insert_ticket_local(local_payload)
            db_append_message(local_id, sender="user", text=message, metadata={"source": channel, **(metadata or {})})
            logger.info("Zendesk ticket created %s (local=%d)", external_id, local_id)
            return {"ticket_id": local_id, "external_id": external_id, "provider": "zendesk", "error": None}

        elif TICKET_PROVIDER == "freshdesk":
            fd_payload = {
                "subject": subject,
                "description": message,
                "email": user.get("email"),
                "phone": user_phone,
                "priority": 2,
                "status": 2,
                "tags": [t for t in ([product_tag, channel] if product_tag else [channel]) if t],
                "custom_fields": {"cf_crm_id": crm_id} if crm_id else {},
            }
            logger.info("Creating Freshdesk ticket...")
            resp = freshdesk_create_ticket(fd_payload)
            external_id = str(resp.get("id"))
            local_payload = {
                "external_id": f"freshdesk:{external_id}",
                "provider": "freshdesk",
                "status": "open",
                "user_phone": user_phone,
                "product_tag": product_tag,
                "crm_id": crm_id,
                "channel": channel,
                "raw_response": resp,
            }
            local_id = db_insert_ticket_local(local_payload)
            db_append_message(local_id, sender="user", text=message, metadata={"source": channel, **(metadata or {})})
            logger.info("Freshdesk ticket created %s (local=%d)", external_id, local_id)
            return {"ticket_id": local_id, "external_id": external_id, "provider": "freshdesk", "error": None}

        else:
            logger.warning("Unknown TICKET_PROVIDER %s, creating local ticket", TICKET_PROVIDER)
            raise RuntimeError("Unknown provider")

    except Exception as exc:
        logger.exception("External ticket creation failed. Falling back to local DB: %s", exc)
        local_payload = {
            "external_id": None,
            "provider": "local",
            "status": "open",
            "user_phone": user_phone,
            "product_tag": product_tag,
            "crm_id": crm_id,
            "channel": channel,
            "error": str(exc),
        }
        local_id = db_insert_ticket_local(local_payload)
        db_append_message(local_id, sender="user", text=message, metadata={"source": channel, "error": str(exc), **(metadata or {})})
        return {"ticket_id": local_id, "external_id": None, "provider": "local", "error": str(exc)}


# Expose the function for other modules to call
tickets_bp.route_support_ticket = route_support_ticket


# -----------------------
# REST endpoints (Blueprint)
# -----------------------
@tickets_bp.route("/tickets/create", methods=["POST"])
def api_create_ticket():
    """
    POST /tickets/create
    body: { user: {phone, crm_id, display_name, email}, message: "text", metadata: {product_tag, channel, session_id} }
    """
    payload = request.json or {}
    user = payload.get("user", {}) or {}
    message = payload.get("message", "")
    metadata = payload.get("metadata", {}) or {}
    if not message or not user.get("phone"):
        return jsonify({"error": "user.phone and message required"}), 400

    result = route_support_ticket(user, message, metadata)
    # track minimal event in logs for now (wire this to your crm tracking if needed)
    logger.info("Ticket create result: %s", result)
    return jsonify(result), 201


@tickets_bp.route("/tickets/<int:ticket_id>/claim", methods=["POST"])
def api_claim_ticket(ticket_id):
    payload = request.json or {}
    agent_id = payload.get("agent_id")
    agent_name = payload.get("agent_name")
    if not agent_id:
        return jsonify({"error": "agent_id required"}), 400

    db_update_ticket_status(ticket_id, "claimed")
    db_append_message(ticket_id, sender="system", text=f"Ticket claimed by {agent_name or agent_id}", metadata={"agent_id": agent_id})
    return jsonify({"ticket_id": ticket_id, "status": "claimed"}), 200


@tickets_bp.route("/tickets/<int:ticket_id>/messages", methods=["GET"])
def api_fetch_messages(ticket_id):
    limit = int(request.args.get("limit", 50))
    # fetch ticket meta
    ticket = db_get_ticket(ticket_id)
    if not ticket:
        return jsonify({"error": "ticket not found"}), 404

    provider = ticket.get("provider")
    external_id = ticket.get("external_id")
    messages = []

    # Try to fetch external comments (best-effort)
    try:
        if provider and external_id:
            if provider.startswith("zendesk"):
                ticket_num = external_id.split(":", 1)[1] if ":" in external_id else external_id
                api_url = f"https://{ZENDESK_SUBDOMAIN}.zendesk.com/api/v2/tickets/{ticket_num}/comments.json"
                resp = requests.get(api_url, auth=(f"{ZENDESK_EMAIL}/token", ZENDESK_API_TOKEN), timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    for c in data.get("comments", []):
                        messages.append({"sender": f"zendesk_user:{c.get('author_id')}", "text": c.get("body"), "created_at": c.get("created_at")})
            elif provider.startswith("freshdesk"):
                ticket_num = external_id.split(":", 1)[1] if ":" in external_id else external_id
                api_url = f"https://{FRESHDESK_DOMAIN}/api/v2/tickets/{ticket_num}/conversations"
                resp = requests.get(api_url, auth=(FRESHDESK_API_KEY, "X"), timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    for c in data:
                        messages.append({"sender": c.get("from"), "text": c.get("body_text") or c.get("body"), "created_at": c.get("created_at")})
    except Exception as exc:
        logger.warning("Could not fetch external comments: %s", exc)

    # Always append local messages
    local_msgs = db_get_messages(ticket_id, limit)

    # Merge external then local, dedupe by (sender,text,created_at)
    seen = set()
    merged = []
    for m in messages + local_msgs:
        key = (m.get("sender"), m.get("text"), m.get("created_at"))
        if key in seen:
            continue
        seen.add(key)
        merged.append(m)

    return jsonify({"messages": merged}), 200


@tickets_bp.route("/tickets/<int:ticket_id>/notes", methods=["POST"])
def api_append_note(ticket_id):
    data = request.json or {}
    agent_id = data.get("agent_id")
    note = data.get("note")
    if not note or not agent_id:
        return jsonify({"error": "agent_id and note required"}), 400

    db_append_message(ticket_id, sender=f"agent:{agent_id}", text=note, metadata={"internal": True})

    # attempt to append to external provider as internal note (best-effort)
    ticket = db_get_ticket(ticket_id)
    if not ticket:
        return jsonify({"error": "ticket not found"}), 404

    external_id = ticket.get("external_id")
    provider = ticket.get("provider")
    try:
        if provider and external_id:
            if provider.startswith("zendesk"):
                ticket_num = external_id.split(":", 1)[1]
                api_url = f"https://{ZENDESK_SUBDOMAIN}.zendesk.com/api/v2/tickets/{ticket_num}.json"
                comment = {"ticket": {"comment": {"body": note, "public": False}}}
                resp = requests.put(api_url, auth=(f"{ZENDESK_EMAIL}/token", ZENDESK_API_TOKEN), json=comment, timeout=10)
                resp.raise_for_status()
            elif provider.startswith("freshdesk"):
                ticket_num = external_id.split(":", 1)[1]
                api_url = f"https://{FRESHDESK_DOMAIN}/api/v2/tickets/{ticket_num}/notes"
                resp = requests.post(api_url, auth=(FRESHDESK_API_KEY, "X"), json={"body": note, "private": True}, timeout=10)
                resp.raise_for_status()
    except Exception as exc:
        logger.warning("Failed to append external note: %s", exc)

    return jsonify({"ticket_id": ticket_id, "status": "note_appended"}), 200


@tickets_bp.route("/tickets/<int:ticket_id>/transfer", methods=["POST"])
def api_transfer(ticket_id):
    data = request.json or {}
    agent_id = data.get("agent_id")
    target_team = data.get("target_team")
    reason = data.get("reason")
    if not agent_id:
        return jsonify({"error": "agent_id required"}), 400

    db_append_message(ticket_id, sender="system", text=f"Transfer requested by {agent_id} to {target_team or 'team'}: {reason}", metadata={"transfer": True})
    db_update_ticket_status(ticket_id, "escalated")

    ticket = db_get_ticket(ticket_id)
    if not ticket:
        return jsonify({"error": "ticket not found"}), 404

    external_id = ticket.get("external_id")
    provider = ticket.get("provider")

    try:
        if provider and external_id:
            if provider.startswith("zendesk"):
                ticket_num = external_id.split(":", 1)[1]
                api_url = f"https://{ZENDESK_SUBDOMAIN}.zendesk.com/api/v2/tickets/{ticket_num}.json"
                update = {"ticket": {"status": "open", "comment": {"body": f"Transferred to {target_team} by {agent_id}", "public": False}}}
                resp = requests.put(api_url, auth=(f"{ZENDESK_EMAIL}/token", ZENDESK_API_TOKEN), json=update, timeout=10)
                resp.raise_for_status()
            elif provider.startswith("freshdesk"):
                ticket_num = external_id.split(":", 1)[1]
                api_url = f"https://{FRESHDESK_DOMAIN}/api/v2/tickets/{ticket_num}"
                data = {"status": 2}  # example
                resp = requests.put(api_url, auth=(FRESHDESK_API_KEY, "X"), json=data, timeout=10)
                resp.raise_for_status()
    except Exception as exc:
        logger.warning("Transfer external API failed: %s", exc)

    return jsonify({"ticket_id": ticket_id, "status": "escalated"}), 200


@tickets_bp.route("/tickets/<int:ticket_id>/close", methods=["POST"])
def api_close_ticket(ticket_id):
    db_update_ticket_status(ticket_id, "closed")
    db_append_message(ticket_id, sender="system", text="Ticket closed", metadata={})

    ticket = db_get_ticket(ticket_id)
    if not ticket:
        return jsonify({"error": "ticket not found"}), 404

    external_id = ticket.get("external_id")
    provider = ticket.get("provider")

    try:
        if provider and external_id:
            if provider.startswith("zendesk"):
                ticket_num = external_id.split(":", 1)[1]
                api_url = f"https://{ZENDESK_SUBDOMAIN}.zendesk.com/api/v2/tickets/{ticket_num}.json"
                update = {"ticket": {"status": "closed"}}
                resp = requests.put(api_url, auth=(f"{ZENDESK_EMAIL}/token", ZENDESK_API_TOKEN), json=update, timeout=10)
                resp.raise_for_status()
            elif provider.startswith("freshdesk"):
                ticket_num = external_id.split(":", 1)[1]
                api_url = f"https://{FRESHDESK_DOMAIN}/api/v2/tickets/{ticket_num}"
                data = {"status": 5}  # example
                resp = requests.put(api_url, auth=(FRESHDESK_API_KEY, "X"), json=data, timeout=10)
                resp.raise_for_status()
    except Exception as exc:
        logger.warning("External close failed: %s", exc)

    return jsonify({"ticket_id": ticket_id, "status": "closed"}), 200


# -----------------------
# Agent console route (serve template)
# -----------------------
@tickets_bp.route("/agent-console", methods=["GET"])
def agent_console():
    # NOTE: protect this route in production (auth / IP whitelist).
    return render_template("agent_console.html")


# If run standalone, start Flask app for convenience
if __name__ == "__main__":
    from flask import Flask

    app = Flask(__name__)
    app.register_blueprint(tickets_bp)
    logger.info("Starting Support Tickets service on port %d (provider=%s)", PORT, TICKET_PROVIDER)
    app.run(host="0.0.0.0", port=PORT, debug=DEBUG_MODE)