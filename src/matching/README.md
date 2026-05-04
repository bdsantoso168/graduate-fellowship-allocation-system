# `src/matching/` — Core Matching Engine

This folder contains the four modules that power the automated student-to-department placement pipeline. Together they form a complete NLP-driven matching engine: from raw resume ingestion all the way to ranked, capacity-aware department assignments.
<img width="2752" height="1536" alt="GFMP Infographic" src="https://github.com/user-attachments/assets/0fd72725-10b6-41ce-b6e6-c486b6029f41" />

---

## Module Overview

| File | Role |
|---|---|
| `loader.py` | Reads, cleans, and stores raw resume text into MySQL |
| `processor.py` | Extracts skills and executes hybrid lexical/semantic scoring |
| `matcher.py` | Builds the global score matrix and runs the 4-phase placement |
| `crud.py` | Manages all permanent and temporary MySQL database operations |

---

## How the Pipeline Works

```
Student Roster (Excel)
        +
Resume Files (PDF / DOCX / Image)
        |
        v
  [ loader.py ]
  Extracts text via OCR or direct parsing.
  Cleans and caches raw text in MySQL students table.
        |
        v
  [ processor.py ]
  Identifies skills using SkillNer (hard skills) + PhraseMatcher (soft skills).
  Validates with spaCy NER. Ranks with BM25. Deduplicates with SBERT at 0.90 threshold.
        |
        v
  [ matcher.py ]
  Computes student-department scores across the full matrix.
  Runs 4-phase placement respecting department capacity caps.
        |
        v
  [ crud.py ]
  Persists matched results to matched_students table.
  Exposes read/write/update operations for the NiceGUI frontend.
        |
        v
  Matching Results (UI display + CSV/Excel export)
```

---

## Weighted Scoring Formula

Each student-department pair receives a composite score based on four weighted components:

```
Score = 0.40 * d_score
      + 0.30 * c_score
      + 0.25 * exp_score
      + 0.05 * gpa_score
```

| Component | Weight | Description |
|---|---|---|
| `d_score` | 40% | Departmental skill match (BM25 lexical + SBERT semantic hybrid) |
| `c_score` | 30% | Common/baseline skills match (non-differentiating soft skills) |
| `exp_score` | 25% | Work experience in years, normalized to a 0–1 scale (cap: 5 years) |
| `gpa_score` | 5% | GPA normalized to a 0–1 scale (cap: 4.0) |

> Degree program match was evaluated and removed from the active scoring formula. It is retained in the data model for audit and display purposes only.

---

## Hybrid Matching Logic (`processor.py`)

The skill scoring engine combines two complementary methods for each department-student pair:

**Lexical match (BM25):** checks whether the student's extracted skill tokens appear in the department's required skill list. Fast, interpretable, zero-false-positive.

**Semantic match (SBERT):** uses `all-MiniLM-L6-v2` sentence embeddings with cosine similarity at a 0.65 threshold to catch synonyms and contextually equivalent skills that BM25 misses (e.g., "data visualization" matching "Tableau").

```
Final hybrid ratio = (lexical_ratio * 0.10) + (semantic_ratio * 0.90)
```

The 90/10 weighting intentionally favors semantic coverage to handle the diverse, non-standardized language found in international resumes.

---

## 4-Phase Placement Funnel (`matcher.py`)

Once scores are computed across the full student-department matrix, placement runs in four sequential phases. A student is assigned exactly once and skipped in all subsequent phases.

```
Phase 1 — Specialist Priority
  Students with at least one domain-specific anchor skill
  are matched to SPECIALISTS-tier departments first.
  Specialist boost: score * 1.5
  No anchor skill found: score forced to 0.0 (protection kill-switch)

Phase 2 — Generalist Draft
  Remaining unassigned students are placed into
  GENERALISTS-tier departments while respecting capacity caps.

Phase 3 — Open Fill
  Any student still unassigned is placed into whichever
  department still has remaining capacity, regardless of tier.

Phase 4 — Strict Fallback
  Guarantees every valid loaded student is assigned.
  Expands department capacity in-memory only (never persisted to DB).
  Uses non-specialist departments first.
```

Each department has a configurable `max_students` cap (default: 3). Caps are enforced per phase and are only temporarily expanded in Phase 4.

---

## Candidate DNA Pipeline (Pre-Match Quality Filter)

Before the scoring matrix runs, each student's extracted skills pass through the Harmony Pipeline:

1. **Deduplication** via SBERT cosine similarity at a 0.90 threshold — removes near-duplicate terms.
2. **Semantic validation** via `filter_with_sbert` at 0.60 threshold — discards noise terms that don't resemble real professional skills when compared against the SKILL_DB reference.
3. **BM25 ranking** — re-orders the surviving skills by how prominently they appear in the student's resume text, with a 2x boost for skills found in section headers.

The pipeline output is saved back to the database as `normalized_skills` and is what appears in the matching results export.

---

## Text Washer (`loader.py`)

Resume text extracted from PDFs and DOCX files goes through the SMS Text Washer before any NLP processing. It handles common extraction artifacts from international resumes:

| Problem | Example | Fix |
|---|---|---|
| Mashed keywords | `SQLPython` | Split on lowercase-to-uppercase boundary |
| Fused headers | `BUSINESSANALYSTBachelor` | Split on all-caps to title-case boundary |
| Table mashing | `March201571.80%` | Split letters from digits |
| Orphan spaces | `m em ber` | Remove spaces trapped between two lowercase letters |
| Sticky punctuation | `Python/SQL` | Space around delimiters |

OCR fallback (via Tesseract + Poppler) activates automatically when extracted text is under 100 characters, catching image-based PDFs.

---

## Performance Metrics

These figures reflect a live run on a real student cohort processed through the full pipeline:

| Metric | Result |
|---|---|
| Match Accuracy | 60% |
| Top-5 Placement Rate | 55.5% |
| Processing Time | 4–6 minutes |
| Students Placed | 70+ across 19 departments |
| Allocation | 19 departments × 3 slots = 57 positions vs. 73 students |
| Fallback Volume | ~16 students placed via Phase 4 strict fallback |

> Most students land in their 2nd or 3rd best-fit department due to specialist tier priority draft absorbing top scorers first.

---

## Key Design Decisions

**Why SBERT over pure keyword matching?** Resumes from international students use highly varied phrasing for the same skills. A pure BM25 approach missed too many valid matches. SBERT semantic similarity bridges the vocabulary gap while BM25 preserves interpretability for exact matches.

**Why a 4-phase placement over a single global sort?** A global sort causes high-scoring students to cluster in technical departments, starving generalist departments. The phased approach guarantees specialist departments are filled before generalist competition begins.

**Why is GPA only 5%?** GPA is a weak differentiator at the graduate level and was found to correlate poorly with departmental fit. It is included to break ties and as a lightweight signal, not as a primary driver.

**Why is degree match excluded from scoring?** Early testing showed degree program matching was too blunt — many strong candidates for a department held degrees from adjacent fields. Removing it improved placement quality. Degree is retained for display and audit only.

---

## Dependencies

```
spacy >= 3.x          # NER and noun chunk extraction
skillNer              # Hard skill extraction from SKILL_DB
sentence-transformers # SBERT embeddings (all-MiniLM-L6-v2)
rank-bm25             # BM25 lexical index
PyPDF2                # PDF text extraction
pytesseract           # OCR fallback for image-based PDFs
pdf2image             # PDF-to-image conversion for OCR
python-docx           # DOCX text extraction
Pillow                # Image handling for OCR
pandas                # Roster loading and Excel I/O
mysql-connector-python # Database connection
```

Full pinned versions are in the project-level `requirements.txt`.

---

## Related Modules

- `src/database/` — database config, schema, and CRUD layer
- `src/utils/filename_parser.py` — UID extraction from resume filenames
- `nicegui_app.py` — frontend UI that triggers this pipeline via `python -m src.main`
