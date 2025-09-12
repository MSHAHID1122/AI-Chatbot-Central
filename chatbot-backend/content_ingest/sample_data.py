# content_ingest/sample_data.py
from pathlib import Path
import csv

DATA_DIR = Path("content_ingest/datasets")
CMS_DIR = DATA_DIR / "cms"
GUIDES_DIR = DATA_DIR / "guides"
SOCIAL_FILE = DATA_DIR / "social.csv"

def ensure_dirs():
    CMS_DIR.mkdir(parents=True, exist_ok=True)
    GUIDES_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

def create_markdown_samples():
    md1 = """# T-Shirt Care
We recommend machine wash cold... Tags: product:TSHIRT, tag:care, tag:faq
"""
    md2 = """# Blazer Care
Blazer cleaning guidelines... Tags: product:BLAZER, tag:care
"""
    (CMS_DIR / "tshirt-care.md").write_text(md1, encoding="utf8")
    (CMS_DIR / "blazer-care.md").write_text(md2, encoding="utf8")

def create_guides():
    g1 = "TSHIRT-usage guide: Wear and care instructions. Warranty 30 days."
    g2 = "Running shoes usage guide: break-in period, cleaning tips."
    (GUIDES_DIR / "tshirt_guide.txt").write_text(g1, encoding="utf8")
    (GUIDES_DIR / "shoes_guide.txt").write_text(g2, encoding="utf8")

def create_social_csv():
    rows = [
        {"id":"s1", "date":"2025-06-01", "text":"Check our new tshirt collection! #tshirt", "tags":"product:TSHIRT"},
        {"id":"s2", "date":"2025-06-02", "text":"Blazers on sale", "tags":"product:BLAZER"}
    ]
    with open(SOCIAL_FILE, 'w', newline='', encoding='utf8') as f:
        writer = csv.DictWriter(f, fieldnames=["id","date","text","tags"])
        writer.writeheader()
        for r in rows:
            writer.writerow(r)

if __name__ == "__main__":
    ensure_dirs()
    create_markdown_samples()
    create_guides()
    create_social_csv()
    print("Sample dataset created under content_ingest/datasets/")