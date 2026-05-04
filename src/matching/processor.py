import os, re, time, math
from collections import Counter, defaultdict
import spacy, torch
from sentence_transformers import SentenceTransformer, util
from rank_bm25 import BM25Okapi

# SkillNer Imports for Requirements 6 & 7
try:
    from spacy.matcher import PhraseMatcher
    from skillNer.general_params import SKILL_DB
    from skillNer.skill_extractor_class import SkillExtractor
except ImportError:
    SkillExtractor = None
    PhraseMatcher = None

# Global Model Initialization
nlp = None
skill_extractor = None
sbert_model = None
device = 'cuda' if torch.cuda.is_available() else 'cpu'

# --- Quality Filter Constants ---
SKILL_NOISE_BLACKLIST = {
    'professional', 'skills', 'experience', 'summary', 'details', 'resume',
    'education', 'work', 'history', 'objective', 'references', 'profile',
    'achievements', 'activities', 'interest', 'interests', 'languages',
    'certifications', 'projects', 'awards', 'honors', 'publications',
    'contact', 'address', 'email', 'phone', 'linkedin', 'github',
    'university', 'college', 'school', 'degree', 'bachelor', 'master',
    'gpa', 'grade', 'cgpa', 'year', 'years', 'month', 'months',
    'jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep',
    'oct', 'nov', 'dec', 'january', 'february', 'march', 'april',
    'june', 'july', 'august', 'september', 'october', 'november', 'december',
    'present', 'current', 'ongoing', 'team', 'company', 'organization',
    'department', 'section', 'list', 'include', 'including', 'use', 'used',
    'develop', 'developed', 'manage', 'managed', 'assist', 'support',
}
_FORBIDDEN_NER_LABELS = {'GPE', 'PERSON', 'DATE', 'CARDINAL', 'ORDINAL', 'FAC', 'LOC', 'NORP'}
_skill_db_reference_embs = None  # Cached SKILL_DB embeddings for filter_with_sbert
_common_phrase_matcher = None    # Cached PhraseMatcher for soft/common skill detection

# Post-extraction clump-washer constants
# Suffix words that commonly get fused to skill names during PDF extraction
_CLUMP_SPLIT_SUFFIXES = [
    'skills', 'skill', 'experience', 'management', 'development',
    'communication', 'leadership', 'analysis', 'interpersonal',
    'professional', 'technical', 'responsibilities', 'knowledge', 'teamwork',
    'and', 'or', 'with', 'in', 'to', 'for', 'the',
]
# Trailing joiners to strip when they dangle at the end after splitting
_TRAILING_JOINERS_RE = re.compile(r'\s+(and|or|with|in|to|for|the|of|a)\s*$', re.IGNORECASE)

def _ensure_nlp():
    """Requirement 6: Loads the best available spaCy model and SkillNer."""
    global nlp, skill_extractor
    if nlp is None:
        for name in ("en_core_web_md", "en_core_web_sm"):
            try:
                nlp = spacy.load(name)
                break
            except: continue
        if nlp is None: nlp = spacy.blank("en")
    
    if skill_extractor is None and SkillExtractor is not None and PhraseMatcher is not None:
        try:
            skill_extractor = SkillExtractor(nlp, SKILL_DB, PhraseMatcher)
        except Exception:
            pass

def _ensure_sbert():
    """Requirement 9: Pre-loads the transformer for semantic vectorization."""
    global sbert_model
    if sbert_model is None:
        sbert_model = SentenceTransformer('all-MiniLM-L6-v2', device=device)

def _norm(s):
    return re.sub(r'[^a-z0-9+#&\-/ ]+', ' ', str(s or '').lower()).strip()

def _normalize_skill_text(term: str) -> str:
    """Normalization-first safety net before semantic math."""
    t = _norm(term)
    t = re.sub(r'\s+', ' ', t).strip()
    return t

def _tokenize(text: str) -> list:
    return [tok for tok in _normalize_skill_text(text).split() if tok]

def clean_resume_text(text: str) -> str:
    """Pre-extraction washer: strips emails, URLs, file paths, and fixes concatenation artifacts."""
    if not text:
        return text
    # Strip email addresses (e.g. mahesh@gmail.com)
    text = re.sub(r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b', ' ', text)
    # Strip URLs (http/https and bare www)
    text = re.sub(r'https?://\S+|www\.\S+', ' ', text)
    # Strip file-path artifacts (.pdf .docx .com etc.)
    text = re.sub(r'\b\S+\.(pdf|docx|doc|xlsx|csv|pptx|com|org|net|edu|io)\b', ' ', text, flags=re.IGNORECASE)
    # Fix camelCase concatenation: "Managementand" → "Management and"
    text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
    # Fix all-caps-fused words: "MANAGEMENTAnd" → "MANAGEMENT And"
    text = re.sub(r'([A-Z]{2,})([A-Z][a-z])', r'\1 \2', text)
    # Strip standalone numbers that are not part of a skill name (e.g. phone digits)
    text = re.sub(r'(?<![A-Za-z])\d{4,}(?![A-Za-z])', ' ', text)
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def prime_common_skills_matcher(common_skills: list):
    """Builds and caches a spaCy PhraseMatcher from the common_skills list.
    Call this once before batch extraction so Stream 2 (soft skills) is active."""
    global _common_phrase_matcher
    if not common_skills:
        return
    _ensure_nlp()
    if PhraseMatcher is None:
        return
    matcher = PhraseMatcher(nlp.vocab, attr='LOWER')
    patterns = [nlp.make_doc(s.strip().lower()) for s in common_skills if s and s.strip()]
    if patterns:
        matcher.add('COMMON_SKILL', patterns)
    _common_phrase_matcher = matcher

def wash_extracted_skill(term: str):
    """Post-extraction washer for individual skill terms.

    1. Rejects email/URL artifacts containing '@' or file extensions.
    2. Splits clumped all-lowercase words using known suffix vocabulary
       (requires 5+ preceding characters to avoid false positives):
         'interpersonalskills'  -> 'interpersonal skills'
         'managementand'        -> 'management and'
    3. Strips trailing noise joiners ('management and' -> 'management').
    4. Enforces Title Case and minimum length 3.
    Returns None for discarded terms.
    """
    if not term:
        return None
    t = term.strip()
    # Rule 1: Reject email and URL/file artifacts
    if '@' in t:
        return None
    if re.search(r'\.(com|edu|org|net|pdf|docx|io)\b', t, re.IGNORECASE):
        return None
    # Rule 2: Split clumped words — insert space before known suffix words
    # The {5,} lookbehind equivalent ensures we only split when the left segment
    # is at least 5 chars, avoiding false positives like 'command' -> 'comm and'
    for suffix in _CLUMP_SPLIT_SUFFIXES:
        pattern = rf'([a-zA-Z]{{5,}})({re.escape(suffix)})(?=[a-z]|$)'
        t = re.sub(pattern, r'\1 \2', t, flags=re.IGNORECASE)
    # Rule 3: Strip trailing joiners that dangle after splitting
    t = _TRAILING_JOINERS_RE.sub('', t).strip()
    # Rule 4: Collapse whitespace, enforce Title Case, check min length
    t = re.sub(r'\s+', ' ', t).strip().title()
    return t if len(t) >= 3 else None

# --- Skill Extraction ---

def extract_skills_batch(texts: list, batch_size: int = 64) -> list:
    """Dual-stream extraction with Pre-Extraction Washer:
    Stream 1 (Hard Skills): SkillNer dictionary extraction.
    Stream 2 (Soft Skills): PhraseMatcher seeded by common_skills (call prime_common_skills_matcher first).
    Stream 3 (Safety net): spaCy Noun Chunks + POS tags with quality gate.
    All output is Title Cased. NER is enabled to block GPE/PERSON/DATE noise."""
    _ensure_nlp()
    res = []
    has_parser = "parser" in nlp.pipe_names

    # Pre-wash texts to remove emails, URLs, clumped words before NLP
    clean_texts = [clean_resume_text(t) for t in texts]

    for doc in nlp.pipe(clean_texts, batch_size=batch_size):
        found = []

        # Stream 1 (Hard Skills): SkillNer — canonical name preserved as-is (already well-cased)
        if skill_extractor:
            try:
                annotations = skill_extractor.annotate(doc.text)
                matches = annotations['results']['full_matches'] + annotations['results']['ngram_scored']
                found.extend([SKILL_DB[m['skill_id']]['skill_name'] for m in matches])
            except: pass

        # Stream 2 (Soft / Common Skills): PhraseMatcher from common_skills DB
        if _common_phrase_matcher is not None:
            try:
                pm_matches = _common_phrase_matcher(doc)
                found.extend([doc[start:end].text.title() for _, start, end in pm_matches])
            except: pass

        # Stream 3 (Safety net): spaCy Noun Chunks + POS tags, gated by validate_skill_quality
        candidates = []
        if has_parser:
            try: candidates.extend([c.text.strip() for c in doc.noun_chunks])
            except: pass
        candidates.extend([t.text for t in doc if t.pos_ in ['PROPN', 'NOUN'] and len(t.text) > 1])
        found.extend([c.title() for c in candidates if validate_skill_quality(c, doc)])

        # Post-extraction wash: repair clumps, strip artifacts, enforce Title Case, deduplicate
        washed, seen_lower = [], set()
        for raw in found:
            cleaned = wash_extracted_skill(raw)
            if cleaned and cleaned.lower() not in seen_lower:
                seen_lower.add(cleaned.lower())
                washed.append(cleaned)
        res.append(washed)
    return res

# --- AI Matching Logic ---

def get_skill_embeddings(skills_list: list):
    """Requirement 9: Vectorizes skills for the Departmental Matrix."""
    if not skills_list: return None
    _ensure_sbert()
    return sbert_model.encode(skills_list, convert_to_tensor=True, show_progress_bar=False)

def build_bm25_index(found_entities):
    """Requirement 7: Pre-indexes student skills for high-speed lexical checks."""
    if not found_entities: return None
    tokens = [_norm(s) for s in found_entities if _norm(s)]
    return BM25Okapi([tokens]) if tokens else None

def validate_skill_quality(term: str, doc=None) -> bool:
    """Unified quality gate combining structural checks, blacklist, and optional NER filtering.
    Use doc=None when validating outside of a spaCy pipeline context."""
    stripped = term.strip()
    # Rule 1: Min length
    if len(stripped) < 3:
        return False
    # Rule 2: Blacklist
    if stripped.lower() in SKILL_NOISE_BLACKLIST:
        return False
    # Rule 3: Reject pure digit strings
    if re.match(r'^\d+$', stripped):
        return False
    # Rule 4: Reject email fragments
    if '@' in stripped:
        return False
    # Rule 5: Reject URL/file-path artifacts
    if re.search(r'\.(com|org|net|edu|pdf|docx|io)\b', stripped, re.IGNORECASE):
        return False
    # Rule 6: NER entity blocking (requires doc)
    if doc is not None:
        term_lower = stripped.lower()
        for ent in doc.ents:
            if ent.label_ in _FORBIDDEN_NER_LABELS and term_lower in ent.text.lower():
                return False
    return True

def is_valid_skill(term: str, doc) -> bool:
    """Backwards-compatible alias for validate_skill_quality with a required doc."""
    return validate_skill_quality(term, doc)

def _get_skill_db_reference():
    """Lazy-loads and caches SKILL_DB name embeddings once for filter_with_sbert."""
    global _skill_db_reference_embs
    if _skill_db_reference_embs is not None:
        return _skill_db_reference_embs
    _ensure_sbert()
    names = []
    if SKILL_DB is not None:
        names = list({v['skill_name'] for v in SKILL_DB.values() if v.get('skill_name')})[:600]
    if not names:
        _skill_db_reference_embs = None
        return None
    norms = [_normalize_skill_text(n) for n in names]
    _skill_db_reference_embs = sbert_model.encode(
        norms, convert_to_tensor=True, show_progress_bar=False, batch_size=256
    )
    return _skill_db_reference_embs

def filter_with_sbert(candidate_skills: list, reference_skills: list = None, threshold: float = 0.60) -> list:
    """Semantic validation: discards any candidate whose max SBERT cosine similarity
    to known professional skills (SKILL_DB + reference_skills) is below threshold."""
    if not candidate_skills:
        return []
    _ensure_sbert()
    # Assemble reference embeddings: cached SKILL_DB + optional extra reference_skills
    db_embs = _get_skill_db_reference()
    extra_embs = None
    if reference_skills:
        extra_norms = [_normalize_skill_text(s) for s in reference_skills if s]
        if extra_norms:
            extra_embs = sbert_model.encode(
                extra_norms, convert_to_tensor=True, show_progress_bar=False, batch_size=128
            )
    ref_parts = [p for p in [db_embs, extra_embs] if p is not None]
    if not ref_parts:
        # No reference available — pass candidates through unchanged
        return candidate_skills
    ref_embs = torch.cat(ref_parts, dim=0) if len(ref_parts) > 1 else ref_parts[0]
    cand_norms = [_normalize_skill_text(s) for s in candidate_skills]
    cand_embs = sbert_model.encode(
        cand_norms, convert_to_tensor=True, show_progress_bar=False, batch_size=128
    )
    # Keep candidates whose max similarity to any reference skill meets the threshold
    sims = util.cos_sim(cand_embs, ref_embs)   # (n_cands, n_refs)
    max_sims = sims.max(dim=1).values           # (n_cands,)
    return [skill for skill, sim in zip(candidate_skills, max_sims) if float(sim) >= threshold]

def deduplicate_skills_sbert(skills: list, threshold: float = 0.90) -> list:
    """Harmony dedup: removes near-duplicate skills via SBERT cosine similarity at 0.90 threshold."""
    if not skills:
        return []
    _ensure_sbert()
    norms = [_normalize_skill_text(s) for s in skills]
    embs = sbert_model.encode(norms, convert_to_tensor=True, show_progress_bar=False)
    unique, seen_vecs = [], []
    for skill, emb in zip(skills, embs):
        if not seen_vecs:
            unique.append(skill)
            seen_vecs.append(emb)
            continue
        sims = util.cos_sim(emb, torch.stack(seen_vecs)).squeeze(0)
        if float(sims.max()) < threshold:
            unique.append(skill)
            seen_vecs.append(emb)
    return unique

def rank_skills_bm25(skills: list, resume_text: str) -> list:
    """Ranks validated skills by BM25 prominence in the resume text.
    Skills whose tokens appear in header lines (short all-caps or title-case lines)
    receive a 2x boost so section headings are surfaced first."""
    if not skills or not resume_text:
        return skills
    corpus_tokens = _normalize_skill_text(resume_text).split()
    if not corpus_tokens:
        return skills
    # Detect header terms: tokens from short lines that are all-caps or title-case
    header_terms = set()
    for line in resume_text.splitlines():
        stripped = line.strip()
        if stripped and len(stripped) <= 60 and (stripped.isupper() or stripped.istitle()):
            header_terms.update(_normalize_skill_text(stripped).split())
    bm25 = BM25Okapi([corpus_tokens])
    scored = []
    for skill in skills:
        base_score = bm25.get_scores(_tokenize(skill))[0]
        skill_tokens = set(_tokenize(skill))
        boost = 2.0 if skill_tokens & header_terms else 1.0
        scored.append((skill, base_score * boost))
    scored.sort(key=lambda x: x[1], reverse=True)
    return [skill for skill, _ in scored]

def run_hybrid_match(entities, student_emb, targets, target_embs, threshold=0.65, bm25_index=None):
    """Requirement 7 & 8: Balanced Lexical/Semantic engine with 0.65 fair threshold."""
    if not entities or not targets: return [], {}, 0.0
    exact, semantic = [], {}
    bm25 = bm25_index or build_bm25_index(entities)
    
    for idx, skill in enumerate(targets):
        query = _norm(skill)
        # Lexical (Exact) fallback
        if bm25 and bm25.get_scores([query])[0] > 0:
            exact.append(skill)
        # Semantic (Context) match
        elif student_emb is not None and target_embs is not None:
            sim = float(util.cos_sim(target_embs[idx], student_emb).max())
            if sim >= threshold:
                semantic[skill] = sim

    # Requirement 8: Balanced scoring (10% Exact / 90% Semantic spirit)
    e_ratio = len(exact) / len(targets) if targets else 0
    s_ratio = len(semantic) / len(targets) if targets else 0
    f_score = (e_ratio * 0.10) + (s_ratio * 0.90)
    
    return exact, semantic, f_score