"""
extract_resume_content.py
-------------------------
Scans all PDF resumes in this folder, extracts text, detects keywords,
and writes a CSV for manual review in Excel/Numbers.

INSTALL (one-time):
    pip install pdfplumber

RUN:
    python extract_resume_content.py

OUTPUT:
    resume_content_preview.csv  (in the same folder as this script)
"""

import csv
import re
from pathlib import Path

try:
    import pdfplumber
except ImportError:
    raise SystemExit(
        "\n[ERROR] pdfplumber is not installed.\n"
        "Run:  pip install pdfplumber\n"
    )

# ---------------------------------------------------------------------------
# Configuration — edit these as needed
# ---------------------------------------------------------------------------

RESUME_FOLDER      = Path(__file__).parent     # same folder as this script
OUTPUT_FILE        = RESUME_FOLDER / "resume_content_preview.csv"
TEXT_PREVIEW_CHARS = 400                       # how many chars to show in preview
NUM_KEYWORD_COLS   = 5                         # number of separate Keyword columns

KEYWORDS = [
    "Python", "SQL", "R", "Excel", "Tableau", "Power BI",
    "Machine Learning", "Data Analysis", "Statistics", "Modeling",
    "Forecasting", "Visualization",
    "Finance", "Accounting", "Economics",
    "Research", "Marketing", "Operations", "Management",
    "Leadership", "Communication",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def extract_text(pdf_path: Path) -> str:
    """Return all text from a PDF, or empty string if extraction fails."""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            pages = [page.extract_text() or "" for page in pdf.pages]
        return " ".join(pages).strip()
    except Exception as e:
        print(f"  [WARN] Could not read {pdf_path.name}: {e}")
        return ""


def detect_keywords(text: str) -> list:
    """Return list of keywords found in text (case-insensitive)."""
    found = []
    text_lower = text.lower()
    for kw in KEYWORDS:
        if kw.lower() in text_lower:
            found.append(kw)
    return found


def make_preview(text: str) -> str:
    """Return a clean, truncated preview of the extracted text."""
    # Collapse excessive whitespace
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) > TEXT_PREVIEW_CHARS:
        return cleaned[:TEXT_PREVIEW_CHARS] + "..."
    return cleaned

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    pdf_files = sorted(RESUME_FOLDER.glob("*.pdf"))

    if not pdf_files:
        print(f"[ERROR] No PDF files found in:\n  {RESUME_FOLDER}")
        return

    print(f"Found {len(pdf_files)} PDF file(s). Extracting text...\n")

    rows = []
    empty_count = 0

    for pdf_path in pdf_files:
        print(f"  Processing: {pdf_path.name}")
        text     = extract_text(pdf_path)
        preview  = make_preview(text)
        keywords = detect_keywords(text)

        if not text:
            empty_count += 1

        kw_padded = (keywords + [""] * NUM_KEYWORD_COLS)[:NUM_KEYWORD_COLS]
        row = {
            "Resume File":            pdf_path.name,
            "Extracted Text Preview": preview,
            "Text Extracted?":        "Yes" if text else "No",
            "Suggested Notes":        "",          # left blank for manual entry
        }
        for i, kw in enumerate(kw_padded, start=1):
            row[f"Keyword {i}"] = kw
        rows.append(row)

    # Write CSV
    kw_cols    = [f"Keyword {i}" for i in range(1, NUM_KEYWORD_COLS + 1)]
    fieldnames = ["Resume File", "Extracted Text Preview", "Text Extracted?"] + kw_cols + ["Suggested Notes"]

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nDone.")
    print(f"  Resumes processed : {len(rows)}")
    print(f"  No text extracted : {empty_count}  (likely scanned/image PDFs — review manually)")
    print(f"  Output saved to   : {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
