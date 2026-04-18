# Staffing Allocation System

**14-week consulting practicum — Python · NiceGUI · MySQL · spaCy · SBERT**

> A faculty-supervised consulting project to replace a fully manual staffing allocation process with a production-ready automated matching platform. The system went from a fragile prototype to a server-deployed enterprise tool in one semester.

![Graduate Fellowship Allocation System thumbnail](https://github.com/user-attachments/assets/d3d82c4d-6ee9-4c84-9763-8c85a7ae1fc9)

---

## The Problem

The client's staffing team spent **40–50 hours per allocation cycle** manually reviewing resumes and placing candidates into business units — and still only hit **50–60% match accuracy**. The root causes were non-standardized resume formats, subjective judgment, and a previous prototype that was too unstable to trust.

Our team was brought in to rebuild it properly.

---

## What I Built

I was the **UI lead and frontend developer**. My responsibilities covered:

- Migrating the frontend from Streamlit to NiceGUI after Streamlit's session lockout and performance issues made it unviable for the client demo
- Building out the full 4-step workflow UI: Upload > Skills > Departments > Matching Results
- Integrating the frontend with the backend matching pipeline via a subprocess + polling pattern
- Implementing all client feedback from the live demo into the working codebase within 48 hours

---

## The UI Migration Story

The original system was built on **Streamlit**. About halfway through the semester, we hit a wall:

- Sessions would lock out if two people opened the app simultaneously
- Page reloads reset in-progress work
- The layout was too rigid for what the client actually needed

We pivoted to **NiceGUI** — a Python-native framework that gives you reactive components without leaving Python. I rebuilt the entire UI from scratch over a weekend.

### What the interface looks like

The app has a dark sidebar (enterprise admin style) and a step-based breadcrumb that enforces the correct user workflow:

```
1. Upload Data  →  2. Common Skills  →  3. Manage Department  →  4. Matching Result
```

Each step auto-loads data from the database when navigated to, using a `ui.timer(0, ..., once=True)` pattern to avoid calling database operations before the component is mounted.

```python
def navigate(page: str):
    for name, panel in self.page_panels.items():
        panel.set_visibility(name == page)
    for p, lbl in step_labels.items():
        if p == page:
            lbl.classes(replace='text-white bg-primary rounded px-3 py-1 text-sm font-bold cursor-pointer')
        else:
            lbl.classes(replace='text-gray-400 px-3 py-1 text-sm cursor-pointer')
    # Auto-load after a tick so the table component is fully mounted
    if page == 'skills':
        ui.timer(0, self.refresh_skills, once=True)
    elif page == 'departments':
        ui.timer(0, self.refresh_departments, once=True)
    elif page == 'results':
        ui.timer(0, self.refresh_matching_results, once=True)
```

---

## The ag-grid Bug (and How I Fixed It)

After the migration, all three data pages (Skills, Departments, Results) rendered with correct toast counts — the right number of rows — but the table body was **completely blank**.

I spent a few hours on it. Here is what I tried and what actually worked.

**What failed:**
```python
# Attempt 1: async sleep before pushing data
async def _push_to_grid(self, grid, rows):
    await asyncio.sleep(0.3)
    grid.options['rowData'] = rows
    grid.update()

# Attempt 2: wait for client connection
await ui.context.client.connected()
grid.options['rowData'] = rows
grid.update()
```

The issue was a **WebSocket timing race condition** in `ui.aggrid`. The component was rendering in the browser before it had fully established its WebSocket channel back to the Python server — so `grid.update()` was firing into a void.

**What actually worked:**

Dropped `ui.aggrid` entirely. Switched to NiceGUI's built-in `ui.table`, which renders synchronously without a WebSocket channel dependency:

```python
def _push_to_grid(self, grid, rows: list):
    async def _do():
        await asyncio.sleep(0.3)
        grid.rows = rows
        grid.update()
    ui.timer(0, _do, once=True)
```

```python
# Before: ui.aggrid (blank rows)
self.skills_grid = ui.aggrid({
    'columnDefs': [...],
    'rowData': [],
})

# After: ui.table (immediate render, no timing issue)
self.skills_grid = ui.table(
    columns=[
        {'name': 'id', 'label': 'ID', 'field': 'id', 'align': 'left'},
        {'name': 'skill_name', 'label': 'Skill Name', 'field': 'skill_name', 'align': 'left'},
    ],
    rows=[],
    row_key='id',
    selection='single',
).classes('w-full')
```

All three pages rendered rows immediately after the swap.

---

## Async File Upload with ZIP Parsing

One of the trickier pieces was handling resume uploads. Candidates submitted resumes as a ZIP archive, and the filenames contained the candidate ID and sometimes their name — but in inconsistent formats (e.g., `12345_John_Smith_Resume_2024.pdf`, `Smith_J_00012345.pdf`).

The upload flow:
1. Accept the ZIP asynchronously (NiceGUI's `ui.upload` gives you an async handler)
2. Run the heavy CPU work (unzipping + filename parsing) in a thread executor so the UI stays responsive
3. Match each file against the uploaded roster using a UID normalization function
4. Save the best resume per candidate (by date if multiple exist)

```python
async def handle_zip_upload(self, e):
    if self.applicant_df is None:
        ui.notify("Please upload the roster first!", type='warning')
        return
    content = await e.file.read()
    zip_path = Path("data/temp_resumes.zip")
    with open(zip_path, "wb") as f:
        f.write(content)
    self.resume_status_label.set_text("Processing ZIP file...")
    loop = asyncio.get_event_loop()
    try:
        saved_count = await loop.run_in_executor(None, self.process_resumes, zip_path)
        ui.notify(f"{saved_count} resume(s) extracted and ready.", type='positive')
    except Exception as ex:
        ui.notify(f"Resume processing error: {ex}", type='negative')
```

The UID normalization strips all non-digit characters and zero-pads to a canonical format, so `00012345`, `12345`, and `UID12345` all resolve to the same candidate:

```python
def norm_uid(val) -> str:
    digits = re.sub(r"\D+", "", str(val) if val is not None else "")
    return digits.lstrip("0") or "0"

def canonical_uid(sheet_value: str, file_uid_digits: str) -> str:
    s = str(sheet_value or "").strip()
    sheet_digits = re.sub(r"\D+", "", s)
    width = len(file_uid_digits) if file_uid_digits else max(len(sheet_digits), 8)
    return "UID" + sheet_digits.zfill(width)
```

---

## Running the Matching Engine (Non-Blocking)

The matching process itself is handled by the backend team's Python module. My job on the UI side was to trigger it and give the user real-time feedback without freezing the interface.

The pattern I used: run the subprocess in a daemon thread, store the result in `app.storage.general` (NiceGUI's shared state), and poll it from a `ui.timer` every 2 seconds:

```python
def run_matching_process(self):
    self.matching_status_label.set_text("Running...")
    self.matching_status_label.classes(replace='text-blue-600 font-bold')

    def process():
        try:
            result = subprocess.run(
                ["python3", "-m", "src.main"],
                capture_output=True, text=True, timeout=300,
                cwd=str(PROJECT_ROOT)
            )
            status = 'ok' if result.returncode == 0 else 'failed'
            app.storage.general['matching_result'] = (status, result.stderr[:500])
        except Exception as e:
            app.storage.general['matching_result'] = ('failed', str(e))

    threading.Thread(target=process, daemon=True).start()

    def poll_result(timer: ui.timer):
        outcome = app.storage.general.get('matching_result')
        if outcome is None:
            return
        status, msg = outcome
        app.storage.general.pop('matching_result', None)
        timer.cancel()
        if status == 'ok':
            self.matching_status_label.set_text("Completed")
            self.matching_status_label.classes(replace='text-green-600 font-bold')
            self.refresh_matching_results()
        else:
            self.matching_status_label.set_text("Failed")
            self.matching_status_label.classes(replace='text-red-600 font-bold')
            ui.notify(f"Matching failed: {msg}", type='negative')

    t = ui.timer(2.0, lambda: None)
    t.callback = lambda: poll_result(t)
```

---

## Results Export

After matching completes, the results table can be exported as CSV or Excel. The key data cleaning step — replacing `NaN` and `None` values with `'N/A'` — happens in a shared helper to keep both export paths consistent:

```python
def _build_results_df(self):
    raw_data = read_all_matched_results()
    if not raw_data:
        return None
    df = pd.DataFrame(raw_data)
    df.drop(columns=["createdDateTime", "tenure"], errors="ignore", inplace=True)
    df.rename(columns={
        "applicant_id": "ID",
        "applicant_name": "Name",
        "skills_matched": "Skills",
        "program": "Program",
        "matched_unit": "Matched Unit",
        "gpa": "GPA",
        "award_amount": "Award",
    }, inplace=True)
    df = df.fillna('N/A')
    df = df.replace('nan', 'N/A').replace('NaN', 'N/A')
    return df

def download_csv(self):
    df = self._build_results_df()
    if df is None:
        ui.notify("No results to download.", type='warning')
        return
    ui.download(df.to_csv(index=False).encode('utf-8'), 'matching_results.csv')

def download_excel(self):
    import io
    df = self._build_results_df()
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    buf.seek(0)
    ui.download(buf.read(), 'matching_results.xlsx')
```

---

## The Mac ZIP Bug

During testing we found that matching only returned 3 results despite uploading 79 resumes. After some digging I traced it to a Mac filesystem artifact.

When you compress a `.zip` on a Mac using Finder's "Compress" on a folder, macOS sometimes creates a `.cpgz` file instead of a flat ZIP — or embeds a nested archive artifact inside the ZIP. The app was seeing a mostly-empty archive with only 3 loose PDFs at the root.

Fix: re-zip the files by selecting all the PDFs directly in Finder (not the enclosing folder) and compressing that selection. The resulting ZIP had all 79 files at the root level and matching ran correctly.

Not a code change, but worth documenting because it cost a few hours.

---

## Matching Algorithm (Backend — not my code, but I documented it)

For context on what the UI is wrapping:

```
Final Score =
    (0.40 × Unit Skill Match)     ← BM25 10% + SBERT semantic 90%
  + (0.30 × Common Skill Match)
  + (0.25 × Work Experience)      ← normalized 0–1, capped at 5 years
  + (0.05 × GPA)                  ← out of 4.0

Tiebreaker (4 levels):
  1. Highest total score
  2. Highest unit skill score
  3. Applicant ID (ascending)
  4. Unit name (ascending)

Allocation: multi-phase (Specialist → Generalist → Overflow → Fallback)
Each applicant placed in exactly one unit. Once assigned, blocked from all phases.
```

---

## Tech Stack

| Layer | Tool |
|---|---|
| UI | NiceGUI |
| Language | Python 3 |
| Skill Extraction | spaCy + SkillNER |
| Matching | BM25 + SBERT (sentence-transformers) |
| OCR Fallback | PyMuPDF + PyTesseract |
| Database | MySQL |
| Data handling | pandas |
| Hosting | Linux server (university-managed) |

---

## Repository Scope

This repository contains **documentation, architecture notes, and anonymized code excerpts** only.

The live system runs within a secure institutional environment. Real applicant data, credentials, and internal identifiers are not stored here. All variable names and domain references in this README have been generalized from the production codebase.

This project was conducted under a signed NDA with the client.
