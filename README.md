# Graduate Fellowship Allocation System - Staffing Allocation System
**Consulting Practicum**

![Graduate Fellowship Allocation System thumbnail](https://github.com/user-attachments/assets/d3d82c4d-6ee9-4c84-9763-8c85a7ae1fc9)

An NLP-driven, automated matching system that places graduate students into fellowship departments based on resume skills, work experience, and academic standing. Built as a faculty-supervised consulting engagement over a 14-week sprint.

---

## What This System Does

The existing fellowship allocation process required 40–50 hours of manual administrative labor per cycle, with match accuracy hovering around 50–60% due to inconsistent resume formats and subjective reviewer judgment.

This system replaces that process with a four-module Python pipeline that reads resumes, extracts skills using NLP, scores each student against every active department using a weighted formula, and places students via a capacity-aware 4-phase draft.

```
Score = 0.40 × dept_skill_match
      + 0.30 × common_skill_match
      + 0.25 × work_experience
      + 0.05 × GPA
```

---

## System Architecture

```
src/
  matching/
    loader.py       — Resume ingestion, OCR fallback, text sanitization
    processor.py    — SkillNer extraction, SBERT embeddings, BM25 ranking
    matcher.py      — Score matrix + 4-phase department placement
  database/
    crud.py         — MySQL read/write operations for all system tables
  utils/
    filename_parser.py  — UID extraction from resume filenames
nicegui_app.py          — Admin dashboard (NiceGUI web UI)
requirements.txt        — All Python dependencies
data/                   — Temporary upload storage (not tracked)
```

The matching engine runs entirely in Python. The NiceGUI frontend provides a browser-based admin interface for uploading rosters, configuring departments, running the matching process, and exporting results to CSV or Excel.

---

## Matching Pipeline

```
Student Roster (Excel / CSV)  +  Resume Files (PDF, DOCX, Image)
                  |
          [ loader.py ]
          Parses and cleans raw resume text.
          OCR fallback via Tesseract for image-based PDFs.
                  |
          [ processor.py ]
          Dual-stream skill extraction:
            Stream 1 — SkillNer hard skills (dictionary-based)
            Stream 2 — PhraseMatcher soft skills (common skills DB)
            Stream 3 — spaCy noun chunks (safety net)
          SBERT deduplication → semantic validation → BM25 ranking
                  |
          [ matcher.py ]
          Computes student × department score matrix.
          Runs 4-phase capacity-aware placement draft.
                  |
          [ crud.py ]
          Persists matched results to MySQL.
          Serves data to NiceGUI results dashboard.
```

---

## 4-Phase Placement

| Phase | Name | Who Gets Placed |
|---|---|---|
| 1 | Specialist Priority | Students with domain-specific anchor skills; 1.5x score boost |
| 2 | Generalist Draft | Remaining students placed into broader-scope departments |
| 3 | Open Fill | Any student still unassigned to any department with capacity |
| 4 | Strict Fallback | Guarantees every valid student is placed; expands caps in-memory only |

Each department has a configurable student cap (default: 3). Specialist departments require at least one anchor skill — without it, the score is forced to zero (protection kill-switch).

---

## Performance Results

These metrics reflect a live run on a real student cohort:

| Metric | Result |
|---|---|
| Match Accuracy | 60% |
| Top-5 Placement Rate | 55.5% |
| Students Placed | 70+ |
| Departments Active | 19 |
| Total Slots | 57 (19 × 3) |
| Students via Fallback | ~16 |
| Processing Time | 4–6 minutes end-to-end |

---

## Technology Stack

| Layer | Technology |
|---|---|
| Language | Python 3.11 |
| NLP Engine | spaCy (`en_core_web_md`) + SkillNer |
| Skill Embeddings | Sentence-BERT (`all-MiniLM-L6-v2`) |
| Lexical Matching | BM25 (`rank-bm25`) |
| OCR | Tesseract + Poppler via `pytesseract` / `pdf2image` |
| Database | MySQL via `mysql-connector-python` |
| Frontend | NiceGUI (Python-based web UI) |
| Resume Parsing | PyPDF2, python-docx, Pillow |
| Data I/O | pandas (Excel/CSV roster loading and export) |

---

## Repository Structure

This repository is used for documentation, sanitized code artifacts, and portfolio-level explanation of the system. Live development, real data, and system execution occur within a secure university VPN environment.

```
graduate-fellowship-allocation-system/
├── src/
│   ├── matching/
│   │   ├── README.md           — Matching engine deep-dive
│   │   ├── loader.py           — Resume ingestion and sanitization
│   │   ├── processor.py        — Skill extraction and scoring
│   │   └── matcher.py          — Placement engine
│   └── database/
│       └── crud.py             — Database operations
├── docs/
│   ├── system/
│   │   └── overview.md         — Architecture and design documentation
│   └── development-setup/
│       └── README.md           — Environment setup rationale
├── resume-matching-benchmark/  — Deprecated: earlier rule-based benchmark
├── resume-classification-framework/ — Manual classification decision table
├── .gitignore
└── README.md
```

**No real student data, credentials, or internal configuration files are stored in this repository.**

---

## Security and Data Constraints

All live system execution takes place within a secure, university-managed VPN environment. The following constraints apply across the entire project:

- Student IDs, GPA, and resume content are never committed to this repository
- Department names and internal organizational references are anonymized in all public artifacts
- MySQL credentials and server configuration are managed externally via environment variables
- The system must be run from a local, non-cloud-synced directory (OneDrive sync causes runtime errors)

---

## Engagement Timeline

| Period | Focus |
|---|---|
| January–February | Environment setup, pipeline architecture, initial extraction validation |
| February–March | Matching algorithm development, hybrid scoring, GUI pivot to NiceGUI |
| March–April | Skill pipeline refinement, GUI stabilization, manual benchmark validation |
| April–May | Documentation, server deployment prep, final demonstration |

**Status: Consulting engagement complete. Final demonstration delivered May 2026.**

---

## Disclaimer

This repository is for documentation and portfolio purposes only. All sensitive implementation details, real student data, and institutional configurations remain within approved institutional systems.
