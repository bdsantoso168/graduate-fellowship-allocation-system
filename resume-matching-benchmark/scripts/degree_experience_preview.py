"""
degree_experience_preview.py
-----------------------------
Scans all PDF resumes in this folder and extracts likely Degree and
Experience information for each resume, then writes a CSV for manual
review in Excel.

INSTALL (one-time):
    pip install pdfplumber

RUN:
    python "degree_experience_preview.py"

OUTPUT:
    degree_experience_preview.csv  (in the same folder as this script)
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
# Configuration
# ---------------------------------------------------------------------------

RESUME_FOLDER = Path(__file__).parent
OUTPUT_FILE   = RESUME_FOLDER / "degree_experience_preview.csv"

DEGREE_KEYWORDS = re.compile(
    r'\b(Bachelor|Master|BS|BA|BSc|MS|MBA|PhD|Doctor|Certificate|Associate)\b',
    re.IGNORECASE,
)

EDUCATION_HEADER = re.compile(r'\bEducation\b', re.IGNORECASE)

EXPERIENCE_HEADER = re.compile(
    r'\b(Experience|Professional Experience|Work Experience|Employment|Career)\b',
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def extract_text(pdf_path: Path) -> str:
    """Return all text from a PDF, or empty string if extraction fails."""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            pages = [page.extract_text() or "" for page in pdf.pages]
        return "\n".join(pages).strip()
    except Exception as e:
        print(f"  [WARN] Could not read {pdf_path.name}: {e}")
        return ""


def get_lines(text: str) -> list:
    """Split text into non-empty, stripped lines."""
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


def extract_degree(text: str) -> str:
    """
    Find the Education section header, then scan the next 10 lines for a
    degree phrase. Return the first matching line, or "" if none found.
    """
    lines = get_lines(text)
    for i, line in enumerate(lines):
        if EDUCATION_HEADER.search(line):
            window = lines[i + 1 : i + 11]  # next 10 lines
            for candidate in window:
                if DEGREE_KEYWORDS.search(candidate):
                    return candidate
    return ""


def extract_experience(text: str) -> str:
    """
    Find the Experience section header, collect the next 8 non-blank lines,
    and return the first 1–2 joined by ' | ', or "" if none found.
    """
    lines = get_lines(text)
    for i, line in enumerate(lines):
        if EXPERIENCE_HEADER.search(line):
            window = lines[i + 1 : i + 9]  # next 8 non-blank lines
            if not window:
                return ""
            # Return first 2 lines as a short summary
            summary_lines = window[:2]
            return " | ".join(summary_lines)
    return ""

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    pdf_files = sorted(RESUME_FOLDER.glob("*.pdf"))

    if not pdf_files:
        print(f"[ERROR] No PDF files found in:\n  {RESUME_FOLDER}")
        return

    print(f"Found {len(pdf_files)} PDF file(s). Extracting degree & experience...\n")

    rows = []
    empty_count = 0

    for pdf_path in pdf_files:
        print(f"  Processing: {pdf_path.name}")
        text = extract_text(pdf_path)

        if not text:
            empty_count += 1

        rows.append({
            "Resume File":          pdf_path.name,
            "Stud_Id":              pdf_path.stem,
            "Suggested Degree":     extract_degree(text),
            "Suggested Experience": extract_experience(text),
        })

    fieldnames = ["Resume File", "Stud_Id", "Suggested Degree", "Suggested Experience"]

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
