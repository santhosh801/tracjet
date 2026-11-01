"""
Scores a job description against every template in the candidate's Template
Library and picks the best one.  Title is only one of seven signals, so the
JD's responsibilities and skills can override a misleading job title.
"""
import re

import knowledge as kb
from jd_analyzer import SENIORITY_RANK, detect_seniority

WEIGHTS = {
    "title": 0.22, "responsibilities": 0.20, "skills": 0.15, "seniority": 0.08,
    "domain": 0.15, "keywords": 0.10, "candidate": 0.10,
}
POOR_MATCH_THRESHOLD = 45  # below this the email goes to Needs Review

TITLE_SYNONYMS = {
    "fsd": "full stack developer", "fullstack": "full stack", "full-stack": "full stack",
    "sde": "software development engineer", "swe": "software engineer", "bde": "business development executive",
    "bdm": "business development manager", "bd": "business development", "tl": "team lead",
    "csm": "customer success manager", "kam": "key account manager", "sdr": "sales development representative",
    "bdr": "business development representative", "ae": "account executive", "qa": "quality assurance",
    "dev": "developer", "mern": "full stack developer",
}


def _norm_title(t: str) -> set[str]:
    words = re.findall(r"[a-z+#.]+", (t or "").lower())
    out = []
    for w in words:
        out += TITLE_SYNONYMS.get(w, w).split()
    generic = {"senior", "sr", "junior", "jr", "associate", "i", "ii", "iii", "the", "a", "an", "for", "of", "and",
               "role", "position", "application", "applying", "immediate", "joiner", "years", "experience"}
    return {w for w in out if w not in generic and len(w) > 1}


def _overlap(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def template_text(t: dict) -> str:
    return " ".join([t.get("name", ""), t.get("role_category", ""), t.get("example_subject", ""),
                     t.get("example_body", "")])


def _calibrate(x: float) -> float:
    """Spread raw cosine values (which cluster low) over 0..1."""
    return min(1.0, x ** 0.6) if x > 0 else 0.0


def score_template(jd: dict, template: dict, profile: dict | None = None) -> dict:
    ttext = template_text(template)
    head = " ".join([template.get("name", ""), template.get("role_category", ""), template.get("example_subject", "")])
    jd_text = jd.get("text", "")
    jd_title = jd.get("job_title", "")

    # 1. title similarity (template name/category/subject vs JD title)
    title = _overlap(_norm_title(jd_title), _norm_title(head)) if jd_title else 0.0

    # 2. responsibilities similarity (concepts in responsibilities vs template body)
    resp_text = " ".join(jd.get("responsibilities") or []) or jd_text
    resp = _calibrate(kb.cosine(kb.concept_vector(resp_text), kb.concept_vector(ttext)))

    # 3. skills similarity
    jd_skills = set(jd.get("required_skills") or []) | set(jd.get("preferred_skills") or [])
    t_skills = {s for cat in kb.find_skills(ttext).values() for s in cat}
    if jd_skills and t_skills:
        skills = len(jd_skills & t_skills) / min(len(jd_skills), len(t_skills))
    else:
        skills = 0.0
    skills = max(skills, _calibrate(kb.cosine(kb.concept_vector(" ".join(jd_skills)), kb.concept_vector(ttext))) * 0.8)

    # 4. seniority similarity
    t_sen = detect_seniority(head, None)
    j_sen = jd.get("seniority") or detect_seniority(jd_title, jd.get("exp_min"))
    seniority = 1.0 - abs(SENIORITY_RANK.get(t_sen, 2) - SENIORITY_RANK.get(j_sen, 2)) / 5.0

    # 5. industry / domain similarity (concept families)
    domain = _calibrate(kb.cosine(jd.get("families") or kb.family_vector(jd_text), kb.family_vector(ttext)))
    jd_ind, t_ind = set(jd.get("industry") or []), set(kb.find_industries(ttext))
    if jd_ind & t_ind:
        domain = min(1.0, domain + 0.1)

    # 6. keyword similarity (bag of words)
    keywords = _calibrate(kb.cosine(kb.token_vector(jd_text), kb.token_vector(ttext)))

    # 7. candidate relevance — how well the candidate's profile backs this template's focus
    candidate = 0.5
    if profile:
        cand_text = " ".join((profile.get("evidence") or []) + (profile.get("skills") or []))
        candidate = _calibrate(kb.cosine(kb.concept_vector(cand_text), kb.concept_vector(ttext)))

    parts = {"title": title, "responsibilities": resp, "skills": skills, "seniority": seniority,
             "domain": domain, "keywords": keywords, "candidate": candidate}
    total = sum(WEIGHTS[k] * v for k, v in parts.items())
    return {"score": int(round(total * 100)), "parts": {k: int(round(v * 100)) for k, v in parts.items()}}


def rank_templates(jd: dict, templates: list[dict], profile: dict | None = None) -> list[dict]:
    """Return every configured template with its score, best first."""
    ranked = []
    for t in templates:
        if not (t.get("example_body") or "").strip():
            continue
        s = score_template(jd, t, t.get("profile") or profile)  # a template's own resume backs its category
        ranked.append({"template_id": t.get("id"), "slot": t.get("slot"), "name": t.get("name") or f"Template {t.get('slot')}",
                       "score": s["score"], "parts": s["parts"]})
    ranked.sort(key=lambda r: (-r["score"], r.get("slot") or 0))
    return ranked


def explain_choice(ranked: list[dict]) -> str:
    if not ranked:
        return "No templates configured."
    best = ranked[0]
    p = best["parts"]
    strongest = sorted(p.items(), key=lambda kv: -(WEIGHTS[kv[0]] * kv[1]))[:3]
    labels = {"title": "job title", "responsibilities": "responsibilities", "skills": "skills",
              "seniority": "seniority", "domain": "domain/industry", "keywords": "keywords",
              "candidate": "candidate relevance"}
    why = ", ".join(f"{labels[k]} {v}%" for k, v in strongest)
    margin = best["score"] - ranked[1]["score"] if len(ranked) > 1 else best["score"]
    return f"Selected “{best['name']}” ({best['score']}%) — strongest on {why}; {margin} pts ahead of next best."


def candidate_match(profile: dict, jd: dict, resume_text: str = "") -> dict:
    """
    How well the candidate (resume/profile only) covers this JD.
    Missing skills are reported for the user — they are never written into the email.
    """
    allowed = profile_fact_text(profile, resume_text)
    jd_skills = list(dict.fromkeys((jd.get("required_skills") or []) + (jd.get("preferred_skills") or [])))
    matched = [s for s in jd_skills if kb.skill_supported(s, allowed)]
    missing = [s for s in jd_skills if s not in matched]
    concept_sim = _calibrate(kb.cosine(kb.concept_vector(allowed), jd.get("concepts") or {}))
    skill_ratio = (len(matched) / len(jd_skills)) if jd_skills else concept_sim
    pct = int(round(100 * (0.6 * skill_ratio + 0.4 * concept_sim)))
    return {"match_percentage": pct, "matched_skills": matched, "missing_skills": missing,
            "concept_similarity": int(round(concept_sim * 100))}


def profile_fact_text(profile: dict, resume_text: str = "") -> str:
    """All candidate facts (resume + reviewed profile) as one searchable string."""
    parts = [resume_text or ""]
    for k, v in (profile or {}).items():
        if k in kb.DERIVED_PROFILE_KEYS:
            continue
        if isinstance(v, str):
            parts.append(v)
        elif isinstance(v, list):
            for item in v:
                parts.append(" ".join(str(x) for x in item.values()) if isinstance(item, dict) else str(item))
    return "\n".join(parts)
