# GUI Contributions

**Benedict D. Santoso | nicegui_app_bds.py | ISOM 424 | Spring 2026**

---

## Overview

My primary contribution to this project was the NiceGUI frontend (`nicegui_app_bds.py`). This document summarizes the design decisions, features implemented, and bugs resolved.

---

## Design Approach

The UI was designed around an enterprise admin tool aesthetic:

- **Dark navy left sidebar** (`bg-gray-900`) with white content area for visual separation
- **Step breadcrumb navigation** displayed at the top of every page: `1. Upload Data → 2. Common Skills → 3. Manage Department → 4. Matching Result`
- Icons on all navigation items for scannability
- Suffolk University brand colors applied to primary actions (`#122e53` navy, `#b28917` gold)

Rationale: the client (Aki, Associate Director) is a non-technical administrator. The interface needed to feel professional and guide her linearly through the workflow without ambiguity about what step came next.

---

## Features Implemented

### Student Count Notification
After a successful roster upload, the app reads the row count from the Excel file and displays a green toast: `"There are X students participating."` This directly addressed the client request (Apr 7 meeting) for visibility into how many records were loaded before running the match.

**Location:** `view_upload()` in `nicegui_app_bds.py`

---

### Delete Confirmation Dialogs
Both the Common Skills page and the Manage Department page include confirmation dialogs before any deletion. Clicking Delete opens a popup: `"Are you sure you want to delete this [item]?"` with Yes and Cancel buttons. The delete only executes on explicit confirmation.

This pattern was requested directly by Aki after she expressed concern about accidental deletion of department configuration.

**Location:** `view_common()` and `view_department()`

---

### Working CSV Download
The Download CSV button in the results view triggers a real file download to the user's machine using `ui.download()`. The previous version of the button was present in the UI but wired to nothing.

**Location:** `view_result()` — `download_csv()` handler

---

### NaN to N/A Replacement
A `clean_row()` helper function was added to replace all `None` and float `NaN` values in the results table with the string `"N/A"` before display. This prevents raw "NaN" text from appearing in the client-facing results table.

This was a direct request from Aki (Apr 7 demo) after she flagged it during the live walkthrough.

**Location:** `clean_row()` helper, called in `refresh_matching_results()`

---

### Stipend → Award Column Rename
The `Stipend` column was renamed to `Award` throughout the results table and in all downloaded files (CSV and Excel). Per Aki's feedback: "Stipend" does not match Suffolk's financial aid terminology; "Award" does.

---

## Bug Resolved: ag-grid Blank Rows

**Root cause:** A race condition between `run_grid_method()` and `grid.update()` being called together at ag-grid mount time. The grid registered the correct row count (28 skills, 19 departments) but displayed blank rows because the WebSocket was not yet ready when the data was pushed.

**Attempted fixes:**
- `await asyncio.sleep(0.3)` before push
- `ui.timer(0, ..., once=True)` deferral
- `await ui.context.client.connected()` pattern

None resolved the blank row issue.

**Final solution:** Replaced all `ui.aggrid()` instances with NiceGUI's built-in `ui.table()`. The `ui.table` component has no mount timing dependency and renders rows immediately. All three data pages (Skills, Departments, Results) were migrated.

**Impact:** All tables now render rows on first load without any async workaround.

---

## Bug Resolved: ZIP File Producing Only 3 Results

**Root cause:** The dummy resume ZIP contained a `.cpgz` file — a macOS double-zip artifact created when Finder's "Compress" feature is applied to a folder that already contains a ZIP. The `.cpgz` was treated as a single file, leaving only 3 loose PDFs accessible to the extraction pipeline.

**Solution:** Re-zip the PDF files directly via Finder by selecting the individual PDFs and using Compress. This produces a clean ZIP without the `.cpgz` artifact.

---

## Apr 7 Client Meeting — Changes Applied

All of the following were confirmed during the live 23-minute Zoom demo with Aki (Associate Director):

| Feedback | Change Applied |
|---|---|
| Replace "NaN" with "N/A" for missing data | `clean_row()` helper added |
| Rename "Stipend" to "Award" | Column renamed in UI and exports |
| Student count visibility | Toast notification after upload |
| Delete confirmations to prevent accidents | Dialogs added to Skills and Departments pages |
