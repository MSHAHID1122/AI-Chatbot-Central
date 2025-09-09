CREATE TABLE IF NOT EXISTS contacts (
  id SERIAL PRIMARY KEY,
  phone VARCHAR(32) UNIQUE NOT NULL,
  display_name VARCHAR(255),
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- opt_ins
CREATE TABLE IF NOT EXISTS opt_ins (
  id SERIAL PRIMARY KEY,
  contact_id INT REFERENCES contacts(id) ON DELETE CASCADE,
  channel VARCHAR(32) NOT NULL,
  source VARCHAR(255),
  consent BOOLEAN NOT NULL DEFAULT true,
  consent_ts TIMESTAMPTZ DEFAULT now(),
  consent_text VARCHAR(1000),
  method VARCHAR(64),
  ip_address VARCHAR(45),
  user_agent TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- messaging_events (audit)
CREATE TABLE IF NOT EXISTS messaging_events (
  id SERIAL PRIMARY KEY,
  contact_id INT REFERENCES contacts(id),
  event_type VARCHAR(64),
  payload JSONB,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- QR links
CREATE TABLE IF NOT EXISTS qr_links (
  id SERIAL PRIMARY KEY,
  short_id VARCHAR(64) UNIQUE,
  target_phone VARCHAR(32),
  prefill_text TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- QR scans
CREATE TABLE IF NOT EXISTS qr_scans (
  id SERIAL PRIMARY KEY,
  short_id VARCHAR(64) REFERENCES qr_links(short_id),
  session_token VARCHAR(64),
  ip VARCHAR(45),
  ua TEXT,
  country VARCHAR(64),
  utm_source VARCHAR(64),
  utm_medium VARCHAR(64),
  ts TIMESTAMPTZ DEFAULT now(),
  matched BOOLEAN DEFAULT FALSE
);

-- Support tickets (local)
CREATE TABLE IF NOT EXISTS tickets (
  id SERIAL PRIMARY KEY,
  external_id VARCHAR(128),
  provider VARCHAR(64),
  status VARCHAR(32),
  user_phone VARCHAR(32),
  product_tag VARCHAR(64),
  crm_id VARCHAR(128),
  channel VARCHAR(32),
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now(),
  payload JSONB
);

-- Ticket messages (local)
CREATE TABLE IF NOT EXISTS messages (
  id SERIAL PRIMARY KEY,
  ticket_id INT REFERENCES tickets(id) ON DELETE CASCADE,
  sender VARCHAR(64),
  text TEXT,
  metadata JSONB,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- content ingest processed state (if you want Postgres instead of SQLite)
CREATE TABLE IF NOT EXISTS processed_docs (
  id SERIAL PRIMARY KEY,
  doc_hash VARCHAR(128) UNIQUE,
  source VARCHAR(64),
  source_id VARCHAR(128),
  file_path TEXT,
  indexed_at TIMESTAMPTZ DEFAULT now()
);