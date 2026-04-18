# Graduate Fellowship Allocation System

**ISOM 424 – Consulting Practicum**

> A faculty-supervised consulting engagement to redesign and stabilize a graduate fellowship matching system for an academic institution, transitioning it from a fragile manual process into a production-ready, server-deployable platform.

![Graduate Fellowship Allocation System thumbnail](https://github.com/user-attachments/assets/d3d82c4d-6ee9-4c84-9763-8c85a7ae1fc9)

---

## Project Overview

The existing fellowship allocation process required 40–50 hours of manual administrative effort per cycle, producing match accuracy of only 50–60%. This project targets an end-to-end automated pipeline that reduces admin labor while improving match quality to near 90%.

| Field | Details |
|---|---|
| Course | ISOM 424 – Consulting Practicum |
| Duration | 14 weeks (Jan – May 2026) |
| Team Size | 8 members |
| Client User | Associate Director, Fellowship Administration |
| Current Status | Active – final deployment phase (target: May 8, 2026) |
| Final Demo | May 11, 2026 |

---

## Repository Scope

Due to data sensitivity, NDA constraints, and institutional security requirements, all live development and real data remain within a secure university VPN environment.

This repository is used for:

- High-level system architecture and design documentation
- Sanitized process analysis (current vs. target state)
- Algorithm and technical decision logs
- UI/UX design evolution and decision records
- Resume classification and matching benchmarks

**No real student data, credentials, or sensitive institutional files are stored here.**

---

## Technology Stack

| Layer | Technology |
|---|---|
| Frontend / UI | NiceGUI (migrated from Streamlit) |
| Backend | Python |
| Skill Extraction | spaCy + SkillNER (with PyMuPDF + PyTesseract OCR fallback) |
| Matching Engine | BM25 (10%) + SBERT semantic similarity (90%) |
| Data Layer | MySQL |
| Hosting | University-managed Linux server |
| CRM Integration | Slate (restricted, VPN-only access) |

---

## System Architecture (High Level)

```
Excel Roster (Slate export)
        +
Resume / SOP Files (ZIP)
        |
        v
  [1] Data Loader (loader.py)
      - PyMuPDF primary extraction
      - PyTesseract OCR fallback (for Canva-formatted PDFs)
      - Plain-text stripping and normalization
        |
        v
  [2] Skill Processor (processor.py)
      - spaCy + SkillNER extraction
      - Noun-chunk fallback if SkillNER returns nothing
      - BM25 lexical check (first-pass)
      - SBERT semantic scoring (90% weight)
        |
        v
  [3] Matching Engine (matcher.py)
      Final score formula:
        40% departmental skill match
        30% common skill match
        25% work experience (normalized 0–1, capped at 5 years)
         5% GPA
      Tiebreaker: total score > dept skill score > UID > dept name
        |
        v
  [4] Allocation (multi-phase)
      Phase 1 (Specialist): top-fit technical departments
      Phase 2 (Generalist): remaining departments
      Phase 3 (Generalist overflow): unfilled slots
      Phase 4 (Safety fallback): unmatched students
      Each student assigned to exactly one department.
        |
        v
  [5] NiceGUI Interface
      Upload Data > Common Skills > Manage Departments > Run Match > View Results
      Export to Excel / CSV
```

---

## UI Development Journey

The frontend went through a significant evolution over the project lifecycle.

**Phase 1 – Streamlit (Inherited)**
The original system used Streamlit. Issues discovered: session lockout on concurrent use, slow reload times, and layout instability.

**Phase 2 – NiceGUI Migration**
Migrated to NiceGUI for a more stable, enterprise-grade experience. Key improvements:
- Persistent skill and department edits to database
- Vacancy cap per department (default 3 students)
- Delete confirmation dialogs (per client request)
- Student count notification after roster upload
- Resume preview feature (opens resume from results table)
- Suffolk University branding – official colors, logo, Get Help section

**Phase 3 – UI Stabilization (Week 10, April 2026)**
After a team-wide GUI design sprint where each team member built their own version, the best elements were combined:
- Dark navy sidebar + white content area (enterprise admin style)
- Step breadcrumb: Upload Data > Common Skills > Manage Department > Matching Result
- ag-grid replaced with `ui.table` to fix mount timing/WebSocket race condition
- ZIP file `.cpgz` artifact bug resolved (Mac double-zip issue)
- Renamed `Stipend` column to `Award` (client feedback)
- Replaced `NaN` with `N/A` in results display (client feedback)
- Download CSV wired to trigger an actual file download

---

## Key Technical Decisions

| Decision | Rationale |
|---|---|
| BM25 kept alongside SBERT | BM25 serves as a fast lexical first-pass filter; SBERT handles semantic similarity for skills not caught by exact match |
| Degree match dropped from scoring | Field was not standardized enough across resumes to produce reliable signal |
| Experience capped at 5 years (normalized 0–1) | Prevents over-weighting of candidates with very long experience histories |
| Multi-phase allocation (not highest-score-first) | Prevents top scorers clustering in technical departments; ensures equitable distribution |
| NiceGUI over Streamlit | Better session handling, lower latency, more control over component lifecycle |
| OCR added via PyTesseract | Handles Canva-formatted PDFs that PyMuPDF cannot parse (known limitation: top-to-bottom only, may misread multi-column layouts) |

---

## Matching Score Formula

```
Final Score =
    (0.40 × Departmental Skill Match Score)  ← BM25 10% + SBERT 90% blended
  + (0.30 × Common Skill Match Score)
  + (0.25 × Work Experience Score)           ← normalized 0–1, capped at 5 years
  + (0.05 × GPA Score)                       ← score out of 4.0
```

> Note: The `total_f_score` is used internally for ranking and allocation only. It is not exposed in the UI or CSV export.

---

## Folder Structure

```
graduate-fellowship-allocation-system/
├── docs/
│   ├── development-setup/        # Environment setup rationale and constraints
│   ├── ui-evolution/             # UI design decision records
│   └── algorithm/                # Matching logic and scoring documentation
├── resume-classification-framework/
│   └── Decision_Table_for_Manual_Matching.csv
├── resume-matching-benchmark/    # Sanitized accuracy benchmarks
├── INSTALLATION.md               # High-level setup guidance
└── README.md
```

---

## Current Phase (April – May 2026)

| Task | Status |
|---|---|
| NiceGUI UI stabilization and bug fixes | Complete |
| Client demo with Aki (Apr 7) | Complete |
| Technical documentation (A3) | In Progress |
| User guide for non-technical users | In Progress |
| Server migration to university Linux host | In Progress |
| Final client presentation | May 11, 2026 |

---

## Disclaimer

This repository is for **documentation and portfolio purposes only**.

All sensitive implementation details, real student data, institutional credentials, and live system files remain within approved university systems and are not stored or referenced here.

This project was conducted under a signed NDA with the client institution. Variable names and institutional identifiers have been generalized throughout this repository.
