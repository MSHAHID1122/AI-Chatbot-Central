# db/models.py
"""
SQLAlchemy models for the project.

This file defines the relational models:
- contact / opt-in management
- messaging events
- QR shortlink & scan attribution
- support tickets & ticket messages
- processed documents state used by the ingest pipeline

Notes:
- Uses timezone-aware TIMESTAMP and server_default=func.now()
- Includes sensible indexes and foreign keys
- Relationship back_populates for ORM navigation
"""

from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    Text,
    ForeignKey,
    TIMESTAMP,
    func,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

# -------------------------
# Contact / opt-in
# -------------------------
class Contact(Base):
    __tablename__ = "contacts"

    id = Column(Integer, primary_key=True)
    phone_number = Column(String(32), unique=True, index=True, nullable=False)
    opted_in = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    messages = relationship("MessageEvent", back_populates="contact")


# -------------------------
# Messaging events
# -------------------------
class MessageEvent(Base):
    __tablename__ = "message_events"

    id = Column(Integer, primary_key=True)
    contact_id = Column(Integer, ForeignKey("contacts.id"))
    direction = Column(String(16))  # inbound/outbound
    content = Column(Text)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    contact = relationship("Contact", back_populates="messages")


# -------------------------
# QR shortlink & scan attribution
# -------------------------
class QRLink(Base):
    __tablename__ = "qr_links"

    id = Column(Integer, primary_key=True)
    short_code = Column(String(32), unique=True, index=True, nullable=False)
    target_url = Column(Text, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())


# -------------------------
# Support tickets
# -------------------------
class Ticket(Base):
    __tablename__ = "tickets"

    id = Column(Integer, primary_key=True)
    external_id = Column(String(255), unique=True)  # ❌ removed duplicate index
    subject = Column(String(255))
    status = Column(String(50), default="open")
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    messages = relationship("TicketMessage", back_populates="ticket")


class TicketMessage(Base):
    __tablename__ = "ticket_messages"

    id = Column(Integer, primary_key=True)
    ticket_id = Column(Integer, ForeignKey("tickets.id"))
    sender = Column(String(50))  # "user" / "agent"
    body = Column(Text)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    ticket = relationship("Ticket", back_populates="messages")


# -------------------------
# Processed documents state
# -------------------------
class ProcessedDocument(Base):
    __tablename__ = "processed_documents"

    id = Column(Integer, primary_key=True)
    file_name = Column(String(255), unique=True)
    status = Column(String(50), default="pending")
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())