import re
import hashlib
import os
import datetime
from bs4 import BeautifulSoup
from markdown import markdown
from urllib.parse import urlparse

def clean_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator="\n")
    return normalize_whitespace(text)

def markdown_to_text(md: str) -> str:
    html = markdown(md)
    return clean_html(html)

def normalize_whitespace(text: str) -> str:
    return re.sub(r'\s+', ' ', text).strip()

def canonical_title(title: str) -> str:
    return re.sub(r'[^a-z0-9\-]', '-', title.lower()).strip('-')

def compute_hash(text: str) -> str:
    h = hashlib.sha256()
    if isinstance(text, str):
        text = text.encode('utf-8')
    h.update(text)
    return h.hexdigest()

def extract_date_from_filename(filename: str):
    base = os.path.basename(filename)
    m = re.search(r'(20\d{2}[-_]?(\d{2})[-_]?(\d{2}))', base)
    if m:
        try:
            s = m.group(1).replace('_','-')
            return datetime.datetime.fromisoformat(s).isoformat()
        except Exception:
            pass
    return None

def safe_filename_to_url(filename: str, base_url: str = None):
    name = os.path.basename(filename)
    if base_url:
        return base_url.rstrip('/') + '/' + name
    return "file://" + os.path.abspath(filename)