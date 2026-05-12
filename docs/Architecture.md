# System Architecture

**Graduate Fellowship Allocation System | ISOM 424 | Spring 2026**

---

## Overview

The system ingests student roster data and resume files from a university CRM (Slate), extracts and scores skills using a hybrid NLP pipeline, and allocates students to graduate fellowship departments using a weighted scoring formula and a four-phase assignment algorithm.

---

## Data Flow

```
Slate CRM (source system, managed by Mara)
        │
        ├── Student roster (.xlsx or .csv)  ← exported and shared manually via email / OneDrive
        └── Resume ZIP (.zip of PDFs and DOCX)
                │
                ▼
           loader.py
        ┌──────────────────────────────────────────┐
        │  1. PyMuPDF attempts text extraction      │
        │  2. If < 100 characters returned:        │
        │     fall back to PyTesseract OCR          │
        │  3. Output: plain text string per resume  │
        │  4. Failure: student record saved to DB   │
        │     but filtered before matching phase    │
        └──────────────────────────────────────────┘
                │
                ▼
           processor.py
        ┌──────────────────────────────────────────┐
        │  SkillNER extracts skills from text       │
        │  If SkillNER finds nothing:               │
        │     fall back to spaCy noun chunks        │
        │  BM25 lexical match (10% weight)          │
        │  SBERT semantic match (90% weight)        │
        │  Per-skill score: max(BM25, SBERT)        │
        └──────────────────────────────────────────┘
                │
                ▼
             MySQL
        ┌──────────────────────────────────────────┐
        │  students         (roster + extracted)   │
        │  departments      (skills, caps, tiers)  │
        │  common_skills    (global baseline)      │
        │  matched_students (allocation output)    │
        │  matching_batches (session management)   │
        └──────────────────────────────────────────┘
                │
                ▼
           matcher.py
        ┌──────────────────────────────────────────────────────┐
        │  Scoring formula per student-department pair:         │
        │    40% departmental skill match score                 │
        │    30% common skill match score                       │
        │    25% work experience (normalized, capped at 5 yrs)  │
        │     5% GPA (converted to US 4.0 scale)                │
        │                                                        │
        │  Technical departments: 1.5x multiplier applied       │
        │  for students with qualifying technical skills        │
        │                                                        │
        │  4-Phase Allocation:                                  │
        │    Phase 1 – Specialist: assign top scorer to each   │
        │              technical dept (strict skill threshold)  │
        │    Phase 2 – Generalist: fill remaining slots with   │
        │              highest global scorers                   │
        │    Phase 3 – Overflow: handle excess students         │
        │    Phase 4 – Safety fallback: assign remaining       │
        │              unassigned students to department with  │
        │              lowest current count                    │
        │                                                        │
        │  Tiebreaker (4 levels):                               │
        │    1. Highest total score                             │
        │    2. Highest departmental skill score                │
        │    3. Student UID ascending (alphabetical)            │
        │    4. Department name ascending (alphabetical)        │
        └──────────────────────────────────────────────────────┘
                │
                ▼
           nicegui_app.py
        ┌──────────────────────────────────────────┐
        │  Web interface (NiceGUI, localhost:8080) │
        │  Guided 4-step workflow:                  │
        │    1. Upload Data                         │
        │    2. Common Skills                       │
        │    3. Manage Departments                  │
        │    4. Matching Result                     │
        │  Export: Excel (.xlsx) and CSV           │
        │  Results: UID, Name, Dept, Degree,       │
        │           Skills, GPA, Award Amount      │
        └──────────────────────────────────────────┘
```

---

## Module Reference

| File | Role |
|---|---|
| `loader.py` | PDF/DOCX text extraction; PyMuPDF primary, PyTesseract OCR fallback |
| `processor.py` | Skill extraction (SkillNER + noun chunk fallback); BM25 + SBERT scoring |
| `matcher.py` | Weighted scoring matrix; 4-phase allocation; tiebreaker logic |
| `nicegui_app.py` | Web UI; session management; file upload handling; result display and export |
| `src/database/crud.py` | CRUD operations for students, departments, skills, matched records |
| `src/database/db_setup.sql` | Schema definition for all five tables |
| `src/utils/filename_parser.py` | Parses student UID from resume filenames for roster lookup |

---

## Scoring Formula

```
Total Score = (0.40 × dept_skill_score)
            + (0.30 × common_skill_score)
            + (0.25 × experience_score)
            + (0.05 × gpa_score)
```

Where:
- `dept_skill_score` = hybrid BM25/SBERT score against department-specific preferred skills
- `common_skill_score` = hybrid BM25/SBERT score against global common skills list
- `experience_score` = years of experience / 5, capped at 1.0
- `gpa_score` = GPA / 4.0 (international GPAs normalized to US scale)

Note: Degree match was evaluated and removed from the final formula. The `preferred_degrees` field remains on the Department object for future use.

---

## Session and Data Management

Each matching run creates a new `matching_batch` record with a status of `IN_PROGRESS` or `COMPLETED`. Student records belong to one batch via foreign key. Clearing a session removes all student and result records for that batch without affecting department or skill configuration.

Student data is treated as temporary by design: data is processed during the matching run and not retained beyond the session per institutional security policy.

---

## Known Limitations

| Limitation | Detail |
|---|---|
| OCR column layout | PyTesseract reads strictly top-to-bottom; multi-column resume layouts may be misread |
| Lexical gap | System cannot distinguish "MS Excel" from "Excel" at the lexical scoring stage; SBERT handles this at the semantic layer |
| Training data | ~73 resumes available; ML-based improvements would require ~100+ labeled historical records |
| Cross-platform paths | PyTesseract and Poppler paths must be configured per machine; relative path bundling implemented as mitigation |
