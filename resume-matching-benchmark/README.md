# Resume Matching Benchmark

This repository contains the manual resume matching benchmark used to validate the automated matching system for the ISOM 424 consulting project.

## Contents
- `data/manual_matching_results.xlsx` — final benchmark matching table
- `data/resume_content_preview.csv` — Python-extracted resume text preview and keywords
- `data/degree_experience_preview.csv` — Python-extracted degree and experience helper file
- `documentation/README_Process.docx` — detailed process documentation

## Method Summary
The workflow followed:
1. Python-based resume text extraction
2. CSV import and structuring in Excel
3. Degree lookup and skills-based standardization
4. Degree-priority department classification
5. Final matched-results benchmark for validation against the system output

## Notes
- Raw resumes are not included here.
- This repository is intended for project documentation and validation support.
