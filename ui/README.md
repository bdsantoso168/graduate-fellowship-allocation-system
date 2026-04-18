# ui/ — NiceGUI Frontend

This folder contains the GUI layer of the staffing allocation system. It is a
single-file Python application built with **NiceGUI** — a Python-native reactive
web UI framework that runs a local web server and renders the interface in the
browser without requiring any HTML or JavaScript files.

---

## What the app does

The interface gives an admin user a structured, step-by-step workflow for running
the matching pipeline end-to-end:

```
Welcome  →  Upload Data  →  Common Skills  →  Manage Units  →  Matching Result
```

Each step is a panel in a single-page app. Navigation shows and hides panels
without a full page reload, which keeps live counters and the matching timer
intact as the user moves between steps.

---

## Pages

### Welcome
Landing page that explains the 4-step workflow before the user starts. Added after
feedback that first-time users were unsure where to begin.

### Upload Data
- Upload an applicant roster (CSV or Excel)
- Upload a ZIP archive of resume files (PDF or DOCX)
- Two live stat cards update in real time: applicants detected from the roster and
  resume files successfully extracted from the ZIP
- A confirmation dialog guards the "Clear All Data" action to prevent accidental
  data loss

### Common Skills
- Manage the shared skill pool that is evaluated across all business units during
  matching (approximately 30% of the total score)
- An explanatory callout banner distinguishes common skills from unit-specific
  skills, added after feedback that end users found the distinction confusing

### Manage Units
- Card-based layout — each unit displayed as a profile card rather than a flat
  table row, making the unit list scannable at a glance
- Add, edit, and delete units with vacancy caps
- Delete actions require confirmation before executing

### Matching Result
- Trigger the NLP matching pipeline as a non-blocking subprocess
- Three live stat cards: matching status, applicants assigned, and a live elapsed
  stopwatch that ticks while the engine runs
- Results table with a "View Resume" button per row — opens the applicant's resume
  PDF directly in a new browser tab for match verification
- Export results as CSV or Excel

---

## Key implementation details

### Non-blocking matching via thread + polling

The matching engine runs in a separate process so the UI stays responsive during
a run that can take 30 seconds to several minutes depending on hardware. A daemon
thread spawns the subprocess and stores the outcome in NiceGUI's shared app
storage. A `ui.timer` polls every 2 seconds, updates the status card, and cancels
itself when a result arrives.

### Table rendering fix (ag-grid → ui.table)

An earlier version used `ui.aggrid` for the data tables. This caused a WebSocket
timing race where row data arrived before the component had fully mounted,
resulting in blank tables despite correct data. Replacing all three tables with
NiceGUI's built-in `ui.table` resolved this — it renders synchronously without a
separate WebSocket channel.

### ZIP resume extraction

Resumes are submitted as a ZIP archive with inconsistent filename conventions
(e.g. `12345_John_Smith.pdf` or `Smith_J_00012345.pdf`). The extraction logic:
1. Strips all non-digit characters from each filename's UID segment
2. Removes leading zeros to produce a normalized key
3. Matches that key against the uploaded roster
4. Selects the most recently dated resume if a candidate has multiple files
5. Skips macOS resource fork files (`._*`) and nested archive artifacts silently

The heavy extraction work runs in a thread executor so the UI event loop is not
blocked while the ZIP is being processed.

### Brand color parameterization

Organization colors are defined as two constants at the top of the file
(`ORG_BLUE`, `ORG_GOLD`). Global CSS is injected once at startup from those
constants, covering sidebar background, active state, hover highlight, and step
progress indicators. Swapping an organization's brand colors requires changing
only those two lines.

---

## Design decisions and their rationale

Decisions from client feedback sessions and code review cycles are tagged inline
in the code with `[TEAM-LEADER]` and `[PROF-REVIEW]` so the reasoning is
traceable without needing to read meeting notes separately.

| Decision | Rationale |
|---|---|
| Sidebar navigation, no top tab bar | Team leader feedback — reduces cognitive load; keeps nav visible at all times |
| Live upload counters as stat cards | Praised as clearer than the previous inline text status label |
| Common Skills explanatory callout | End users confused common skills with unit-specific skills during review |
| Live elapsed stopwatch | Processing time varies by hardware; a timer signals the app is working, not frozen |
| Card layout for units | Makes unit profiles scannable; flagged as an improvement over flat table rows |
| Resume viewer per row | Endorsed as a valuable exception-handling tool for verifying individual matches |
| "Confirm" instead of "Next" | Makes step progression feel deliberate rather than decorative |
| Confirmation dialogs on delete | Prevents accidental data loss; specifically requested after a live demo |

---

## Dependencies

```
nicegui
pandas
openpyxl
```

The file also imports from `src/database/crud.py` (database read/write functions)
and `src/utils/filename_parser.py` (resume filename parsing). These are part of
the broader project pipeline and are not included in this repository.

---

## Running locally

```bash
pip install nicegui pandas openpyxl
python staffing_app.py
```

Open `http://127.0.0.1:8080` in your browser.

The app expects a `src/` directory with the database and matching pipeline modules.
Without those, the import at the top of the file will fail. See the root
`INSTALLATION.md` for full setup instructions.
