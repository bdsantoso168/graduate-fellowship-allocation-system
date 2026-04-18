"""
Staffing Allocation System — NiceGUI Frontend
============================================
Author: Benedict Santoso
Course context: Built as part of a semester-long consulting project in which a
student team designed and delivered an AI-powered staffing allocation system for a university
client. This file is the GUI layer of that system.

Technology stack:
  - NiceGUI  (Python-based reactive web UI framework)
  - Pandas   (roster and results data handling)
  - MySQL via custom CRUD layer  (src/database/crud.py)
  - subprocess call to src/main.py which runs the NLP matching pipeline
    (OCR + spaCy + BERT + weighted scoring: ~40% hard skills, ~30% common skills,
     ~25-30% degree/experience, ~5% GPA)

Key design decisions documented below were informed by:
  - Client feedback sessions with the end-user stakeholder (program administrator)
  - Team leader code reviews  (tagged [TEAM-LEADER] throughout)
  - Professor-led design review sessions  (tagged [PROF-REVIEW] throughout)

Portfolio note:
  All organization-specific branding (colors, logo path) is parameterized via constants below.
  No real student data, resume files, or database credentials are included in this repository.
  See sample_data/ for safe demo files and .gitignore for exclusion rules.

Usage:
  python nicegui_app_bds.py
  Then open http://127.0.0.1:8080
"""

from nicegui import ui, app
import asyncio
import pandas as pd
import os
import shutil
import subprocess
import threading
import zipfile
import re
from pathlib import Path
from src.utils.filename_parser import parse_filename
from src.database.crud import (
    create_department, read_departments, update_department, delete_department,
    create_common_skill, read_common_skills, update_common_skill, delete_common_skill,
    upsert_applicant_name, read_all_matched_applicants
)

# ─────────────────────────────────────────────────────────────────────────────
# Brand constants
# [TEAM-LEADER] Apply institution brand colors across the UI. Replace these hex
# values with your own institution's official color codes.
# [TEAM-LEADER] When the mouse cursor hovers over a sidebar tab, that tab should
# turn gold — implemented via injected CSS below.
# ─────────────────────────────────────────────────────────────────────────────
ORG_BLUE = '#122e53'   # Primary sidebar and heading color
ORG_GOLD = '#b28917'   # Accent / hover highlight color

ui.colors(primary=ORG_BLUE, secondary='#1e293b', accent=ORG_GOLD, positive='#2e7d32')

# Serve the static folder so the logo PNG can be referenced in the UI.
# [TEAM-LEADER] Add organization logo somewhere — upload image into the code.
# Place your organization logo at static/logo.png. The file is excluded from
# this repository; add your own before running.
app.add_static_files('/static', Path(__file__).parent / 'static')

PROJECT_ROOT = Path(__file__).parent


# ─────────────────────────────────────────────────────────────────────────────
# Global CSS injected once at startup
# ─────────────────────────────────────────────────────────────────────────────
ui.add_head_html(f"""
<style>
  /* [TEAM-LEADER] Gold hover on sidebar nav items */
  .nav-btn:hover {{ background-color: {ORG_GOLD} !important; border-radius: 6px; }}
  .nav-btn {{ transition: background-color 0.15s; border-radius: 6px; }}

  /* Active nav item */
  .nav-btn-active {{ background-color: {ORG_GOLD} !important; border-radius: 6px; }}

  /* Stat cards on Upload and Results pages */
  .stat-card {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; padding: 1rem; }}

  /* Department profile cards */
  .dept-card {{ background: white; border: 1px solid #e2e8f0; border-radius: 10px; padding: 1.25rem; transition: box-shadow 0.15s; }}
  .dept-card:hover {{ box-shadow: 0 2px 8px rgba(0,0,0,0.09); }}

  /* [PROF-REVIEW] Info callout used on the Common Skills page to distinguish
     common skills from department-specific skills — confusion flagged by the
     professor during the April 10 review session. */
  .info-callout {{ background: #e8f4fd; border-left: 4px solid #1976d2; border-radius: 0 6px 6px 0; padding: 0.75rem 1rem; }}

  /* Step progress connectors */
  .step-done   {{ color: #2e7d32; font-weight: 600; }}
  .step-active {{ color: white; background: {ORG_BLUE}; border-radius: 6px; padding: 2px 10px; font-weight: 700; }}
  .step-pending {{ color: #9ca3af; }}
</style>
""")


class StaffingAllocationApp:
    """
    Main application class for the Staffing Allocation System GUI.

    Manages all UI state and coordinates between:
      - File uploads (roster CSV/Excel and resume ZIP)
      - Database reads/writes via the CRUD layer
      - The NLP matching subprocess (src/main.py)
      - Real-time status updates displayed to the admin user

    Navigation model: single-page app with panel show/hide. All pages exist in
    the DOM; navigate() toggles visibility. This avoids full page reloads and
    keeps UI state (upload counters, matching timer) intact across tab switches.
    """

    # ─────────────────────────────────────────────────────────────────────────
    # Initialisation
    # ─────────────────────────────────────────────────────────────────────────

    def __init__(self):
        self.departments = []
        self.skills = []
        self.roster_df = None
        self.page_panels = {}

        # Grid references — set during build_ui, updated by refresh methods
        self.matching_grid = None
        self.dept_cards_container = None   # replaced table with card grid
        self.skills_grid = None

        # Status labels
        self.upload_status_label = None
        self.resume_status_label = None
        self.matching_status_label = None
        self.assigned_count_label = None

        # [TEAM-LEADER] The upload tracker showing student count and resume file
        # count dynamically updating was praised as a clear UX improvement over
        # the old inline text label ("✅ There are 97 students participating.").
        self.applicant_count = 0
        self.resume_count = 0
        self.applicant_count_label = None    # NiceGUI ref — updated by upload handler
        self.resume_count_label = None     # NiceGUI ref — updated by upload handler

        # [TEAM-LEADER] Add a run stopwatch so the admin can see how long
        # matching has been running. Processing time varies by hardware:
        # ~30 s on GPU, 2-3 min on RAM-only machines — not an app bug.
        self.elapsed_seconds = 0
        self.elapsed_timer = None
        self.elapsed_label = None

        # Sidebar button refs for active-state highlighting
        self._nav_buttons = {}

    # ─────────────────────────────────────────────────────────────────────────
    # Grid helper
    # ─────────────────────────────────────────────────────────────────────────

    def _push_to_grid(self, grid, rows: list):
        """
        Push rows to a NiceGUI table with a short delay.

        NiceGUI ag-grid tables occasionally receive row data before the DOM
        element is fully mounted. The 0.3 s delay is a workaround for that
        race condition. ui.timer(0, ..., once=True) runs the coroutine in the
        event loop without blocking the main thread.
        """
        async def _do():
            await asyncio.sleep(0.3)
            grid.rows = rows
            grid.update()
        ui.timer(0, _do, once=True)

    # ─────────────────────────────────────────────────────────────────────────
    # Data refresh methods
    # ─────────────────────────────────────────────────────────────────────────
    # Called on page navigation and after any write operation (add/edit/delete)
    # to keep displayed data in sync with the database.

    def refresh_matching_results(self):
        try:
            raw_data = read_all_matched_applicants()
            if not raw_data:
                if self.matching_grid:
                    self._push_to_grid(self.matching_grid, [])
                ui.notify("No matched results found.", type='warning')
                return
            df = pd.DataFrame(raw_data)
            df.drop(columns=["createdDateTime", "work_experience"], errors="ignore", inplace=True)

            # [PROF-REVIEW] Results table column order: UID, First Name, Last Name,
            # Department, Degree, Skills Matched, Score, GPA, Award — matching the
            # output format the client (program administrator) expects.
            df.rename(columns={
                "applicant_id":         "UID",
                "applicant_name":       "Applicant Name",
                "skills_matched":     "Skills Matched",
                "degree_program":     "Degree",
                "matched_unit": "Department",
                "gpa":                "GPA",
                "award_amount":     "Award",
            }, inplace=True)
            df = df.fillna('N/A').replace('nan', 'N/A').replace('NaN', 'N/A')
            rows = df.to_dict('records')
            if self.matching_grid:
                self._push_to_grid(self.matching_grid, rows)
            if self.assigned_count_label:
                self.assigned_count_label.set_text(str(len(rows)))
            ui.notify(f"Matching results loaded — {len(rows)} student(s).", type='positive')
        except Exception as e:
            ui.notify(f"Error loading matched students: {e}", type='negative')

    def refresh_departments(self):
        try:
            self.departments = read_departments()
            # Rebuild the card grid instead of pushing to a table
            if self.dept_cards_container:
                self._rebuild_dept_cards()
            ui.notify(f"Departments loaded — {len(self.departments)} total.", type='positive')
        except Exception as e:
            ui.notify(f"Error loading departments: {e}", type='negative')

    def _rebuild_dept_cards(self):
        """Re-render all department profile cards after any data change."""
        import json as _json

        def _list_str(val):
            if isinstance(val, list):
                return ", ".join(val)
            if isinstance(val, str):
                try:
                    parsed = _json.loads(val)
                    if isinstance(parsed, list):
                        return ", ".join(parsed)
                except Exception:
                    pass
            return val or "—"

        self.dept_cards_container.clear()
        with self.dept_cards_container:
            for dept in self.departments:
                # [TEAM-LEADER] Replace the plain table grid with card-based
                # department profiles — makes department info scannable at a
                # glance and matches the client's visual expectations.
                with ui.card().classes('dept-card w-full'):
                    with ui.row().classes('items-start justify-between w-full mb-1'):
                        with ui.column().classes('gap-0'):
                            ui.label(dept.get('name', '').upper()).classes('font-bold text-base')
                            ui.label('Department profile').classes('text-xs text-gray-400')
                        ui.badge('ACTIVE', color='green').classes('text-xs')

                    ui.separator().classes('my-2')

                    skills_str = _list_str(dept.get('department_skills'))
                    if skills_str and skills_str != '—':
                        ui.label('SKILLS').classes('text-xs font-bold text-gray-400 tracking-widest mt-1')
                        ui.label(skills_str).classes('text-sm text-gray-700 mb-1')

                    degrees_str = _list_str(dept.get('preferred_degrees'))
                    ui.label('PREFERRED DEGREES').classes('text-xs font-bold text-gray-400 tracking-widest mt-1')
                    ui.label(degrees_str if degrees_str else '—').classes('text-sm text-gray-700 mb-1')

                    cap = dept.get('max_students')
                    cap_txt = f"Vacancy Cap: {cap}" if cap else "Vacancy Cap: No limit"
                    with ui.row().classes('items-center gap-1 mt-1'):
                        ui.icon('people').classes('text-gray-400 text-sm')
                        ui.label(cap_txt).classes('text-sm text-gray-600')

                    with ui.row().classes('justify-end gap-2 mt-3'):
                        ui.button('Edit', icon='edit',
                                  on_click=lambda d=dept: self.edit_department_dialog(d)
                                  ).props('outline size=sm')
                        ui.button('Delete', icon='delete',
                                  on_click=lambda d=dept: self.delete_department_dialog(d)
                                  ).props('outline color=red size=sm')

    def refresh_skills(self):
        try:
            result = read_common_skills()
            if result is None:
                ui.notify("Could not read skills from database.", type='negative')
                return
            self.skills = result
            if self.skills_grid:
                cleaned = [{k: ('N/A' if v is None else v) for k, v in r.items()} for r in self.skills]
                self._push_to_grid(self.skills_grid, cleaned)
            ui.notify(f"Skills loaded — {len(self.skills)} total.", type='positive')
        except Exception as e:
            ui.notify(f"Error loading skills: {e}", type='negative')

    # ─────────────────────────────────────────────────────────────────────────
    # Department dialogs
    # ─────────────────────────────────────────────────────────────────────────

    def add_department_dialog(self):
        with ui.dialog() as dialog, ui.card().classes('min-w-96'):
            ui.label('Add Department').classes('text-xl font-bold mb-2')
            name_input = ui.input('Department Name').classes('w-full')
            dept_skills_input = ui.textarea('Department Skills (comma-separated)').classes('w-full')
            degrees_input = ui.textarea('Preferred Degrees (comma-separated)').classes('w-full')
            max_students_input = ui.number('Vacancy Cap (Max Students)', value=3, min=0).classes('w-full')

            def save():
                name = name_input.value.strip()
                if not name:
                    ui.notify("Name is required", type='negative')
                    return
                dept_skills_list = [s.strip() for s in dept_skills_input.value.split(',') if s.strip()]
                preferred_degrees_list = [s.strip() for s in degrees_input.value.split(',') if s.strip()]
                ms_val = str(max_students_input.value).strip()
                max_students_int = int(float(ms_val)) if ms_val else None
                try:
                    create_department(name, dept_skills_list, preferred_degrees_list, max_students_int)
                    ui.notify("Department added.", type='positive')
                    self.refresh_departments()
                    dialog.close()
                except Exception as e:
                    ui.notify(f"Error: {e}", type='negative')

            with ui.row().classes('w-full justify-end gap-2 mt-2'):
                ui.button('Cancel', on_click=dialog.close).props('flat')
                ui.button('Save', on_click=save).props('color=primary')
        dialog.open()

    def edit_department_dialog(self, row_data):
        if not row_data:
            ui.notify("Select a department first.", type='warning')
            return
        import json as _json

        def _to_display_str(val):
            if isinstance(val, list):
                return ", ".join(val)
            if isinstance(val, str):
                try:
                    parsed = _json.loads(val)
                    if isinstance(parsed, list):
                        return ", ".join(parsed)
                except Exception:
                    pass
            return val or ""

        with ui.dialog() as dialog, ui.card().classes('min-w-96'):
            ui.label(f'Edit: {row_data["name"]}').classes('text-xl font-bold mb-2')
            name_input = ui.input('Department Name', value=row_data['name']).classes('w-full')
            dept_skills_input = ui.textarea(
                'Department Skills', value=_to_display_str(row_data.get('department_skills', ''))
            ).classes('w-full')
            degrees_input = ui.textarea(
                'Preferred Degrees (comma-separated)',
                value=_to_display_str(row_data.get('preferred_degrees', ''))
            ).classes('w-full')
            max_students_input = ui.number(
                'Vacancy Cap (Max Students)', value=row_data.get('max_students', 3) or 3, min=0
            ).classes('w-full')

            def save():
                try:
                    dept_id = row_data['id']
                    dept_skills_list = [s.strip() for s in dept_skills_input.value.split(',') if s.strip()]
                    preferred_degrees_list = [s.strip() for s in degrees_input.value.split(',') if s.strip()]
                    ms_val = str(max_students_input.value).strip()
                    max_students_int = int(float(ms_val)) if ms_val else None
                    update_department(dept_id, name_input.value, dept_skills_list, preferred_degrees_list, max_students_int)
                    ui.notify("Department updated.", type='positive')
                    self.refresh_departments()
                    dialog.close()
                except Exception as e:
                    ui.notify(f"Error: {e}", type='negative')

            with ui.row().classes('w-full justify-end gap-2 mt-2'):
                ui.button('Cancel', on_click=dialog.close).props('flat')
                ui.button('Save', on_click=save).props('color=primary')
        dialog.open()

    def delete_department_dialog(self, row_data):
        if not row_data:
            ui.notify("Select a department first.", type='warning')
            return
        with ui.dialog() as dialog, ui.card().classes('min-w-80'):
            with ui.row().classes('items-center gap-2 mb-1'):
                ui.icon('warning').classes('text-red-600 text-2xl')
                ui.label('Confirm Deletion').classes('text-xl font-bold text-red-600')
            ui.label(f'Are you sure you want to delete "{row_data["name"]}"?').classes('text-sm mb-1')
            ui.label('The department will be removed for this session only.').classes('text-xs text-gray-500')

            def delete():
                try:
                    delete_department(row_data['id'])
                    ui.notify(f'"{row_data["name"]}" removed.', type='positive')
                    self.refresh_departments()
                    dialog.close()
                except Exception as e:
                    ui.notify(f"Error: {e}", type='negative')

            with ui.row().classes('w-full justify-end gap-2 mt-3'):
                ui.button('Cancel', on_click=dialog.close).props('flat')
                ui.button('Yes, Delete', on_click=delete).props('color=red')
        dialog.open()

    # ─────────────────────────────────────────────────────────────────────────
    # Skill dialogs
    # ─────────────────────────────────────────────────────────────────────────

    def add_skill_dialog(self):
        with ui.dialog() as dialog, ui.card().classes('min-w-80'):
            ui.label('Add Common Skill').classes('text-xl font-bold mb-2')
            name_input = ui.input('Skill Name').classes('w-full')

            def save():
                name = name_input.value.strip()
                if not name:
                    ui.notify("Skill name is required", type='negative')
                    return
                try:
                    create_common_skill(name)
                    ui.notify("Skill added.", type='positive')
                    self.refresh_skills()
                    dialog.close()
                except Exception as e:
                    ui.notify(f"Error: {e}", type='negative')

            with ui.row().classes('w-full justify-end gap-2 mt-2'):
                ui.button('Cancel', on_click=dialog.close).props('flat')
                ui.button('Save', on_click=save).props('color=primary')
        dialog.open()

    def edit_skill_dialog(self, row_data):
        if not row_data:
            ui.notify("Select a skill first.", type='warning')
            return
        with ui.dialog() as dialog, ui.card().classes('min-w-80'):
            ui.label('Edit Skill').classes('text-xl font-bold mb-2')
            name_input = ui.input('Skill Name', value=row_data['skill_name']).classes('w-full')

            def save():
                try:
                    update_common_skill(row_data['id'], name_input.value.strip())
                    ui.notify("Skill updated.", type='positive')
                    self.refresh_skills()
                    dialog.close()
                except Exception as e:
                    ui.notify(f"Error: {e}", type='negative')

            with ui.row().classes('w-full justify-end gap-2 mt-2'):
                ui.button('Cancel', on_click=dialog.close).props('flat')
                ui.button('Save', on_click=save).props('color=primary')
        dialog.open()

    def delete_skill_dialog(self, row_data):
        if not row_data:
            ui.notify("Select a skill first.", type='warning')
            return
        with ui.dialog() as dialog, ui.card().classes('min-w-80'):
            with ui.row().classes('items-center gap-2 mb-1'):
                ui.icon('warning').classes('text-red-600 text-2xl')
                ui.label('Confirm Deletion').classes('text-xl font-bold text-red-600')
            ui.label(f'Are you sure you want to delete "{row_data["skill_name"]}"?').classes('text-sm mb-1')
            ui.label('The skill will be removed for this session only.').classes('text-xs text-gray-500')

            def delete():
                try:
                    delete_common_skill(row_data['id'])
                    ui.notify(f'"{row_data["skill_name"]}" removed.', type='positive')
                    self.refresh_skills()
                    dialog.close()
                except Exception as e:
                    ui.notify(f"Error: {e}", type='negative')

            with ui.row().classes('w-full justify-end gap-2 mt-3'):
                ui.button('Cancel', on_click=dialog.close).props('flat')
                ui.button('Yes, Delete', on_click=delete).props('color=red')
        dialog.open()

    # ─────────────────────────────────────────────────────────────────────────
    # Upload logic
    # ─────────────────────────────────────────────────────────────────────────

    async def handle_student_upload(self, e):
        """
        Parse the uploaded CSV/Excel roster and update the live student counter.

        [TEAM-LEADER] Remove the old inline confirmation label ("✅ There are 97
        students participating.") — it duplicated the stat card above. Replace with
        a simple toast notification only.
        """
        try:
            filename = e.file.name
            content = await e.file.read()
            data_folder = Path("data")
            data_folder.mkdir(exist_ok=True)
            dest_path = data_folder / filename
            with open(dest_path, "wb") as f:
                f.write(content)
            if filename.endswith('.csv'):
                self.roster_df = pd.read_csv(dest_path)
            else:
                self.roster_df = pd.read_excel(dest_path)
            self.applicant_count = len(self.roster_df)
            if self.applicant_count_label:
                self.applicant_count_label.set_text(str(self.applicant_count))
            # Simple status update — no duplicate inline label
            self.upload_status_label.set_text("Roster uploaded successfully.")
            ui.notify(f"Roster loaded — {self.applicant_count} student(s) detected.", type='positive')
        except Exception as ex:
            ui.notify(f"Upload failed: {ex}", type='negative')
            self.upload_status_label.set_text(f"Upload error: {ex}")

    def clear_all_data(self):
        with ui.dialog() as dialog, ui.card().classes('min-w-80'):
            with ui.row().classes('items-center gap-2 mb-1'):
                ui.icon('warning').classes('text-red-600 text-2xl')
                ui.label('Clear All Data?').classes('text-xl font-bold text-red-600')
            ui.label('This will permanently delete all uploaded students and resumes.').classes('text-sm mb-1')

            async def confirm():
                try:
                    data_path = Path("data")
                    for file in data_path.glob("*"):
                        if file.name != "skill_taxonomy.json" and file.suffix in [".csv", ".xlsx"]:
                            file.unlink()
                    student_folder = data_path / "students"
                    if student_folder.exists():
                        shutil.rmtree(student_folder)
                    self.roster_df = None
                    self.applicant_count = 0
                    self.resume_count = 0
                    if self.applicant_count_label:
                        self.applicant_count_label.set_text("0")
                    if self.resume_count_label:
                        self.resume_count_label.set_text("0")
                    self.upload_status_label.set_text("No roster loaded.")
                    self.resume_status_label.set_text("No resumes loaded.")
                    ui.notify("All student data cleared.", type='positive')
                    dialog.close()
                except Exception as e:
                    ui.notify(f"Error clearing data: {e}", type='negative')

            with ui.row().classes('w-full justify-end gap-2 mt-3'):
                ui.button('Cancel', on_click=dialog.close).props('flat')
                ui.button('Yes, Clear All', on_click=confirm).props('color=red')
        dialog.open()

    async def handle_zip_upload(self, e):
        """
        Extract resume PDFs/DOCX from the uploaded ZIP and update the live counter.

        [TEAM-LEADER] Same as roster — replace the inline "✅ X resume(s) extracted"
        label with a toast notification only.
        """
        if self.roster_df is None:
            ui.notify("Please upload the applicant roster first!", type='warning')
            return
        filename = e.file.name
        content = await e.file.read()
        zip_path = Path("data/temp_resumes.zip")
        with open(zip_path, "wb") as f:
            f.write(content)
        self.resume_status_label.set_text("Processing ZIP file...")
        loop = asyncio.get_event_loop()
        try:
            saved_count = await loop.run_in_executor(None, self.process_resumes, zip_path)
            self.resume_count = saved_count
            if self.resume_count_label:
                self.resume_count_label.set_text(str(saved_count))
            self.resume_status_label.set_text("Resumes uploaded successfully.")
            ui.notify(f"{saved_count} resume(s) extracted and ready.", type='positive')
        except Exception as ex:
            self.resume_status_label.set_text(f"Error: {ex}")
            ui.notify(f"Resume processing error: {ex}", type='negative')

    def process_resumes(self, zip_path) -> int:
        """
        Extract PDF/DOCX resumes from a ZIP and save them to data/applicants/<UID>/.

        UID normalisation strategy:
          The roster CSV and resume filenames may encode UIDs differently
          (e.g. "UID010042146" vs "10042146"). Both are stripped to digits, then
          the canonical form is reconstructed by zero-padding to match the roster
          width. This prevents duplicate folders for the same student.

        Best-file selection:
          If a student has multiple resumes in the ZIP, the most recently dated
          file (parsed from the filename by src/utils/filename_parser.py) wins.

        [TEAM-LEADER] Processing speed is hardware-dependent — not an app bug.
        Machines without a dedicated GPU process resumes in 2-3 minutes;
        machines with GPU complete in ~30 seconds.
        """
        def norm_uid(val) -> str:
            digits = re.sub(r"\D+", "", str(val) if val is not None else "")
            return digits.lstrip("0") or "0"

        def canonical_uid(sheet_value: str, file_uid_digits: str) -> str:
            s = str(sheet_value or "").strip()
            sheet_digits = re.sub(r"\D+", "", s)
            width = len(file_uid_digits) if file_uid_digits else max(len(sheet_digits), 8)
            return "UID" + sheet_digits.zfill(width)

        UID_ALIASES = ["uid", "universal id", "student id", "id"]
        uid_col = None
        for col in self.roster_df.columns:
            if col.lower().strip() in UID_ALIASES:
                uid_col = col
                break
        if not uid_col:
            raise ValueError(f"Could not find UID column. Available: {list(self.roster_df.columns)}")

        uid_map = {}
        for u in self.roster_df[uid_col].astype(str).tolist():
            uid_map.setdefault(norm_uid(u), u)

        resume_base_dir = Path("data/applicants")
        saved_count = 0

        with zipfile.ZipFile(zip_path) as zip_ref:
            members = zip_ref.infolist()
            best_by_uid: dict = {}
            for member in members:
                try:
                    if member.is_dir():
                        continue
                    basename = Path(member.filename).name
                    if basename.startswith("._"):
                        continue
                    ext = Path(basename).suffix.lower()
                    if ext not in [".pdf", ".docx"]:
                        continue
                    info = parse_filename(basename)
                    if not info.ok or not info.uid:
                        continue
                    uid_norm = norm_uid(info.uid)
                    if uid_norm not in uid_map:
                        continue
                    prev = best_by_uid.get(uid_norm)
                    if (prev is None) or (prev[0].date and info.date and info.date > prev[0].date):
                        best_by_uid[uid_norm] = (info, member)
                except Exception as ex:
                    print(f"[process_resumes] scan error {member.filename}: {ex}")

            for uid_norm, (info, member) in best_by_uid.items():
                try:
                    canon_id = canonical_uid(uid_map[uid_norm], info.uid)
                    resume_folder = resume_base_dir / canon_id
                    resume_folder.mkdir(parents=True, exist_ok=True)
                    ext = Path(member.filename).suffix.lower()
                    out_path = resume_folder / f"applicant_resume{ext}"
                    with zip_ref.open(member) as source, open(out_path, "wb") as target:
                        shutil.copyfileobj(source, target)
                    saved_count += 1
                    full_name = (info.first_name or "").strip()
                    if info.last_name:
                        full_name = f"{full_name} {info.last_name}".strip()
                    if full_name:
                        upsert_applicant_name(applicant_id=canon_id, applicant_name=full_name)
                except Exception as ex:
                    print(f"[process_resumes] save error {member.filename}: {ex}")

        return saved_count

    # ─────────────────────────────────────────────────────────────────────────
    # Download helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _build_results_df(self):
        raw_data = read_all_matched_applicants()
        if not raw_data:
            return None
        df = pd.DataFrame(raw_data)
        df.drop(columns=["createdDateTime", "work_experience"], errors="ignore", inplace=True)
        df.rename(columns={
            "applicant_id":         "UID",
            "applicant_name":       "Applicant Name",
            "skills_matched":     "Skills Matched",
            "degree_program":     "Degree",
            "matched_unit": "Department",
            "gpa":                "GPA",
            "award_amount":     "Award",
        }, inplace=True)
        return df.fillna('N/A').replace('nan', 'N/A').replace('NaN', 'N/A')

    def download_csv(self):
        try:
            df = self._build_results_df()
            if df is None:
                ui.notify("No matched results to download.", type='warning')
                return
            ui.download(df.to_csv(index=False).encode('utf-8'), 'matching_results.csv')
        except Exception as e:
            ui.notify(f"CSV download error: {e}", type='negative')

    def download_excel(self):
        try:
            import io
            df = self._build_results_df()
            if df is None:
                ui.notify("No matched results to download.", type='warning')
                return
            buf = io.BytesIO()
            df.to_excel(buf, index=False)
            buf.seek(0)
            ui.download(buf.read(), 'matching_results.xlsx')
        except Exception as e:
            ui.notify(f"Excel download error: {e}", type='negative')

    # ─────────────────────────────────────────────────────────────────────────
    # Matching subprocess runner
    # ─────────────────────────────────────────────────────────────────────────

    def run_matching_process(self):
        """
        Spawn src/main.py as a subprocess so the NLP pipeline (OCR, spaCy, BERT)
        runs in a separate process without blocking the NiceGUI event loop.
        Result is communicated back via app.storage.general (NiceGUI shared state).
        A ui.timer polls every 2 seconds until the subprocess finishes.

        [TEAM-LEADER] Start the stopwatch here; stop it when matching completes or fails.
        [PROF-REVIEW] Resume preview opens from the results table — professor strongly
        endorsed this as a valuable exception-handling tool for reviewing match rationale.
        """
        resume_folder_exists = os.path.exists("data/applicants")
        has_excel_or_csv = any(Path("data").glob("*.xlsx")) or any(Path("data").glob("*.csv"))
        if not resume_folder_exists or not has_excel_or_csv:
            ui.notify("Please upload the applicant roster and resumes first.", type='warning')
            return

        # Update status card to "Running"
        if self.matching_status_label:
            self.matching_status_label.set_text("Running")
        if self.assigned_count_label:
            self.assigned_count_label.set_text("0")
        app.storage.general.pop('matching_result', None)

        # [TEAM-LEADER] Reset and start the elapsed stopwatch for this run.
        self.elapsed_seconds = 0
        if self.elapsed_timer:
            self.elapsed_timer.cancel()
        if self.elapsed_label:
            self.elapsed_label.set_text("00:00:00")

        def _tick():
            self.elapsed_seconds += 1
            if self.elapsed_label:
                h = self.elapsed_seconds // 3600
                m = (self.elapsed_seconds % 3600) // 60
                s = self.elapsed_seconds % 60
                self.elapsed_label.set_text(f"{h:02}:{m:02}:{s:02}")

        self.elapsed_timer = ui.timer(1.0, _tick)

        def process():
            try:
                result = subprocess.run(
                    ["python3", "-m", "src.main"],
                    capture_output=True, text=True, timeout=300,
                    cwd=str(PROJECT_ROOT)
                )
                if result.returncode != 0:
                    app.storage.general['matching_result'] = ('failed', result.stderr[:500])
                else:
                    app.storage.general['matching_result'] = ('ok', '')
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
            # Stop the stopwatch
            if self.elapsed_timer:
                self.elapsed_timer.cancel()
                self.elapsed_timer = None
            if status == 'ok':
                if self.matching_status_label:
                    self.matching_status_label.set_text("Completed")
                ui.notify("Matching completed successfully!", type='positive')
                self.refresh_matching_results()
            else:
                if self.matching_status_label:
                    self.matching_status_label.set_text("Failed")
                ui.notify(f"Matching failed: {msg}", type='negative')

        t = ui.timer(2.0, lambda: None)
        t.callback = lambda: poll_result(t)

    # ─────────────────────────────────────────────────────────────────────────
    # Resume viewer
    # ─────────────────────────────────────────────────────────────────────────

    def open_resume(self, applicant_uid: str):
        """
        Open the student's resume PDF in a new browser tab.

        [PROF-REVIEW] Resume preview feature was strongly endorsed by the professor
        as a valuable exception-handling tool — allows the admin to review the match
        rationale for a specific student without downloading the file separately.
        """
        resume_folder = Path("data/applicants") / applicant_uid
        for ext in [".pdf", ".docx"]:
            candidate = resume_folder / f"applicant_resume{ext}"
            if candidate.exists():
                ui.navigate.to(f"/static/resumes/{applicant_uid}/applicant_resume{ext}", new_tab=True)
                return
        ui.notify(f"Resume not found for {applicant_uid}.", type='warning')

    # ─────────────────────────────────────────────────────────────────────────
    # UI Layout
    # ─────────────────────────────────────────────────────────────────────────

    def build_ui(self):
        """
        Construct the entire application layout in a single call.

        Structure:
          - Left sidebar: logo, nav items, system status
          - Main content area: step progress bar + page panels

        Navigation is panel-based (show/hide) rather than page-based (reload).
        All panels are created once at startup; navigate() toggles visibility
        and triggers lazy data refresh for Skills, Departments, and Results.

        [TEAM-LEADER] Keep the side tab; remove the top tab bar entirely.
        [TEAM-LEADER] Add a Welcome page as the default landing view.
        [TEAM-LEADER] Rename all "Next" buttons to "Confirm".
        """

        STEPS = [
            ('upload',      'upload_file', 'Upload Data'),
            ('skills',      'school',      'Common Skills'),
            ('departments', 'domain',      'Manage Departments'),
            ('results',     'analytics',   'Matching Result'),
        ]

        # step_labels maps page key -> label widget for the progress bar
        step_labels = {}

        def navigate(page: str):
            """
            Toggle panel visibility and update active sidebar and progress bar state.
            Also triggers a lazy data refresh on first visit to data-heavy pages.
            """
            for name, panel in self.page_panels.items():
                panel.set_visibility(name == page)

            # Update progress bar labels
            step_keys = [s[0] for s in STEPS]
            current_idx = step_keys.index(page) if page in step_keys else -1
            for i, (p, lbl) in enumerate(step_labels.items()):
                if i < current_idx:
                    lbl.classes(replace='step-done px-2 py-1 text-sm cursor-pointer')
                elif i == current_idx:
                    lbl.classes(replace='step-active px-2 py-1 text-sm cursor-pointer')
                else:
                    lbl.classes(replace='step-pending px-2 py-1 text-sm cursor-pointer')

            # Update sidebar active button highlighting
            for p, btn in self._nav_buttons.items():
                if p == page:
                    btn.classes(add='nav-btn-active')
                else:
                    btn.classes(remove='nav-btn-active')

            # Lazy data refresh
            if page == 'skills':
                ui.timer(0, self.refresh_skills, once=True)
            elif page == 'departments':
                ui.timer(0, self.refresh_departments, once=True)
            elif page == 'results':
                ui.timer(0, self.refresh_matching_results, once=True)

        # ── Left sidebar ────────────────────────────────────────────────────
        # [TEAM-LEADER] Dark navy sidebar (ORG_BLUE) with white text.
        # Gold hover applied via injected CSS class .nav-btn:hover.
        with ui.left_drawer(fixed=True, bordered=False).style(
            f'background-color: {ORG_BLUE};'
        ).classes('flex flex-col justify-between'):

            with ui.column().classes('p-4 gap-1 w-full'):
                # [TEAM-LEADER] Add organization logo — place logo.png in static/
                with ui.row().classes('items-center justify-center w-full mb-2 mt-2'):
                    ui.image('/static/logo.png').style(
                        'height:56px; object-fit:contain; filter:brightness(0) invert(1);'
                    )

                ui.label('Graduate Matching').classes('text-base font-bold text-white text-center w-full')
                ui.label('Enterprise Admin').classes('text-xs text-center w-full mb-4').style('color:#94a3b8')

                ui.separator().style('background:#2d4a70; margin-bottom:8px')

                # Welcome is a special nav item (not in the STEPS workflow list)
                btn_welcome = (
                    ui.button('Welcome', icon='home', on_click=lambda: navigate('welcome'))
                    .classes('w-full justify-start text-white text-sm nav-btn nav-btn-active')
                    .props('flat no-caps align=left')
                )
                self._nav_buttons['welcome'] = btn_welcome

                for page_key, icon_name, label in STEPS:
                    btn = (
                        ui.button(label, icon=icon_name, on_click=lambda p=page_key: navigate(p))
                        .classes('w-full justify-start text-white text-sm nav-btn')
                        .props('flat no-caps align=left')
                    )
                    self._nav_buttons[page_key] = btn

            # System status at the bottom of the sidebar
            with ui.column().classes('p-4 w-full'):
                ui.separator().style('background:#2d4a70; margin-bottom:12px')
                ui.label('SYSTEM STATUS').classes('text-xs tracking-widest uppercase mb-1').style('color:#64748b')
                with ui.row().classes('items-center gap-1'):
                    ui.icon('circle').classes('text-green-400').style('font-size:10px')
                    ui.label('Database connected').classes('text-xs text-green-400')
                ui.label('Ready for enterprise workflow').classes('text-xs').style('color:#64748b')

        # ── Main content area ───────────────────────────────────────────────
        with ui.column().classes('p-6 w-full gap-0'):

            # Step progress bar
            # [TEAM-LEADER] Keep the step progress bar but give it meaningful
            # state: completed (green), current (navy), pending (gray).
            # [PROF-REVIEW] Professor reviewed Nazar's version which introduced
            # this progress tracker. He asked for screenshots to evaluate the
            # "common skills completed" checkbox logic further.
            with ui.row().classes(
                'items-center gap-1 mb-6 flex-wrap w-full rounded-lg px-4 py-2 border border-gray-100'
            ).style('background:#f8fafc'):
                for i, (page_key, _, label) in enumerate(STEPS):
                    lbl = ui.label(f"{i + 1}. {label}").classes(
                        'step-pending px-2 py-1 text-sm cursor-pointer'
                    )
                    lbl.on('click', lambda p=page_key: navigate(p))
                    step_labels[page_key] = lbl
                    if i < len(STEPS) - 1:
                        ui.icon('chevron_right').classes('text-gray-300 text-sm')

            # ── Welcome page ────────────────────────────────────────────────
            # [TEAM-LEADER] Add a welcome page with workflow overview so the
            # end user understands the process before starting.
            with ui.column().classes('w-full gap-6 items-center') as welcome_panel:
                with ui.column().classes('items-center gap-2 mt-4'):
                    ui.image('/static/logo.png').style('height:72px; object-fit:contain')
                    ui.label('Staffing Allocation System').classes('text-3xl font-bold text-center').style(
                        f'color:{ORG_BLUE}'
                    )
                    ui.label('Enterprise Admin Portal').classes('text-base text-gray-500 text-center')

                ui.label(
                    'This tool automates the placement of applicants into business units '
                    'by matching resumes, skills, and degree programs using an AI-powered matching engine.'
                ).classes('text-sm text-gray-600 text-center max-w-lg')

                ui.separator().classes('w-full max-w-2xl my-2')

                # 4-step workflow overview cards
                ui.label('How it works').classes('text-lg font-bold').style(f'color:{ORG_BLUE}')
                workflow_steps = [
                    ('upload_file', '1', 'Upload Data',
                     'Upload applicant roster (CSV/Excel) and resume ZIP archive'),
                    ('school',      '2', 'Common Skills',
                     'Review and confirm skills shared across all departments'),
                    ('domain',      '3', 'Manage Departments',
                     'Set department skills, preferred degrees, and vacancy caps'),
                    ('analytics',   '4', 'Matching Result',
                     'Run the algorithm and download assignment results'),
                ]
                with ui.row().classes('gap-4 flex-wrap justify-center w-full max-w-3xl'):
                    for icon_name, step_num, step_name, step_desc in workflow_steps:
                        with ui.card().classes('p-4 items-center text-center').style('min-width:160px; max-width:200px'):
                            with ui.row().classes('items-center justify-center w-8 h-8 rounded-full mb-2').style(
                                f'background:{ORG_BLUE}'
                            ):
                                ui.label(step_num).classes('text-white font-bold text-sm')
                            ui.icon(icon_name).classes('text-2xl').style(f'color:{ORG_GOLD}')
                            ui.label(step_name).classes('font-bold text-sm mt-1').style(f'color:{ORG_BLUE}')
                            ui.label(step_desc).classes('text-xs text-gray-500 mt-1')

                ui.button(
                    'Get Started', icon='arrow_forward',
                    on_click=lambda: navigate('upload')
                ).props('color=primary size=lg').classes('mt-2')

            self.page_panels['welcome'] = welcome_panel

            # ── Upload Data page ────────────────────────────────────────────
            with ui.column().classes('w-full gap-4') as upload_panel:
                with ui.row().classes('items-center gap-2 mb-1'):
                    ui.icon('upload_file').classes('text-3xl text-primary')
                    ui.label('Upload Data').classes('text-2xl font-bold')
                ui.label(
                    'Upload roster files and student resumes for the current matching session.'
                ).classes('text-gray-500 mb-2')

                # Live tracker cards
                # [TEAM-LEADER] The upload tracker showing student count and resume
                # count dynamically updating was praised as a clear UX improvement.
                with ui.row().classes('w-full gap-4 mb-2'):
                    with ui.card().classes('flex-1 p-4 border border-gray-200 shadow-sm'):
                        with ui.row().classes('items-center justify-between'):
                            ui.label('Applicants participating').classes('text-sm text-gray-500 font-medium')
                            ui.icon('group').classes('text-2xl').style(f'color:{ORG_BLUE}')
                        self.applicant_count_label = ui.label('0').classes('text-4xl font-bold mt-1').style(
                            f'color:{ORG_BLUE}'
                        )
                        ui.label('Detected from the uploaded roster').classes('text-xs text-gray-400 mt-1')

                    with ui.card().classes('flex-1 p-4 border border-gray-200 shadow-sm'):
                        with ui.row().classes('items-center justify-between'):
                            ui.label('Resume files uploaded').classes('text-sm text-gray-500 font-medium')
                            ui.icon('description').classes('text-2xl').style(f'color:{ORG_GOLD}')
                        self.resume_count_label = ui.label('0').classes('text-4xl font-bold mt-1').style(
                            f'color:{ORG_GOLD}'
                        )
                        ui.label('Extracted from ZIP archive').classes('text-xs text-gray-400 mt-1')

                # Clear data
                with ui.card().classes('w-full max-w-2xl p-4 border border-gray-200 shadow-sm'):
                    ui.label('1. Clear Old Data').classes('font-bold mb-1')
                    ui.label(
                        'Remove all existing students and resumes before starting a new cycle.'
                    ).classes('text-sm text-gray-600 mb-3')
                    ui.button('Clear All Data', on_click=self.clear_all_data, icon='delete').props('color=red')

                # Roster upload
                with ui.card().classes('w-full max-w-2xl p-4 border border-gray-200 shadow-sm'):
                    ui.label('2. Upload Applicant Roster (CSV / Excel)').classes('font-bold mb-1')
                    ui.upload(
                        on_upload=self.handle_student_upload,
                        label='Drop Excel/CSV here or click to browse',
                        auto_upload=True
                    ).classes('w-full')
                    # [TEAM-LEADER] Simple status text only — no duplicate counter label.
                    self.upload_status_label = ui.label('No roster loaded.').classes('text-gray-500 mt-2 text-sm')

                # Resume upload
                with ui.card().classes('w-full max-w-2xl p-4 border border-gray-200 shadow-sm'):
                    ui.label('3. Upload Applicant Resumes (ZIP)').classes('font-bold mb-1')
                    ui.label(
                        'Upload a ZIP containing PDF or DOCX resumes named with student UIDs.'
                    ).classes('text-xs text-gray-500 mb-2')
                    ui.upload(
                        on_upload=self.handle_zip_upload,
                        label='Drop ZIP here or click to browse',
                        auto_upload=True
                    ).classes('w-full')
                    self.resume_status_label = ui.label('No resumes loaded.').classes('text-gray-500 mt-2 text-sm')

                with ui.row().classes('mt-2'):
                    # [TEAM-LEADER] Rename "Next" to "Confirm" so the step bar
                    # has meaningful influence over workflow progression.
                    ui.button(
                        'Confirm & Continue', icon='arrow_forward',
                        on_click=lambda: navigate('skills')
                    ).props('color=primary')

            self.page_panels['upload'] = upload_panel

            # ── Common Skills page ──────────────────────────────────────────
            # [PROF-REVIEW] Professor questioned the distinction between common
            # skills and department skills from an end-user perspective. He
            # suggested the workflow should flow: upload data → confirm common
            # skills → review departments → run match → view results.
            # An explanatory callout banner is added to clarify the difference.
            with ui.column().classes('w-full gap-4') as skills_panel:
                with ui.row().classes('items-center gap-2 mb-1'):
                    ui.icon('school').classes('text-3xl text-primary')
                    ui.label('Common Skills').classes('text-2xl font-bold')

                # [PROF-REVIEW] Explanatory callout to prevent end-user confusion.
                with ui.row().classes('info-callout w-full max-w-3xl gap-3 items-start mb-2'):
                    ui.icon('info').classes('text-blue-700 mt-1').style('font-size:20px; flex-shrink:0')
                    with ui.column().classes('gap-1'):
                        ui.label('What are Common Skills?').classes('font-bold text-blue-900 text-sm')
                        ui.label(
                            'Common skills are baseline professional competencies evaluated for ALL '
                            'students regardless of which department they are matched to — such as '
                            'communication, teamwork, and MS Office. They account for approximately '
                            '30% of the matching score. Department-specific skills are managed '
                            'separately in the "Manage Departments" step.'
                        ).classes('text-sm text-blue-800')

                with ui.row().classes('items-center gap-2 mb-2'):
                    ui.button('Add Skill', on_click=self.add_skill_dialog, icon='add').props('color=primary')
                    ui.button('Refresh', on_click=self.refresh_skills, icon='refresh').props('flat')

                self.skills_grid = ui.table(
                    columns=[
                        {'name': 'id',         'label': 'ID',         'field': 'id',         'align': 'left'},
                        {'name': 'skill_name', 'label': 'Skill Name', 'field': 'skill_name', 'align': 'left'},
                    ],
                    rows=[],
                    row_key='id',
                    selection='single',
                ).classes('w-full')

                def edit_selected_skill():
                    row = self.skills_grid.selected[0] if self.skills_grid.selected else None
                    self.edit_skill_dialog(row) if row else ui.notify("Select a skill row first.", type='warning')

                def delete_selected_skill():
                    row = self.skills_grid.selected[0] if self.skills_grid.selected else None
                    self.delete_skill_dialog(row) if row else ui.notify("Select a skill row first.", type='warning')

                with ui.row().classes('items-center gap-2 mt-1'):
                    ui.label('Select a row to edit or delete').classes('text-gray-400 italic text-sm')
                    ui.button('Edit Selected', on_click=edit_selected_skill).props('outline')
                    ui.button('Delete Selected', on_click=delete_selected_skill).props('outline color=red')

                with ui.row().classes('mt-2 gap-2'):
                    ui.button('Back', icon='arrow_back', on_click=lambda: navigate('upload')).props('flat')
                    ui.button(
                        'Confirm & Continue to Departments', icon='arrow_forward',
                        on_click=lambda: navigate('departments')
                    ).props('color=primary')

            self.page_panels['skills'] = skills_panel

            # ── Manage Departments page ─────────────────────────────────────
            # [TEAM-LEADER] Replace the plain table grid with card-based department
            # profiles so the admin can scan all departments at a glance.
            with ui.column().classes('w-full gap-4') as dept_panel:
                with ui.row().classes('items-center justify-between w-full mb-1'):
                    with ui.row().classes('items-center gap-2'):
                        ui.icon('domain').classes('text-3xl text-primary')
                        ui.label('Manage Departments').classes('text-2xl font-bold')
                    ui.button(
                        'Add Department', icon='add', on_click=self.add_department_dialog
                    ).props('color=primary')

                ui.label(
                    'Add, edit, or remove departments and set vacancy caps before running matching.'
                ).classes('text-gray-500 mb-2')

                with ui.row().classes('items-center gap-2 mb-2'):
                    ui.button('Refresh', on_click=self.refresh_departments, icon='refresh').props('flat')

                # Department cards rendered here (rebuilt by _rebuild_dept_cards)
                self.dept_cards_container = ui.grid(columns=2).classes('w-full gap-4')

                with ui.row().classes('mt-2 gap-2'):
                    ui.button('Back', icon='arrow_back', on_click=lambda: navigate('skills')).props('flat')
                    ui.button(
                        'Confirm & Continue to Results', icon='arrow_forward',
                        on_click=lambda: navigate('results')
                    ).props('color=primary')

            self.page_panels['departments'] = dept_panel

            # ── Matching Results page ───────────────────────────────────────
            # [TEAM-LEADER] Add:
            #   1. Live elapsed stopwatch
            #   2. Three stat cards: Matching Status / Students Assigned / Time Elapsed
            #   3. "View Resume" button per row (open PDF in new tab)
            # [PROF-REVIEW] Resume preview strongly endorsed as a valuable
            # exception-handling tool for verifying individual match decisions.
            with ui.column().classes('w-full gap-4') as results_panel:
                with ui.row().classes('items-center gap-2 mb-1'):
                    ui.icon('analytics').classes('text-3xl text-primary')
                    ui.label('Matching Result').classes('text-2xl font-bold')
                ui.label(
                    'Run the matching engine, review assignments, and export client-ready outputs.'
                ).classes('text-gray-500 mb-2')

                # Control buttons
                # [TEAM-LEADER] Labeled text buttons preferred over icon-only for
                # clarity — debated in team review; no final consensus, so labeled
                # text was chosen to reduce ambiguity for the end user.
                with ui.row().classes('items-center gap-2 mb-3 flex-wrap'):
                    ui.button(
                        'Run Matching', icon='play_arrow', on_click=self.run_matching_process
                    ).props('color=primary')
                    ui.button(
                        'Download Excel', icon='download', on_click=self.download_excel
                    ).props('outline color=primary')
                    ui.button(
                        'Download CSV', icon='download', on_click=self.download_csv
                    ).props('outline color=primary')
                    ui.button(
                        'Clear Results', icon='delete_sweep',
                        on_click=lambda: (self._push_to_grid(self.matching_grid, []),
                                          ui.notify("Results cleared.", type='positive'))
                    ).props('outline color=red')

                # Three stat cards
                with ui.row().classes('w-full gap-4 mb-2'):
                    # Card 1: Matching status
                    with ui.card().classes('flex-1 p-4 border border-gray-200 shadow-sm'):
                        with ui.row().classes('items-center justify-between'):
                            ui.label('Matching status').classes('text-sm text-gray-500 font-medium')
                            ui.icon('settings').classes('text-2xl text-amber-500')
                        self.matching_status_label = ui.label('Ready').classes('text-xl font-bold mt-1 text-gray-700')
                        ui.label('Engine status for the current session').classes('text-xs text-gray-400 mt-1')

                    # Card 2: Students assigned
                    with ui.card().classes('flex-1 p-4 border border-gray-200 shadow-sm'):
                        with ui.row().classes('items-center justify-between'):
                            ui.label('Students assigned').classes('text-sm text-gray-500 font-medium')
                            ui.icon('person_check').classes('text-2xl text-green-500')
                        self.assigned_count_label = ui.label('0').classes('text-4xl font-bold mt-1 text-green-700')
                        ui.label('Assigned within current session roster').classes('text-xs text-gray-400 mt-1')

                    # Card 3: Time elapsed (live stopwatch)
                    # [TEAM-LEADER] Add the run stopwatch to the results page.
                    with ui.card().classes('flex-1 p-4 border border-gray-200 shadow-sm'):
                        with ui.row().classes('items-center justify-between'):
                            ui.label('Time elapsed').classes('text-sm text-gray-500 font-medium')
                            ui.icon('timer').classes('text-2xl text-amber-600')
                        self.elapsed_label = ui.label('00:00:00').classes('text-4xl font-bold mt-1 text-amber-700')
                        ui.label('Live timer for the current run').classes('text-xs text-gray-400 mt-1')

                # Results table with improved columns
                self.matching_grid = ui.table(
                    columns=[
                        {'name': 'UID',            'label': 'UID',            'field': 'UID',            'align': 'left'},
                        {'name': 'Applicant Name',   'label': 'Applicant Name',   'field': 'Applicant Name',   'align': 'left'},
                        {'name': 'Department',     'label': 'Department',     'field': 'Department',     'align': 'left'},
                        {'name': 'Degree',         'label': 'Degree',         'field': 'Degree',         'align': 'left'},
                        {'name': 'Skills Matched', 'label': 'Skills Matched', 'field': 'Skills Matched', 'align': 'left'},
                        {'name': 'GPA',            'label': 'GPA',            'field': 'GPA',            'align': 'left'},
                        {'name': 'Award',          'label': 'Award',          'field': 'Award',          'align': 'left'},
                    ],
                    rows=[],
                    row_key='UID',
                    pagination=20,
                ).classes('w-full')

                # [PROF-REVIEW] View Resume button per row — opens PDF in a new tab.
                self.matching_grid.add_slot('body-cell-UID', '''
                    <q-td :props="props">
                        {{ props.value }}
                        <q-btn flat dense size="xs" icon="open_in_new" color="primary"
                            class="q-ml-xs"
                            @click="$parent.$emit('view-resume', props.row)"
                            title="View Resume" />
                    </q-td>
                ''')
                self.matching_grid.on('view-resume', lambda e: self.open_resume(e.args.get('UID', '')))

                with ui.row().classes('mt-2 gap-2'):
                    ui.button('Back', icon='arrow_back', on_click=lambda: navigate('departments')).props('flat')

            self.page_panels['results'] = results_panel

        # Start on the Welcome page
        navigate('welcome')


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────
app_instance = StaffingAllocationApp()
app_instance.build_ui()

ui.run(title='Staffing Allocation System', port=8080, reload=True)
