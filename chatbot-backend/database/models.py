# db/models.py
"""
SQLAlchemy models for the project.

This file defines the primary relational models used across:
- contact / opt-in management
- messaging events
- QR shortlink & scan attribution
- support tickets & ticket messages (local fallback)
- processed documents state used by the ingest pipeline

Notes:
- Uses timezone-aware TIMESTAMP and server_default=func.now()
- Includes sensible indexes and foreign keys
- Relationship back_populates are provided for convenient ORM navigation
- Add more columns/constraints as your app requires (this is a complete, ready-to-create schema)
"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    Text,
    JSON,
    TIMESTAMP,
    ForeignKey,
    Index,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.sql import func

Base = declarative_base()


class Contact(Base):
    __tablename__ = "contacts"

    id = Column(Integer, primary_key=True)
    phone = Column(String(32), unique=True, nullable=False, index=True)  # E.164 preferred
    display_name = Column(String(255), nullable=True)
    email = Column(String(255), nullable=True, index=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # relationships
    opt_ins = relationship("OptIn", back_populates="contact", cascade="all, delete-orphan")
    events = relationship("MessagingEvent", back_populates="contact", cascade="all, delete-orphan")
    tickets = relationship("Ticket", back_populates="contact", cascade="all, delete-orphan")
    qr_scans = relationship("QRScan", back_populates="matched_contact", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Contact id={self.id} phone={self.phone} name={self.display_name}>"


class OptIn(Base):
    __tablename__ = "opt_ins"
    id = Column(Integer, primary_key=True)
    contact_id = Column(Integer, ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False, index=True)
    channel = Column(String(32), nullable=False)  # e.g., 'whatsapp', 'sms', 'web'
    source = Column(String(255), nullable=True)  # 'checkout', 'qr', 'support_form'
    consent = Column(Boolean, nullable=False, default=True)
    consent_ts = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    consent_text = Column(String(1000), nullable=True)
    method = Column(String(64), nullable=True)  # 'checkbox', 'button', 'sms_reply'
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

    contact = relationship("Contact", back_populates="opt_ins")

    # optionally ensure one optin per (contact, channel, source) if desired:
    __table_args__ = (
        UniqueConstraint("contact_id", "channel", "source", name="uq_optin_contact_channel_source"),
    )

    def __repr__(self) -> str:
        return f"<OptIn id={self.id} contact_id={self.contact_id} channel={self.channel} consent={self.consent}>"


class MessagingEvent(Base):
    __tablename__ = "messaging_events"
    id = Column(Integer, primary_key=True)
    contact_id = Column(Integer, ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True, index=True)
    event_type = Column(String(64), nullable=False)  # e.g., 'inbound','delivery','template_sent','qr_scanned'
    provider = Column(String(64), nullable=True)  # e.g., 'twilio','meta'
    provider_id = Column(String(255), nullable=True, index=True)  # provider-specific id (message_sid, etc)
    payload = Column(JSON, nullable=True)  # raw or normalized payload
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

    contact = relationship("Contact", back_populates="events")

    def __repr__(self) -> str:
        return f"<MessagingEvent id={self.id} type={self.event_type} contact_id={self.contact_id}>"


class QRLink(Base):
    __tablename__ = "qr_links"
    id = Column(Integer, primary_key=True)
    short_id = Column(String(128), unique=True, nullable=False, index=True)  # e.g., 'xYz12'
    target_phone = Column(String(32), nullable=False)  # E.164 or plain digits
    prefill_text = Column(Text, nullable=False)
    session_token = Column(String(128), nullable=True)  # optional session token embedded in prefill
    extra_metadata = Column(JSON, nullable=True)  # optional metadata (campaign, creator, etc.)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

    scans = relationship("QRScan", back_populates="qr_link", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<QRLink id={self.id} short_id={self.short_id} phone={self.target_phone}>"


class QRScan(Base):
    __tablename__ = "qr_scans"
    id = Column(Integer, primary_key=True)
    qr_link_id = Column(Integer, ForeignKey("qr_links.id", ondelete="CASCADE"), nullable=False, index=True)
    session_token = Column(String(128), nullable=True, index=True)
    ip = Column(String(45), nullable=True)
    ua = Column(Text, nullable=True)
    country = Column(String(64), nullable=True)
    utm_source = Column(String(128), nullable=True)
    utm_medium = Column(String(128), nullable=True)
    matched = Column(Boolean, nullable=False, default=False)  # matched to an inbound message/ticket
    matched_at = Column(TIMESTAMP(timezone=True), nullable=True)
    matched_contact_id = Column(Integer, ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

    qr_link = relationship("QRLink", back_populates="scans")
    matched_contact = relationship("Contact", back_populates="qr_scans")

    def __repr__(self) -> str:
        return f"<QRScan id={self.id} qr_link_id={self.qr_link_id} session={self.session_token} ip={self.ip}>"


class Ticket(Base):
    __tablename__ = "tickets"
    id = Column(Integer, primary_key=True)
    external_id = Column(String(255), nullable=True, index=True)  # e.g., 'zendesk:12345'
    provider = Column(String(64), nullable=False, default="local")  # 'zendesk'|'freshdesk'|'local'
    status = Column(String(32), nullable=False, default="open")  # open, claimed, escalated, closed, etc.
    contact_id = Column(Integer, ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True, index=True)
    assignee = Column(String(255), nullable=True)  # optional agent id or assignee identifier
    user_phone = Column(String(32), nullable=True)  # denormalized for quick queries
    product_tag = Column(String(128), nullable=True)
    crm_id = Column(String(255), nullable=True)  # external CRM id if known
    channel = Column(String(32), nullable=True)  # e.g., 'whatsapp', 'web'
    raw_payload = Column(JSON, nullable=True)  # raw response from provider or creation payload
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    contact = relationship("Contact", back_populates="tickets")
    messages = relationship("TicketMessage", back_populates="ticket", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Ticket id={self.id} external={self.external_id} provider={self.provider} status={self.status}>"


class TicketMessage(Base):
    __tablename__ = "ticket_messages"
    id = Column(Integer, primary_key=True)
    ticket_id = Column(Integer, ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False, index=True)
    sender = Column(String(128), nullable=False)  # 'user', 'agent:alice', 'system'
    sender_contact_id = Column(Integer, ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True, index=True)
    text = Column(Text, nullable=False)
    extra_metadata = Column(JSON, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

    ticket = relationship("Ticket", back_populates="messages")
    sender_contact = relationship("Contact", foreign_keys=[sender_contact_id])

    def __repr__(self) -> str:
        return f"<TicketMessage id={self.id} ticket_id={self.ticket_id} sender={self.sender}>"


class ProcessedDoc(Base):
    __tablename__ = "processed_docs"
    id = Column(Integer, primary_key=True)
    doc_hash = Column(String(128), unique=True, nullable=False, index=True)  # SHA-256 hex
    source = Column(String(128), nullable=True)  # 'cms','guides','social',...
    source_id = Column(String(255), nullable=True)  # e.g., filename or CMS id
    file_path = Column(Text, nullable=True)
    indexed_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    extra_metadata = Column(JSON, nullable=True)

    def __repr__(self) -> str:
        short = (self.doc_hash or "")[:8]
        return f"<ProcessedDoc id={self.id} hash={short} source={self.source}>"


# Convenience indexes (declarative)
Index("ix_contacts_phone", Contact.phone)
Index("ix_qrlinks_shortid", QRLink.short_id)
Index("ix_processed_docs_hash", ProcessedDoc.doc_hash)
Index("ix_tickets_external_id", Ticket.external_id)
Index("ix_optins_contact_channel", OptIn.contact_id, OptIn.channel)