import json
from datetime import datetime
from src.database.config import get_connection

_MATCHED_STUDENTS_SCHEMA_READY = False
_D_SCORE_COLUMN_READY = False
_NORMALIZED_SKILLS_COLUMN_READY = False
_STUDENT_SKILLS_COLUMN_READY = False

# --- Session Management ---

def create_matching_batch(batch_name: str) -> int:
    """Requirement 10: Initializes a unique session for the draft."""
    conn = get_connection()
    if not conn: return 0
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO matching_batches (batch_name, status) VALUES (%s, %s)",
            (batch_name, 'IN-PROGRESS')
        )
        batch_id = cursor.lastrowid
        conn.commit()
        return batch_id
    finally:
        cursor.close()
        conn.close()

def clear_all_session_data():
    """Wipes the database for a fresh matching session."""
    conn = get_connection()
    if not conn: return
    cursor = conn.cursor()
    try:
        cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
        cursor.execute("DELETE FROM matched_students")
        cursor.execute("DELETE FROM students")
        cursor.execute("TRUNCATE TABLE matching_batches")
        cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
        conn.commit()
    finally:
        cursor.close()
        conn.close()

# --- Ingestion & Skill Cache ---

def upsert_student_ingestion_batch(payload_list: list):
    """Requirement 3: Saves full resume text and metadata in bulk."""
    if not payload_list: return
    conn = get_connection()
    if not conn: return
    cursor = conn.cursor()
    try:
        query = """
            INSERT INTO students (student_id, name, resume_text, file_hash, batch_id, extraction_status, extracted_at) 
            VALUES (%s, %s, %s, %s, %s, 'COMPLETED', %s)
            ON DUPLICATE KEY UPDATE 
                resume_text = VALUES(resume_text), 
                file_hash = VALUES(file_hash),
                batch_id = VALUES(batch_id), 
                extracted_at = VALUES(extracted_at)
        """
        now = datetime.now()
        final_payload = [(*item, now) for item in payload_list]
        cursor.executemany(query, final_payload)
        conn.commit()
    finally:
        cursor.close()
        conn.close()

def get_cached_student_record_map(student_ids: list):
    """High-speed fetch of student profiles for the Matrix calculation."""
    if not student_ids: return {}
    conn = get_connection()
    if not conn: return {}
    cursor = conn.cursor(dictionary=True)
    try:
        # Ensure normalized_skills column exists before selecting it
        _ensure_normalized_skills_column(conn)
        placeholders = ','.join(['%s'] * len(student_ids))
        query = f"SELECT student_id, resume_text, normalized_skills FROM students WHERE student_id IN ({placeholders})"
        cursor.execute(query, tuple(student_ids))
        rows = cursor.fetchall()
        return {
            r['student_id']: {
                'resume_text': r.get('resume_text') or '',
                'normalized_skills': json.loads(r['normalized_skills']) if r.get('normalized_skills') else [],
            } for r in rows
        }
    finally:
        cursor.close()
        conn.close()

# --- Departmental Data ---

def read_departments():
    """Requirement 5 & 10: Reads all departments and their technical caps."""
    conn = get_connection()
    if not conn: return []
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM departments ORDER BY name")
        rows = cursor.fetchall()
        for r in rows:
            r['department_skills'] = json.loads(r['department_skills']) if r['department_skills'] else []
            r['preferred_degrees'] = json.loads(r['preferred_degrees']) if r['preferred_degrees'] else []
        return rows
    finally:
        cursor.close()
        conn.close()

def read_common_skills():
    """Requirement 8: Fetches baseline skills for the non-differentiating score."""
    conn = get_connection()
    if not conn: return []
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT id, skill_name FROM common_skills ORDER BY skill_name")
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

# --- Student Candidate DNA ---

def _ensure_normalized_skills_column(conn):
    """Ensures the normalized_skills column exists on the students table."""
    global _NORMALIZED_SKILLS_COLUMN_READY
    if _NORMALIZED_SKILLS_COLUMN_READY: return
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'students' AND COLUMN_NAME = 'normalized_skills'"
        )
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE students ADD COLUMN normalized_skills MEDIUMTEXT NULL")
            conn.commit()
        _NORMALIZED_SKILLS_COLUMN_READY = True
    finally:
        cursor.close()

def save_normalized_skills_batch(skills_map: dict):
    """Persists BM25-ranked normalized_skills for multiple students in one batch write."""
    if not skills_map: return
    conn = get_connection()
    if not conn: return
    cursor = conn.cursor()
    try:
        _ensure_normalized_skills_column(conn)
        payload = [
            (json.dumps(skills), student_id)
            for student_id, skills in skills_map.items()
            if skills
        ]
        if payload:
            cursor.executemany(
                "UPDATE students SET normalized_skills = %s WHERE student_id = %s",
                payload
            )
            conn.commit()
    finally:
        cursor.close()
        conn.close()

# --- Matched Results Contract ---

def _ensure_student_skills_column(conn):
    """Guarantees student_skills column exists in matched_students. Called before every read and write."""
    global _STUDENT_SKILLS_COLUMN_READY
    if _STUDENT_SKILLS_COLUMN_READY: return
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'matched_students' AND COLUMN_NAME = 'student_skills'"
        )
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE matched_students ADD COLUMN student_skills TEXT NULL")
            conn.commit()
        _STUDENT_SKILLS_COLUMN_READY = True
    finally:
        cursor.close()

def _ensure_matched_students_schema(conn):
    """Safety logic to prevent 'Out of Range' errors for experience."""
    global _MATCHED_STUDENTS_SCHEMA_READY
    if _MATCHED_STUDENTS_SCHEMA_READY: return
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT NUMERIC_PRECISION FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'matched_students' AND COLUMN_NAME = 'work_experience'")
        row = cursor.fetchone() or {}
        if int(row.get('NUMERIC_PRECISION') or 0) < 5:
            cursor.execute("ALTER TABLE matched_students MODIFY COLUMN work_experience DECIMAL(5,2)")
            conn.commit()
        # Safety: add d_score column if it does not yet exist
        cursor.execute(
            "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'matched_students' AND COLUMN_NAME = 'd_score'"
        )
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE matched_students ADD COLUMN d_score FLOAT DEFAULT 0.0")
            conn.commit()
        # Safety: add student_skills column if it does not yet exist
        _ensure_student_skills_column(conn)
        _MATCHED_STUDENTS_SCHEMA_READY = True
    finally: cursor.close()

def _ensure_d_score_column(conn):
    """Guarantees d_score column exists in matched_students. Called before every read and write."""
    global _D_SCORE_COLUMN_READY
    if _D_SCORE_COLUMN_READY: return
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'matched_students' AND COLUMN_NAME = 'd_score'"
        )
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE matched_students ADD COLUMN d_score FLOAT DEFAULT 0.0")
            conn.commit()
        _D_SCORE_COLUMN_READY = True
    finally:
        cursor.close()

def create_or_update_matched_records_batch(matched_records):
    """Saves final matched results, adapting to available matched_students columns."""
    if not matched_records: return
    conn = get_connection()
    if not conn: return
    cursor = conn.cursor()
    try:
        _ensure_matched_students_schema(conn)
        _ensure_d_score_column(conn)

        info_cursor = conn.cursor(dictionary=True)
        try:
            info_cursor.execute("SHOW COLUMNS FROM matched_students")
            table_columns = {row['Field'] for row in info_cursor.fetchall()}
        finally:
            info_cursor.close()

        # Keep student_id first as the key; include only columns that exist.
        candidate_mappings = [
            ('student_id', lambda r: getattr(r, 'uid', '')),
            ('first_name', lambda r: getattr(r, 'first_name', '') or ''),
            ('last_name', lambda r: getattr(r, 'last_name', '') or ''),
            ('preferred_name', lambda r: getattr(r, 'preferred_name', '') or ''),
            ('matched_department', lambda r: getattr(r, 'department', '') or ''),
            ('degree_program', lambda r: getattr(r, 'degree', '') or ''),
            ('skills_matched', lambda r: getattr(r, 'skills_matched', '') or ''),
            ('student_skills', lambda r: getattr(r, 'student_skills', '') or ''),
            ('gpa', lambda r: getattr(r, 'gpa', 0) or 0),
            ('work_experience', lambda r: getattr(r, 'experience', 0) or 0),
            ('d_score', lambda r: getattr(r, 'd_score', 0.0) or 0.0),
            ('semester_award', lambda r: getattr(r, 'semester_award', 0) or 0),
            ('student_name', lambda r: getattr(r, 'student_name', '') or ''),
        ]

        active_mappings = [m for m in candidate_mappings if m[0] in table_columns]
        if not active_mappings:
            return

        active_columns = [name for name, _ in active_mappings]
        placeholders = ', '.join(['%s'] * len(active_columns))
        insert_columns = ', '.join(active_columns)

        update_columns = [c for c in active_columns if c != 'student_id']
        update_clause = ',\n                '.join(f'{c} = VALUES({c})' for c in update_columns)

        query = (
            f"INSERT INTO matched_students ({insert_columns})\n"
            f"            VALUES ({placeholders})"
        )
        if update_clause:
            query += f"\n            ON DUPLICATE KEY UPDATE\n                {update_clause}"

        payload = [
            tuple(extractor(r) for _, extractor in active_mappings)
            for r in matched_records
        ]

        cursor.executemany(query, payload)
        conn.commit()
    finally:
        cursor.close()
        conn.close()
        
def read_all_matched_students():
    conn = get_connection()
    if not conn: return []
    _ensure_d_score_column(conn)
    _ensure_student_skills_column(conn)
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SHOW COLUMNS FROM matched_students")
        table_columns = {row['Field'] for row in cursor.fetchall()}

        if 'student_id' not in table_columns:
            return []

        first_name_expr = (
            'first_name'
            if 'first_name' in table_columns
            else (
                "TRIM(SUBSTRING_INDEX(COALESCE(student_name, ''), ' ', 1))"
                if 'student_name' in table_columns
                else "''"
            )
        )
        last_name_expr = (
            'last_name'
            if 'last_name' in table_columns
            else (
                "TRIM(SUBSTRING(COALESCE(student_name, ''), LENGTH(SUBSTRING_INDEX(COALESCE(student_name, ''), ' ', 1)) + 1))"
                if 'student_name' in table_columns
                else "''"
            )
        )
        dept_expr = 'matched_department' if 'matched_department' in table_columns else "''"
        degree_expr = 'degree_program' if 'degree_program' in table_columns else "''"
        skills_expr = 'skills_matched' if 'skills_matched' in table_columns else "''"
        student_skills_expr = 'student_skills' if 'student_skills' in table_columns else "''"
        gpa_expr = 'gpa' if 'gpa' in table_columns else '0'
        stipend_expr = 'semester_award' if 'semester_award' in table_columns else '0'
        d_score_expr = 'd_score' if 'd_score' in table_columns else '0'

        query = f"""
            SELECT
                student_id AS `Stud_Id`,
                {first_name_expr} AS `First Name`,
                {last_name_expr} AS `Last Name`,
                {dept_expr} AS `Dept_Name/Bus_Unit`,
                {degree_expr} AS `Degree`,
                {skills_expr} AS `Skills matched`,
                {student_skills_expr} AS `Student Skills`,
                {gpa_expr} AS `GPA`,
                {stipend_expr} AS `Stipend`,
                {d_score_expr} AS `d_score`
            FROM matched_students
            ORDER BY {dept_expr}, student_id
        """
        cursor.execute(query)
        return cursor.fetchall()
    except Exception as error:
        print(f'[CRUD] read_all_matched_students error: {error}')
        return []
    finally:
        cursor.close()
        conn.close()

# --- Department Management ---

def create_department(name: str, department_skills: list, preferred_degrees: list, max_students: int = None):
    """Creates a new department with skills and degree preferences."""
    conn = get_connection()
    if not conn: return
    cursor = conn.cursor()
    try:
        skills_json = json.dumps(department_skills) if department_skills else json.dumps([])
        degrees_json = json.dumps(preferred_degrees) if preferred_degrees else None
        cursor.execute(
            "INSERT INTO departments (name, department_skills, preferred_degrees, max_students) VALUES (%s, %s, %s, %s)",
            (name, skills_json, degrees_json, max_students)
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()

def update_department(department_id: int, name: str, department_skills: list, preferred_degrees: list, max_students: int = None):
    """Updates an existing department."""
    conn = get_connection()
    if not conn: return
    cursor = conn.cursor()
    try:
        skills_json = json.dumps(department_skills) if department_skills else json.dumps([])
        degrees_json = json.dumps(preferred_degrees) if preferred_degrees else None
        cursor.execute(
            "UPDATE departments SET name = %s, department_skills = %s, preferred_degrees = %s, max_students = %s WHERE id = %s",
            (name, skills_json, degrees_json, max_students, department_id)
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()

def delete_department(department_id: int):
    """Deletes a department by ID."""
    conn = get_connection()
    if not conn: return
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE departments SET is_active = 0 WHERE id = %s", (department_id,))
        conn.commit()
    finally:
        cursor.close()
        conn.close()

# --- Common Skills Management ---

def create_common_skill(skill_name: str):
    """Creates a new common skill."""
    conn = get_connection()
    if not conn: return
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO common_skills (skill_name) VALUES (%s)", (skill_name,))
        conn.commit()
    finally:
        cursor.close()
        conn.close()

def update_common_skill(skill_id: int, skill_name: str):
    """Updates an existing common skill."""
    conn = get_connection()
    if not conn: return
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE common_skills SET skill_name = %s WHERE id = %s", (skill_name, skill_id))
        conn.commit()
    finally:
        cursor.close()
        conn.close()

def delete_common_skill(skill_id: int):
    """Deletes a common skill by ID."""
    conn = get_connection()
    if not conn: return
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM common_skills WHERE id = %s", (skill_id,))
        conn.commit()
    finally:
        cursor.close()
        conn.close()

# --- Student Management ---

def upsert_student_name(student_id: str, name: str):
    """Updates a student's name if they exist, or creates a stub record."""
    conn = get_connection()
    if not conn: return
    cursor = conn.cursor()
    try:
        # Try to update first
        cursor.execute(
            "UPDATE students SET name = %s, name_source = 'resume_filename' WHERE student_id = %s",
            (name, student_id)
        )
        if cursor.rowcount == 0:
            # If no update occurred, insert a stub record
            cursor.execute(
                "INSERT INTO students (student_id, name, name_source) VALUES (%s, %s, %s)",
                (student_id, name, 'resume_filename')
            )
        conn.commit()
    finally:
        cursor.close()
        conn.close()