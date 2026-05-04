import re, time
from src.database import crud
from src.database.models import Department, MatchedRecord
from src.database.crud import create_or_update_matched_records_batch, read_common_skills, read_departments, save_normalized_skills_batch
from src.matching.processor import extract_skills_batch, get_skill_embeddings, run_hybrid_match, build_bm25_index, deduplicate_skills_sbert, rank_skills_bm25, filter_with_sbert, prime_common_skills_matcher

# Department Tier Definitions
# SPECIALISTS: Departments requiring domain-specific (anchor) skills for placement.
# GENERALISTS: Departments that accept a broader range of student profiles.
SPECIALISTS = {
    'INFORMATION SYSTEMS & OPERATIONS',
    'ITS',
    'FINANCE',
    'ACCOUNTING',
    'HEALTHCARE ADMINISTRATION',
    'CENTER FOR REAL ESTATE',
}
GENERALISTS = {
    "GRADUATE DEAN'S OFFICE",
    "UNDERGRADUATE DEAN'S OFFICE",
    'CENTER FOR PUBLIC POLICY',
    'MANAGEMENT DEPARTMENT',
    'INSTITUTE FOR PUBLIC SERVICE',
    'INTL STUDENT AFFAIRS',
    'CIVIC ENGAGEMENT CENTER',
    'STRATEGY & INTERNATIONAL BUSINESS',
    'CENTER FOR INNOVATION & CHANGE LEADERSHIP',
    'INTL ACADEMIC PARTNERSHIPS',
    'OFFICE OF GRADUATE ADMISSIONS',
}

def _norm_skill(v): return re.sub(r'[^a-z0-9 ]+', '', str(v or '').lower()).strip()
def _dept_name(d): return str(getattr(d, 'name', '') or '').strip()
def _dept_skills(d):
    sk = getattr(d, 'department_skills', None) or getattr(d, 'preferred_skills', None)
    return [str(s).strip() for s in (sk or []) if str(s).strip()]

def _dept_cap(d):
    """Requirement 10: Respects individual department student caps."""
    try:
        c = getattr(d, 'max_students', None)
        return int(c) if c is not None and int(c) > 0 else 3
    except: return 3

def get_all_departments():
    import os
    excluded_raw = os.getenv('SMS_EXCLUDED_DEPT_IDS', '').strip()
    excluded_ids = {int(x) for x in excluded_raw.split(',') if x.strip().isdigit()}

    """Requirement 5: Initializes only active departments from the DB."""
    rows = crud.read_departments()  # Now only returns is_active=1 rows
    return [Department(
        id=r.get('id'),
        name=r.get('name', ''),
        department_skills=r.get('department_skills') or [],
        is_participating=True,  # Active rows are participating by default
        max_students=r.get('max_students')
    ) for r in rows if r.get('id') not in excluded_ids]

def match_students_to_departments(students, departments=None, dept_embs=None, common_skills=None, common_vecs=None, return_metrics=False, strict_assign_all_valid=False, required_uids=None):
    """Requirement 9: The core SMS Matrix Scoring and Placement Engine."""
    metrics = {'match_seconds': 0.0}
    t_start = time.perf_counter()

    if departments is None: departments = get_all_departments()
    if common_skills is None:
        import os
        excluded_raw = os.getenv('SMS_EXCLUDED_SKILL_IDS', '').strip()
        excluded_ids = {int(x) for x in excluded_raw.split(',') if x.strip().isdigit()}
        common_skills = [
            r.get('skill_name', '') for r in read_common_skills()
            if r.get('id') not in excluded_ids
        ]

    # Requirement 9: Pre-compute Department Vectors
    if dept_embs is None:
        dept_embs = {_dept_name(d): get_skill_embeddings(_dept_skills(d)) for d in departments}

    # Prime the soft-skill PhraseMatcher once with the resolved common_skills list
    prime_common_skills_matcher(common_skills)

    assigned, assigned_map = set(), {}
    dept_counts = {_dept_name(d): 0 for d in departments}
    caps = {_dept_name(d): _dept_cap(d) for d in departments}
    common_set = {_norm_skill(s) for s in common_skills}

    # Requirement 6: Ensure skills are extracted from resumes
    ents = [s.skills if (s.skills and len(s.skills) > 0) else [] for s in students]
    missing = [i for i, s in enumerate(students) if not ents[i]]
    if missing:
        res = extract_skills_batch([students[i].resume_text for i in missing])
        for idx, r in enumerate(res): ents[missing[idx]] = r

    vecs = [get_skill_embeddings(e) for e in ents]

    # --- PRE-MATCH: Candidate DNA (Harmony Pipeline) ---
    # Deduplicates, quality-filters, and BM25-ranks each student's skills before the
    # scoring matrix. Does NOT modify ents or vecs, so department allocation math is unaffected.
    skills_to_persist = {}
    for i, student in enumerate(students):
        if not ents[i]:
            continue
        deduped = deduplicate_skills_sbert(ents[i], threshold=0.90)
        # Quality gate: discard noise terms that don't resemble real professional skills
        validated = filter_with_sbert(deduped, common_skills, threshold=0.60)
        ranked = rank_skills_bm25(validated, student.resume_text or '')
        student.normalized_skills = ranked
        skills_to_persist[student.student_id] = ranked
    if skills_to_persist:
        save_normalized_skills_batch(skills_to_persist)

    all_potential_matches = []

    # --- THE MATRIX: Requirement 9 (Score Calculation) ---
    for student, e, v in zip(students, ents, vecs):
        s_bm25 = build_bm25_index(e)

        # Requirement 8 & 9b: Static Common Skills Score
        _, _, c_score = run_hybrid_match(e, v, common_skills, common_vecs, threshold=0.65, bm25_index=s_bm25)

        # Requirement 9c/d: Static Experience and GPA Scores
        exp_score = max(0.0, min(1.0, float(student.experience or 0.0) / 5.0))
        gpa_score = max(0.0, min(1.0, float(student.gpa or 0.0) / 4.0))

        for dept in departments:
            if not getattr(dept, 'is_participating', True): continue

            # Requirement 9a: Departmental Matrix Match
            dname = _dept_name(dept)
            d_ex, d_sem, d_score = run_hybrid_match(e, v, _dept_skills(dept), dept_embs.get(dname), threshold=0.65, bm25_index=s_bm25)

            # Requirement 10: Specialist Anchor check
            anchors = sum(1 for s in d_ex if _norm_skill(s) not in common_set)
            anchors += sum(1 for s, score in d_sem.items() if score >= 0.75 and _norm_skill(s) not in common_set)

            # Requirement 9: Final Differentiated Score
            total_f_score = (0.40 * d_score) + (0.30 * c_score) + (0.25 * exp_score) + (0.05 * gpa_score)

            is_spec = any(t in dname.upper() for t in SPECIALISTS)
            is_gen = any(t in dname.upper() for t in GENERALISTS)
            if is_spec:
                if anchors >= 1: total_f_score *= 1.5  # Specialist Priority Boost
                else: total_f_score = 0.0              # Specialist Protection Kill-switch

            all_potential_matches.append({
                'score': total_f_score, 'student': student, 'dept': dept, 'is_spec': is_spec, 'is_gen': is_gen,
                'matched_skills': ", ".join(list(set(d_ex + list(d_sem.keys()))))
            })

    # Sort Matrix by highest scores
    all_potential_matches.sort(key=lambda x: x['score'], reverse=True)

    # --- PLACEMENT: Requirement 10 (Two-Phase Draft) ---
    records = []

    # Phase 1: Specialized Priority Draft
    for m in all_potential_matches:
        sid, dname = m['student'].student_id, _dept_name(m['dept'])
        if sid in assigned or not m['is_spec'] or dept_counts[dname] >= caps[dname] or m['score'] <= 0: continue
        records.append(build_match_record(m))
        assigned.add(sid); assigned_map[sid] = dname; dept_counts[dname] += 1

    # Phase 2: Generalist Draft
    for m in all_potential_matches:
        sid, dname = m['student'].student_id, _dept_name(m['dept'])
        if sid in assigned or not m['is_gen'] or dept_counts[dname] >= caps[dname]: continue
        records.append(build_match_record(m))
        assigned.add(sid); assigned_map[sid] = dname; dept_counts[dname] += 1

    # Phase 3: Open Fill to preserve prior assignment coverage
    for m in all_potential_matches:
        sid, dname = m['student'].student_id, _dept_name(m['dept'])
        if sid in assigned or dept_counts[dname] >= caps[dname]: continue
        records.append(build_match_record(m))
        assigned.add(sid); assigned_map[sid] = dname; dept_counts[dname] += 1

    # --- PHASE 4: Strict Fallback ---
    # Guarantees every required valid student is assigned. Uses non-specialist
    # departments first. Temporarily expands effective cap in-memory only --
    # never persists cap changes to the database.
    fallback_assigned_map: dict = {}
    pre_fallback_unassigned_uids: set = set()
    if strict_assign_all_valid:
        effective_required = required_uids if required_uids is not None else {s.student_id for s in students}
        unassigned_required = [s for s in students
                               if s.student_id in effective_required and s.student_id not in assigned]
        pre_fallback_unassigned_uids = {s.student_id for s in unassigned_required}

        if unassigned_required:
            print(f"[STRICT FALLBACK] {len(unassigned_required)} valid student(s) unassigned after 3 phases -- initiating fallback...")
            # Prefer non-specialist departments; fall back to all departments if none exist
            non_spec_depts = [d for d in departments
                              if not any(t in _dept_name(d).upper() for t in SPECIALISTS)]
            candidate_depts = non_spec_depts if non_spec_depts else list(departments)
            # In-memory effective caps -- never written to DB
            effective_caps = dict(caps)
            fallback_cap_expanded = 0
            for student in unassigned_required:
                best_dept = min(candidate_depts, key=lambda d: dept_counts.get(_dept_name(d), 0))
                dname = _dept_name(best_dept)
                expanded = False
                if dept_counts[dname] >= effective_caps[dname]:
                    effective_caps[dname] = dept_counts[dname] + 1
                    expanded = True
                    fallback_cap_expanded += 1
                reason = 'FORCE_ASSIGN_CAP_EXPANDED' if expanded else 'FORCE_ASSIGN_STRICT'
                fb_rec = {
                    'student': student, 'dept': best_dept, 'score': 0.0,
                    'is_spec': False, 'is_gen': False,
                    'matched_skills': f'(strict fallback: {reason})',
                }
                records.append(build_match_record(fb_rec))
                assigned.add(student.student_id)
                assigned_map[student.student_id] = dname
                fallback_assigned_map[student.student_id] = dname
                dept_counts[dname] += 1
                print(f"  [FALLBACK] {student.student_id} -> {dname} [{reason}]")
            metrics['fallback_assigned_count'] = len(fallback_assigned_map)
            metrics['fallback_cap_expanded_count'] = fallback_cap_expanded

    metrics['pre_fallback_unassigned_uids'] = pre_fallback_unassigned_uids
    metrics['fallback_assigned_map'] = fallback_assigned_map

    if records: create_or_update_matched_records_batch(records)
    metrics['match_seconds'] = time.perf_counter() - t_start
    return (assigned_map, metrics) if return_metrics else assigned_map

def build_match_record(m):
    student_obj = m['student']

    # 1. Create a combined name for the 'student_name' field
    full_name = f"{getattr(student_obj, 'first_name', '')} {getattr(student_obj, 'last_name', '')}".strip()

    # 2. Get the experience value (default to 0.0 if missing)
    exp_value = float(getattr(student_obj, 'experience', 0.0) or 0.0)

    # 3. Join student skills into a string
    student_skill_values = getattr(m['student'], 'normalized_skills', None) or getattr(m['student'], 'skills', None) or []

    return MatchedRecord(
        uid=student_obj.student_id,
        first_name=getattr(student_obj, 'first_name', ''),
        last_name=getattr(student_obj, 'last_name', ''),
        student_name=full_name,
        preferred_name=getattr(student_obj, 'preferred_name', ''),
        department_id=m['dept'].id,
        department=m['dept'].name,
        degree=getattr(student_obj, 'degree_program', ''),
        skills_matched=m['matched_skills'],
        student_skills=', '.join([str(skill).strip() for skill in student_skill_values if str(skill).strip()]),  # BM25-ranked order preserved
        gpa=float(getattr(student_obj, 'gpa', 0.0)),
        experience=exp_value,
        d_score=round(float(m.get('score', 0.0)), 6),
        semester_award=float(getattr(student_obj, 'semester_award', 0.0))
    )
