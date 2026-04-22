# database/

MySQL schema for the staffing allocation system.

---

## Tables

| Table | Purpose |
|---|---|
| `applicants` | Core applicant record — stores profile data, extracted resume text, and ingestion status |
| `units` | Business units with skill requirements, preferred programs, and vacancy caps |
| `common_skills` | Shared skill pool evaluated across all applicants (~30% of matching score) |
| `matched_applicants` | Final output of each matching run — one record per applicant |
| `matching_batches` | Tracks upload sessions so results from different cycles can be archived independently |

---

## Key design decisions

**Ingestion-first architecture** — resume text and a SHA-256 file hash are cached directly on the `applicants` record. On subsequent runs the pipeline checks the hash first and skips re-extraction for unchanged files, cutting processing time on large batches.

**JSON columns for skills** — `unit_skills` and `preferred_programs` on the `units` table are stored as JSON arrays. This lets the admin add, edit, or remove skills via the UI without any schema changes.

**Vacancy cap per unit** — `max_applicants` on the `units` table enforces the allocation limit the admin sets before each matching cycle. The matching engine respects this cap during the multi-phase placement algorithm.

---

## Setup

```bash
mysql -u root -p < db_setup.sql
```

Applies to MySQL 8.0+. The script drops and recreates all tables on each run — intended for fresh setup only.

---

## Notes

Department names and institution identifiers have been generalized. All structural decisions, constraints, and seed data reflect the actual production schema.
