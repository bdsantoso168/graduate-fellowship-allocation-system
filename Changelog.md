# Changelog

All major changes to the Graduate Fellowship Allocation System are documented here.

---

## [Final Release] – May 11, 2026

### Project Delivered
- Final client presentation to Suffolk University Sawyer Business School stakeholders
- System deployed to university-managed Red Hat Linux server
- Technical guide and user manual submitted and delivered

---

## [v0.5] – May 2026 (Pre-Presentation)

### Changed
- Moved Common Skills step to appear after Manage Department in workflow (per professor feedback)
- Reverted department management layout to row-based view (name + skills + cap per row; pop-up on click for detail)
- Renamed download buttons to "Download Merged Results" and "Download Dept Allocation Summary"
- Removed CSV download option; Excel-only export retained
- Added green color indicator for "Process Complete" status on results page
- Updated Help page contact to reference ITS general number

### Fixed
- Integrated PDF resume parsing fix for resumes that previously only worked as DOCX

---

## [v0.4] – April 2026

### Added
- Student count toast notification after roster upload
- Delete confirmation dialogs on Common Skills and Manage Department pages (per Aki's explicit request)
- Working CSV download via `ui.download()` — previously the button existed but did nothing
- `clean_row()` helper that replaces all `None` and float `NaN` values with the string `"N/A"` before displaying in results
- Roster file upload lock — one file at a time; Remove button resets count to zero
- Student skills display in department view (Royal)
- "View Resume" button for inline resume popup from results table (Nikita)
- Suffolk University brand colors integrated (`#122e53`, `#b28917`)

### Changed
- Renamed `Stipend` column to `Award` throughout UI and all export files (per client request, Apr 7 meeting)
- Migrated all `ui.aggrid()` instances to `ui.table()` to resolve ag-grid WebSocket mount race condition causing blank rows
- Score column renamed with descriptive label and displayed as percentage (e.g. 91%) instead of raw decimal
- Student skills column removed from UI results view; retained in downloaded Excel report

### Fixed
- Hardcoded PyTesseract and Poppler paths replaced with relative paths bundled inside the project directory (cross-machine portability)
- ZIP upload bug — macOS `.cpgz` double-zip artifact caused only 3 resumes to match; fixed by re-zipping PDFs directly

---

## [v0.3] – March–April 2026

### Added
- Hybrid BM25 + SBERT scoring engine: BM25 lexical first pass (10%), SBERT semantic similarity (90%)
- Four-phase allocation algorithm: Specialist → Generalist → Generalist overflow → Safety fallback (lowest-count department)
- Department capacity caps (default: 3 students per department; configurable)
- Technical department multiplier (1.5x) for students with technical skills (SQL, Power BI, Python, etc.)
- GPA normalization for international grades to US 4.0 scale
- Experience normalization: capped at 5 years, scaled 0–1
- Tiebreaker logic: (1) total score, (2) departmental skill score, (3) UID alphabetical ascending, (4) department name alphabetical ascending
- Batch-based session management in database (each run = one batch; supports data reset between cycles)

### Changed
- Degree match removed entirely from scoring formula (was flat +2 bonus; now 0% weight)
- Final scoring weights confirmed: 40% dept skills + 30% common skills + 25% experience + 5% GPA
- Student silently skipped (not zero-scored) if resume returns empty text after PyMuPDF and OCR

---

## [v0.2] – February 2026

### Added
- NiceGUI interface replacing Streamlit (migrated Week 4 due to Streamlit instability and full-page rerun on every interaction)
- Multi-page PDF handling confirmed working in NiceGUI
- SkillNER skill extraction integrated into processor.py (spaCy noun chunk fallback if SkillNER finds nothing)
- PyMuPDF as primary text extractor in loader.py
- PyTesseract OCR as fallback for image-based and Canva-formatted PDFs
- GUI blueprint defined: Welcome → Upload Data → Common Skills → Manage Department → Matching Result
- Department tier system (department-level priority, not student-level ranking)
- Progress bar for resume ZIP upload
- Delete with confirmation dialog pattern established

### Changed
- Streamlit replaced by NiceGUI for all GUI work
- Tika deprioritized due to SSL certificate issues on macOS
- "Plus skills" tier removed from scoring after review; only preferred and common skill tiers retained

---

## [v0.1] – January 2026

### Initial State (Inherited System)
- Python-based matching engine: loader.py → processor.py → matcher.py
- Streamlit UI for review and export
- PyPDF2 for text extraction (failed on image-based and Canva PDFs)
- NLTK for skill tokenization (no semantic similarity)
- String-based matching only (could not recognize "MS Excel" and "Excel" as equivalent)
- First-come-first-served allocation (sorted by student name; not score-based)
- Manual administration requiring 40–50 hours per matching cycle
- Matching accuracy approximately 50–60%
