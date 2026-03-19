# Resume Matching Benchmark

This folder contains the manual benchmark workflow used to validate the automated matching system in the Graduate Fellowship Allocation System project.

## Purpose
The goal of this work was to create a structured manual benchmark to compare against the system-generated matching results.

## Workflow
1. Python-based resume text extraction
2. CSV generation for preview, keywords, degree, and experience
3. Excel import and Power Query structuring
4. Degree lookup and standardized experience logic
5. Degree-priority department classification
6. Final matched-results benchmark for validation

## Files
### data/
- `manual_matching_results.xlsx` — final benchmark matching table
- `resume_content_preview.csv` — extracted resume preview and keyword helper file
- `degree_experience_preview.csv` — extracted degree and experience helper file

### scripts/
- `extract_resume_content.py` — extracts resume preview text and keywords
- `degree_experience_preview.py` — extracts suggested degree and experience fields

### documentation/
- `README_Process.docx` — full process documentation

## Notes
- Raw resumes are not included in this repository.
- Department matching uses a degree-priority rule-based logic with skills as fallback.
- This benchmark is intended for internal validation against the automated system.
