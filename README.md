# Graduate Fellowship Allocation System

**ISOM 424 – Consulting Practicum | Suffolk University – Sawyer Business School**

![Graduate Fellowship Allocation System thumbnail](https://github.com/user-attachments/assets/d3d82c4d-6ee9-4c84-9763-8c85a7ae1fc9)

> **Status: Completed and delivered — May 11, 2026**
> Final client presentation delivered to the Associate Director of Fellowship Administration and faculty stakeholders. System successfully deployed to a university-managed Red Hat Linux server.

---

## Project Context

The Sawyer Business School places graduate fellows with university departments twice per year. The previous process required 40–50 hours of manual administrator effort per cycle, with matching accuracy estimated at 50–60%. This 14-week consulting engagement redesigned the system from the ground up into a stable, server-deployed matching platform.

---

## What Was Built

A full-stack fellowship allocation system with:

- **Automated resume text extraction** (PyMuPDF primary, PyTesseract OCR fallback for image-based and Canva-formatted PDFs)
- **Hybrid NLP matching engine** combining BM25 lexical scoring (10% weight) and SBERT semantic similarity (90% weight) via spaCy + SkillNER
- **Weighted scoring formula:** 40% departmental skill match + 30% common skill match + 25% work experience (capped at 5 years, normalized 0–1) + 5% GPA (converted to US 4.0 scale)
- **Four-phase allocation algorithm:** Specialist placement → Generalist placement → Generalist overflow → Safety fallback (lowest-count department)
- **NiceGUI web interface** with guided workflow: Upload Data → Common Skills → Manage Departments → Run Matching → View Results
- **Department capacity controls** with configurable vacancy caps per department
- **MySQL database layer** with batch-based session management and full CRUD operations
- **Excel and CSV export** of matched results and department allocation summary

---

## Technology Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11 |
| NLP / Skill Extraction | spaCy, SkillNER |
| Semantic Matching | SBERT (sentence-transformers), BM25 |
| PDF Extraction | PyMuPDF (primary), PyTesseract + Poppler (OCR fallback) |
| Database | MySQL (via SQLAlchemy) |
| Frontend / GUI | NiceGUI |
| Data Handling | pandas, openpyxl |
| Server Environment | Red Hat Linux (university-managed) |

---

## System Architecture

```
Slate CRM (source)
    │
    ├── Student roster (Excel/CSV)
    └── Resume files (ZIP of PDFs/DOCX)
            │
            ▼
        loader.py
    (PyMuPDF → OCR fallback → plain text output)
            │
            ▼
        processor.py
    (SkillNER extraction → BM25 lexical + SBERT semantic scoring)
            │
            ▼
          MySQL
    (students, departments, common_skills, matched_students, matching_batches)
            │
            ▼
        matcher.py
    (weighted score matrix → 4-phase allocation → matched_students table)
            │
            ▼
        nicegui_app.py
    (web UI → results table → Excel/CSV export)
```

---

## Key Milestones

| Phase | Period | Outcome |
|---|---|---|
| Environment setup and system walkthrough | Jan 2026 | Local dev environment configured; system architecture understood |
| Text extraction research and validation | Feb 2026 | PyMuPDF + PyTesseract pipeline validated; tiered extraction strategy confirmed |
| GUI framework pivot | Feb 2026 | Migrated from Streamlit to NiceGUI for performance and stability |
| Matching algorithm refinement | Mar 2026 | Hybrid BM25/SBERT scoring implemented; 4-phase allocation designed |
| Client demo and feedback integration | Apr 7, 2026 | Live demo to Associate Director (Aki); NaN fix, Award column rename, vacancy caps confirmed |
| GUI improvements (Week 10 deliverable) | Apr 5–8, 2026 | Student count notification, delete confirmations, working CSV download, ag-grid replaced with ui.table |
| Technical documentation and user manual | Apr–May 2026 | Full handoff documentation produced for developers and non-technical users |
| Server deployment | May 2026 | System deployed to Red Hat Linux university server |
| Final client presentation | May 11, 2026 | Delivered to Associate Director, faculty stakeholders, and department chairs |

---

## Performance

- **Matching accuracy:** ~60% validated against 6 independent human reviewers across 30 resumes
- **Processing speed:** under 5 minutes for ~70–90 students across 19 departments (vs. 40–50 hours manually)
- **Placement quality:** 55%+ of students placed in their top 5 highest-scoring departments; average placement was 2nd or 3rd choice due to specialist-first priority rule

---

## GUI Contributions (Benedict D. Santoso)

My direct contributions to `nicegui_app_bds.py`:

- Dark navy sidebar with step breadcrumb navigation (Upload → Skills → Departments → Results)
- Student count toast notification after roster upload
- Delete confirmation dialogs on Common Skills and Manage Department pages
- Working CSV download via `ui.download()`
- `clean_row()` helper replacing all `None`/`NaN` values with `"N/A"` in the results table
- Renamed `Stipend` column to `Award` per client request (Apr 7 meeting)
- Migrated all `ui.aggrid()` instances to `ui.table()` to resolve ag-grid WebSocket mount race condition

---

## Repository Scope

Due to NDA and institutional data security requirements, all live development, real student data, and production credentials remain within the university's secure VPN environment.

This repository contains:

- High-level architecture and design documentation
- Process analysis (current vs. target state)
- Sanitized meeting notes and decision logs
- GUI development artifacts and design rationale
- Resume classification and matching benchmark frameworks

**No real student data, credentials, or internal system code is stored here.**

---

## Future Recommendations

1. **Standardize source files** – require a consistent Excel template from the CRM administrator to reduce extraction edge cases
2. **Expand the skill inventory** – department skill lists should be more granular and reviewed annually
3. **Machine learning upgrade** – once multi-year historical match data is available (~100+ labeled records), transition to ensemble methods (decision trees, random forests, XGBoost) or a domain-specific fine-tuned model

---

## Disclaimer

This repository is for documentation and portfolio purposes only.
All sensitive implementation details remain within approved institutional systems.
