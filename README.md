# Staffing Allocation System — GUI Layer

A NiceGUI-based admin interface for an AI-powered staffing allocation system,
built as part of a semester consulting project. The system matches applicants
to business units by analyzing resumes, skills, and degree programs using
NLP (spaCy + BERT) and a weighted scoring algorithm.

This repository contains **my individual contribution**: the frontend GUI layer
(`staffing_app.py`). The broader project includes a matching pipeline, database
layer, and user documentation built collaboratively by the team.

![Graduate Fellowship Allocation System thumbnail](https://github.com/user-attachments/assets/d3d82c4d-6ee9-4c84-9763-8c85a7ae1fc9)

---

## Screenshots

> Add screenshots of the running app here after setup.

---

## Features

| Page | What it does |
|---|---|
| **Welcome** | Landing page with 4-step workflow overview |
| **Upload Data** | Upload applicant roster CSV/Excel + resume ZIP; live counters update on upload |
| **Common Skills** | Manage the shared skill pool (~30% of matching score) with an explanatory banner |
| **Manage Departments** | Card-based interface to add, edit, and remove departments |
| **Matching Result** | Run the engine, watch a live stopwatch, view results table, export CSV/Excel |

Additional details:
- Live upload counters showing applicants detected and resumes extracted in real time
- Live elapsed stopwatch during the matching run
- Resume viewer button per row — opens PDF directly in a new tab for match verification
- Organization brand colors applied throughout (configurable via constants)
- Dark sidebar navigation with gold hover highlight

---

## Tech Stack

| Layer | Technology |
|---|---|
| UI framework | NiceGUI (Python reactive web UI) |
| Data handling | Pandas |
| Database | MySQL via custom CRUD layer |
| NLP pipeline | spaCy + BERT + OCR (subprocess) |
| Language | Python 3.10+ |

---

## Design Decisions

This interface was iteratively improved through team leader code reviews and professor
feedback sessions. Key decisions and their rationale are documented inline in the code
using `[TEAM-LEADER]` and `[PROF-REVIEW]` tags.

| Decision | Rationale |
|---|---|
| Sidebar navigation over top tabs | Team leader feedback — reduces cognitive load |
| Live upload counters (stat cards) | Praised as clearer than a plain text status label |
| Common Skills explanatory banner | Professor noted end users confused common vs. department skills |
| Live elapsed stopwatch | Team leader request — processing time varies by hardware (30 s GPU vs. 2-3 min CPU) |
| Card-based department layout | Makes department profiles scannable at a glance |
| Resume viewer (open in new tab) | Strongly endorsed by professor for verifying individual match decisions |
| "Confirm" instead of "Next" | Makes step progression feel deliberate; discussed in team review |

---

## Setup

### Prerequisites
- Python 3.10+
- MySQL (or SQLite for local testing)
- The full project pipeline in `src/` (not included — this repo contains the GUI layer only)

### Install dependencies
```bash
pip install nicegui pandas openpyxl
```

### Add organization logo
Place your organization logo PNG at `static/logo.png`. The file is excluded from this
repository — add your own before running.

### Run
```bash
python staffing_app.py
```
Then open `http://127.0.0.1:8080`.

### Sample data
See `sample_data/` for a fictional roster CSV you can use to test the upload flow
without any real applicant records.

---

## Repository structure

```
.
├── staffing_app.py          Main GUI application
├── sample_data/
│   ├── sample_roster.csv       Fictional demo data — safe to share
│   └── README.md               Required CSV column specification
├── static/
│   └── logo.png                (Not included) Place organization logo here
├── src/                        (Not included) NLP pipeline and database layer
│   ├── main.py                 Matching subprocess entry point
│   ├── database/
│   │   └── crud.py             Database read/write functions
│   └── utils/
│       └── filename_parser.py
├── README.md
└── .gitignore
```

---

## Privacy and data safety

- **No real applicant records are included.** The `data/` folder is excluded by `.gitignore`.
- **No resume files are included.** All PDF/DOCX files are excluded by `.gitignore`.
- **No credentials are hardcoded.** Database connections are configured in `src/database/crud.py`
  which is not part of this repository.
- **Brand assets** are parameterized as constants (`ORG_BLUE`, `ORG_GOLD`) and
  the logo file is excluded from the repository.

---

## Acknowledgements

Built during a graduate consulting course project. Iterative feedback from team leader
code reviews and professor-led design sessions shaped the final interface.
