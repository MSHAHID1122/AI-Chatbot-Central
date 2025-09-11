# content_ingest/ingest.py
import sqlite3
from pathlib import Path
from typing import List, Dict, Any
from tenacity import retry, stop_after_attempt, wait_exponential
from tqdm import tqdm
import pandas as pd
from datetime import datetime

# LangChain imports
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.embeddings import OpenAIEmbeddings
from langchain.vectorstores import Chroma
from langchain.schema import Document

# Import from your centralized config - THIS IS THE KEY CHANGE
from config import (
    OPENAI_API_KEY,
    CHROMA_PERSIST_DIR,
    CHROMA_COLLECTION_NAME,
    DATA_DIR,  # Use this instead of redefining
    BATCH_SIZE,
    EMBEDDING_MODEL,
    STATE_DB,
    BASE_DIR  # Added to help with path resolution
)

from utils import (
    markdown_to_text,
    compute_hash,
    extract_date_from_filename,
    safe_filename_to_url,
)

# REMOVE THIS LINE: load_dotenv() - config.py already loads it

# Use the DATA_DIR from config instead of redefining
# REMOVE: DATA_DIR = Path(DATA_DIR) - already done in config
CMS_DIR = DATA_DIR / "cms"
GUIDES_DIR = DATA_DIR / "guides"
SOCIAL_FILE = DATA_DIR / "social.csv"

# State DB init
def init_state_db(state_db_path=STATE_DB):
    conn = sqlite3.connect(state_db_path)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS processed (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_hash TEXT UNIQUE,
            source TEXT,
            source_id TEXT,
            file_path TEXT,
            indexed_at TEXT
        );
    """)
    conn.commit()
    conn.close()

init_state_db()

def has_been_processed(doc_hash: str) -> bool:
    conn = sqlite3.connect(STATE_DB)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM processed WHERE doc_hash = ?", (doc_hash,))
    row = cur.fetchone()
    conn.close()
    return bool(row)

def mark_processed(doc_hash: str, source: str, source_id: str, file_path: str):
    conn = sqlite3.connect(STATE_DB)
    cur = conn.cursor()
    cur.execute(
        "INSERT OR IGNORE INTO processed(doc_hash, source, source_id, file_path, indexed_at) VALUES (?, ?, ?, ?, datetime('now'))",
        (doc_hash, source, source_id, file_path)
    )
    conn.commit()
    conn.close()

# retry wrapper for embeddings
@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=2, max=60))
def create_embeddings(batch_texts: List[str], embeddings):
    return embeddings.embed_documents(batch_texts)

def load_cms_markdown() -> List[Dict[str, Any]]:
    docs = []
    if not CMS_DIR.exists():
        return docs
    for p in CMS_DIR.glob("*.md"):
        raw = p.read_text(encoding='utf8')
        text = markdown_to_text(raw)
        title = p.stem
        date = extract_date_from_filename(str(p)) or None
        tags = []
        m = [line for line in raw.splitlines() if line.lower().startswith("tags:")]
        if m:
            tags = [t.strip() for t in m[0].split(':',1)[1].split(',')]
        docs.append({
            "source":"cms",
            "source_id": p.name,
            "file_path": str(p),
            "title": title,
            "date": date,
            "text": text,
            "tags": tags,
            "url": safe_filename_to_url(p)
        })
    return docs

def load_guides() -> List[Dict[str, Any]]:
    docs = []
    if not GUIDES_DIR.exists():
        return docs
    for p in GUIDES_DIR.glob("*.*"):
        text = p.read_text(encoding='utf8')
        docs.append({
            "source":"guides",
            "source_id": p.name,
            "file_path": str(p),
            "title": p.stem,
            "date": extract_date_from_filename(str(p)),
            "text": text,
            "tags": [],
            "url": safe_filename_to_url(p)
        })
    return docs

def load_social_csv() -> List[Dict[str, Any]]:
    if not SOCIAL_FILE.exists():
        return []
    df = pd.read_csv(SOCIAL_FILE)
    docs = []
    for idx, row in df.iterrows():
        text = str(row.get("text",""))
        tags = []
        tfield = row.get("tags","")
        if pd.notna(tfield):
            tags = [t.strip() for t in str(tfield).split(',') if t.strip()]
        docs.append({
            "source":"social",
            "source_id": str(row.get("id", idx)),
            "file_path": str(SOCIAL_FILE),
            "title": text[:50],
            "date": str(row.get("date")) if 'date' in row else None,
            "text": text,
            "tags": tags,
            "url": None
        })
    return docs

def normalize_doc(raw: Dict[str, Any]) -> Dict[str, Any]:
    txt = raw.get("text", "")
    body = txt.strip()
    doc_hash = compute_hash(body)
    meta = {
        "title": raw.get("title"),
        "date": raw.get("date"),
        "tags": raw.get("tags", []),
        "product_tags": [t.split(':')[1] for t in raw.get("tags",[]) if ':' in t and t.split(':')[0].lower()=='product'],
        "source": raw.get("source"),
        "source_id": raw.get("source_id"),
        "url": raw.get("url"),
        "file_path": raw.get("file_path")
    }
    return {
        "text": body,
        "metadata": meta,
        "hash": doc_hash
    }

def chunk_document(doc_text: str) -> List[str]:
    splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=100)
    chunks = splitter.split_text(doc_text)
    return chunks

def index_documents(docs: List[Dict[str, Any]]):
    # initialize embeddings + chroma
    print("Initializing embeddings and Chroma")
    embeddings = OpenAIEmbeddings(openai_api_key=OPENAI_API_KEY)
    chroma = Chroma(
        persist_directory=str(CHROMA_PERSIST_DIR),  # Convert Path to string
        collection_name=CHROMA_COLLECTION_NAME,
        embedding_function=embeddings
    )

    texts = []
    metadatas = []
    ids = []

    for raw in tqdm(docs, desc="Processing docs"):
        nd = normalize_doc(raw)
        if has_been_processed(nd["hash"]):
            continue
        chunks = chunk_document(nd["text"])
        for i, chunk in enumerate(chunks):
            metadata = dict(nd["metadata"])
            metadata.update({
                "chunk_index": i,
                "chunk_length": len(chunk),
                "doc_hash": nd["hash"]
            })
            texts.append(chunk)
            metadatas.append(metadata)
            ids.append(f"{nd['hash']}-{i}")

            if len(texts) >= BATCH_SIZE:
                # embed + add to chroma
                _ = create_embeddings(texts, embeddings)
                chroma.add_documents([Document(page_content=t, metadata=m) for t,m in zip(texts, metadatas)])
                texts, metadatas, ids = [], [], []

        # mark processed at doc-level
        mark_processed(nd["hash"], raw.get("source","unknown"), raw.get("source_id",""), raw.get("file_path",""))

    # final flush
    if texts:
        _ = create_embeddings(texts, embeddings)
        chroma.add_documents([Document(page_content=t, metadata=m) for t,m in zip(texts, metadatas)])
    chroma.persist()
    print("Indexing complete. Persisted to", CHROMA_PERSIST_DIR)

def run_full_ingest():
    print("Loading data sources...")
    cms = load_cms_markdown()
    guides = load_guides()
    social = load_social_csv()
    all_docs = cms + guides + social
    print(f"Found {len(all_docs)} source documents")
    index_documents(all_docs)

if __name__ == "__main__":
    run_full_ingest()