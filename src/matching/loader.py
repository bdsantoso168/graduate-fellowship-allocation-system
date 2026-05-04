import os
import re
import hashlib
import pandas as pd
from pathlib import Path
from typing import List, Dict, Optional
from PyPDF2 import PdfReader
from docx import Document
from PIL import Image

# ---------------------------------------------------------------------------
# Configurable OCR tool paths -- relative to the project root (tools/ folder).
# loader.py lives at  src/matching/loader.py  -> three levels up = project root.
# Change _PROJECT_ROOT below if the tools/ folder moves relative to this file.
# ---------------------------------------------------------------------------
_PROJECT_ROOT  = Path(__file__).resolve().parent.parent.parent
_TESSERACT_EXE = _PROJECT_ROOT / 'tools' / 'Tesseract-OCR' / 'tesseract.exe'
_POPPLER_BIN   = _PROJECT_ROOT / 'tools' / 'poppler' / 'Release-25.12.0-0_2' / 'poppler-25.12.0' / 'Library' / 'bin'

try:
    import pytesseract
    from pdf2image import convert_from_path
    pytesseract.pytesseract.tesseract_cmd = str(_TESSERACT_EXE)
    POPPLER_PATH = str(_POPPLER_BIN)
    if not _TESSERACT_EXE.exists():
        print(f'[WARN] loader.py: Tesseract not found at {_TESSERACT_EXE}')
    if not _POPPLER_BIN.exists():
        print(f'[WARN] loader.py: Poppler not found at {_POPPLER_BIN}')
except ImportError:
    pytesseract = None

from src.database.models import Student
from src.utils.filename_parser import parse_filename
from src.database.crud import upsert_student_ingestion_batch, get_cached_student_record_map

# --- The Sanitization Pipeline (The Text Washer) ---

def clean_extracted_text(text: str) -> str:
    """
    SMS Text Washer (V4 - Dynamic Pattern Engine).
    Designed to handle 'Table Mashing' and 'Title Fusion' across
    unstructured international CVs/Resumes.
    """
    if not text: return ""

    # 1. Unicode & Ligature Cleanup (Fixes 'fi', 'fl', and invisible PDF noise)
    text = text.encode("ascii", "ignore").decode("ascii")  # Strip non-ASCII
    ligs = {"fi": "fi", "fl": "fl", "ff": "ff", "ffi": "ffi", "ffl": "ffl"}
    for k, v in ligs.items(): text = text.replace(k, v)

    # 2. DYNAMIC: Split Mashed Keywords (The 'SQLPython' or 'AWSCloud' fix)
    # Pattern: Split where a lowercase letter is followed by an Uppercase
    # EXCEPT for cases like 'iPhone' or 'scikit-learn' (handled by common sense regex)
    text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)

    # 3. DYNAMIC: Split Fused Headers (The 'BUSINESSANALYSTBachelor' fix)
    # Pattern: Split where an All-Caps word meets a Title-Case word
    # Logic: Look for 2+ Caps followed by 1 Cap and 1 Lowercase
    text = re.sub(r'([A-Z]{2,})([A-Z][a-z])', r'\1 \2', text)

    # 4. DYNAMIC: Fix Table Mashing (The 'March201571.80%' fix)
    # Pattern: Split letters from numbers and vice versa
    text = re.sub(r'([a-zA-Z])([0-9])', r'\1 \2', text)
    text = re.sub(r'([0-9])([a-zA-Z])', r'\1 \2', text)
    # Split percentages/decimals from text (e.g., '71.80%HSC')
    text = re.sub(r'([%0-9])([A-Z])', r'\1 \2', text)

    # 5. DYNAMIC: The 'Orphan Space' Fix (The 'm em ber' or 'Proce ss' fix)
    # Logic: If a single space is trapped between two lowercase letters, it's likely a mistake.
    # We temporarily remove these, then collapse real spaces.
    text = re.sub(r'([a-z])\s([a-z])', r'\1\2', text)

    # 6. Break 'Sticky' Punctuation (The 'Python/SQL' or 'BRDsuser' fix)
    text = re.sub(r'([a-z0-9])([/\\()&])([a-z0-9])', r'\1 \3', text, flags=re.I)

    # 7. Final Polish: Collapse all whitespace and strip noise
    text = re.sub(r'\s+', ' ', text)   # Collapse multiple spaces
    text = re.sub(r'[§•|▪\*]', '', text)  # Remove common bullet junk

    return text.strip()

# --- Extraction Engine ---

def _detect_ext(file_path: str) -> str:
    """Detects extension using magic bytes or extension string."""
    ext = os.path.splitext(file_path)[1].lower()
    if ext in {'.pdf', '.docx', '.jpg', '.jpeg', '.png'}: return ext
    try:
        with open(file_path, 'rb') as f:
            head = f.read(8)
        if head.startswith(b'%PDF'): return '.pdf'
        if head.startswith(b'PK\x03\x04'): return '.docx'
    except: pass
    return ext

def extract_text_from_pdf(file_path: str) -> str:
    """Reads all pages; falls back to OCR if text is sparse."""
    try:
        reader = PdfReader(file_path, strict=False)
        # Greedily extract every page for international CV depth
        text = "\n".join([p.extract_text() or "" for p in reader.pages])

        # OCR Fallback for image-based PDFs
        if len(text.strip()) < 100 and pytesseract:
            images = convert_from_path(file_path, poppler_path=POPPLER_PATH)
            text = "\n".join([pytesseract.image_to_string(img) for img in images])
        return text
    except Exception as e:
        print(f"[ERROR] PDF extraction failed for '{file_path}': {e}")
        return ""

def extract_text_from_docx(file_path: str) -> str:
    """Standard docx paragraph extraction."""
    try:
        doc = Document(file_path)
        return "\n".join([p.text for p in doc.paragraphs])
    except: return ""

def extract_text(file_path: str) -> str:
    """Universal router for ingestion with built-in sanitization."""
    ext = _detect_ext(file_path)
    text = ""
    if ext == '.pdf': text = extract_text_from_pdf(file_path)
    elif ext == '.docx': text = extract_text_from_docx(file_path)
    elif ext in ['.jpg', '.jpeg', '.png'] and pytesseract:
        text = pytesseract.image_to_string(Image.open(file_path))

    # Apply the Sanitization Pipeline (The Text Washer)
    return clean_extracted_text(text)

# --- Database Ingestion ---

def ingest_resumes_to_db(base_folder: str = "data/students", batch_id: int = None, allowed_uids: Optional[set] = None, strict_mode: bool = False):
    """Batches folder resumes into one database write operation."""
    uid_map = build_uid_file_map(base_folder)
    if allowed_uids is not None:
        uid_map = {uid: path for uid, path in uid_map.items() if uid in allowed_uids}
    mode_label = "STRICT" if strict_mode else "STANDARD"
    print(f"--- [INGESTOR] Mode={mode_label} Source={base_folder} Caching {len(uid_map)} resumes to Database ---")

    payload = []
    for uid, file_path in uid_map.items():
        if os.path.basename(file_path).startswith('.'): continue
        raw_text = extract_text(file_path)
        f_hash = hashlib.sha256(raw_text.encode()).hexdigest()

        meta = parse_filename(os.path.basename(file_path)).__dict__
        name = resolve_student_name(uid, raw_text, meta)
        payload.append((uid, name, raw_text, f_hash, batch_id))

    if payload: upsert_student_ingestion_batch(payload)
    return {uid for uid, *_ in payload}

def get_roster_uids_from_file(excel_path: str) -> set:
    """Returns the UID set from the currently selected roster file."""
    df = pd.read_excel(excel_path) if excel_path.endswith(".xlsx") else pd.read_csv(excel_path)
    uids = [str(row.get("Universal ID") or row.get("UID") or "").strip() for _, row in df.iterrows()]
    return {u for u in uids if u}

# --- Engine Loading ---

def load_students_from_excel_with_audit(excel_path: str):
    """Builds Student objects with a full UID audit trail.

    Returns:
        tuple: (students, roster_uids, loaded_uids, skipped_missing_resume_uids)
            students                    -- list of Student objects ready for matching
            roster_uids                 -- all UIDs found in the Excel roster
            loaded_uids                 -- UIDs successfully loaded (had resume text)
            skipped_missing_resume_uids -- UIDs in roster whose DB record had no text
    """
    df = pd.read_excel(excel_path) if excel_path.endswith(".xlsx") else pd.read_csv(excel_path)

    roster_uids: set = set()
    for _, row in df.iterrows():
        uid = str(row.get("Universal ID") or row.get("UID") or "").strip()
        if uid:
            roster_uids.add(uid)

    record_map = get_cached_student_record_map(list(roster_uids))

    students = []
    loaded_uids: set = set()
    skipped_uids: set = set()

    for _, row in df.iterrows():
        uid = str(row.get("Universal ID") or row.get("UID") or "").strip()
        if not uid:
            continue
        record = record_map.get(uid) or {}
        if not record.get('resume_text'):
            skipped_uids.add(uid)
            continue

        raw_m = row.get("Calculated Work Experience (in months)", 0)
        try: m = float(raw_m) if pd.notna(raw_m) else 0.0
        except: m = 0.0

        raw_s = row.get("Semester Award", 0.0)
        try: s = float(raw_s) if pd.notna(raw_s) else 0.0
        except: s = 0.0

        students.append(Student(
            student_id=uid,
            name=str(row.get("Name", f"UID {uid}")),
            preferred_name=str(row.get("Person Preferred", "")),
            first_name=str(row.get("Person First", "")),
            last_name=str(row.get("Person Last", "")),
            gpa=float(row.get("GPA", 0.0)),
            degree_program=str(row.get("Graduate Program", "General")),
            skills=record.get('normalized_skills') or [],
            resume_text=record.get('resume_text'),
            experience=m / 12.0,
            semester_award=s
        ))
        loaded_uids.add(uid)

    return students, roster_uids, loaded_uids, skipped_uids


def load_students_from_excel(excel_path: str) -> List[Student]:
    """Compatibility wrapper -- returns students only. Use load_students_from_excel_with_audit for the full audit trail."""
    students, _, _, _ = load_students_from_excel_with_audit(excel_path)
    return students

# --- Heuristics ---

def build_uid_file_map(base_folder: str) -> Dict[str, str]:
    """Maps Universal IDs to local file paths."""
    uid_map = {}
    for root, dirs, files in os.walk(base_folder, topdown=True):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for f in files:
            full_path = os.path.join(root, f)
            ext = _detect_ext(full_path)
            if ext in ('.pdf', '.docx', '.jpg', '.png', '.jpeg'):
                uid = os.path.basename(root)
                if not re.match(r'^UID\d+$', uid, re.IGNORECASE):
                    uid = parse_filename(f).uid
                if uid: uid_map[uid] = full_path
    return uid_map

def resolve_student_name(uid, text, meta):
    """Resolves name from metadata or defaults to UID."""
    if meta.get("name_raw"): return meta["name_raw"].title()
    return f"UID {uid}"
