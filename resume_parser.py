"""
End-to-end resume analysis.

Reads the WHOLE resume (every page / paragraph), splits it into sections and
builds a structured candidate profile.  Everything in the profile is copied
from the resume text — nothing is inferred beyond simple categorisation — so
the profile can act as the source of truth for email generation.
"""
import html
import os
import re
import zipfile
from datetime import date

import knowledge as kb

# "?" / "" / "o" cover bullet glyphs that PDF extraction could not map
BULLET_RE = re.compile(r"^\s*(?:[•●▪◦▶►➢➤✓✔✦■□○·\-\*–?]|o(?=\s+[A-Z])|\(?\d{1,2}[.)])\s+")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?<![\d])(\+?\d[\d\s\-().]{8,17}\d)(?![\d])")

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
_MON = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
_DATE = rf"(?:{_MON}\s*[’',]?\s*\d{{2,4}}|\d{{1,2}}[/\-.]\d{{2,4}}|(?:19|20)\d{{2}})"
_END = rf"(?:{_DATE}|present|current|now|till\s*date|to\s*date|date|ongoing|today)"
DATE_RANGE_RE = re.compile(rf"({_DATE})\s*(?:-|–|—|to|till|until)\s*({_END})", re.IGNORECASE)

SECTION_HEADINGS = {
    "summary": ["summary", "professional summary", "profile", "profile summary", "career objective", "objective",
                "about me", "career summary", "executive summary", "professional profile", "overview"],
    "experience": ["experience", "work experience", "professional experience", "employment history", "work history",
                   "career history", "employment", "experience summary", "relevant experience", "internships",
                   "internship", "professional background", "employment details"],
    "skills": ["skills", "technical skills", "key skills", "core skills", "core competencies", "competencies",
               "areas of expertise", "expertise", "skill set", "skills & tools", "skills and tools", "tools",
               "tools & technologies", "technologies", "it skills", "soft skills", "functional skills",
               "skills summary", "key strengths", "strengths"],
    "education": ["education", "academic qualifications", "educational qualifications", "educational qualification",
                  "academics", "qualifications", "academic background", "education details"],
    "certifications": ["certifications", "certificates", "certification", "licenses & certifications",
                       "courses", "trainings", "training & certifications", "certifications & training"],
    "achievements": ["achievements", "key achievements", "accomplishments", "awards", "awards & achievements",
                     "achievements & awards", "honors", "honours", "recognition", "awards and recognition"],
    "projects": ["projects", "key projects", "academic projects", "personal projects"],
    "languages": ["languages", "languages known", "language proficiency"],
    "personal": ["personal details", "personal information", "declaration", "hobbies", "interests", "references",
                 "personal profile", "contact", "contact details"],
}
STRONG_COMPANY_SUFFIXES = {"pvt", "pvt.", "private", "ltd", "ltd.", "limited", "inc", "inc.", "llc", "llp", "corp",
                           "corporation", "technologies", "solutions", "labs", "systems", "infotech", "enterprises",
                           "consulting", "services", "group"}
_HEADING_LOOKUP = {h: sec for sec, names in SECTION_HEADINGS.items() for h in names}


# ── Text extraction ──────────────────────────────────────────────────────
def extract_text(path: str) -> str:
    """Extract all text from a PDF, DOCX or TXT resume."""
    if not path or not os.path.exists(path):
        raise FileNotFoundError(f"Resume not found: {path}")
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(path)
        pages = [(page.extract_text() or "") for page in reader.pages]  # every page, not just the first
        return "\n".join(pages)
    if ext == ".docx":
        return _docx_text(path)
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


def _docx_text(path: str) -> str:
    """Read paragraphs (body, tables, headers) from a .docx without python-docx."""
    parts = []
    with zipfile.ZipFile(path) as z:
        names = ["word/document.xml"] + sorted(n for n in z.namelist()
                                               if re.match(r"word/(header|footer)\d*\.xml", n))
        for name in names:
            if name not in z.namelist():
                continue
            xml = z.read(name).decode("utf-8", errors="ignore")
            xml = re.sub(r"<w:tab/>", "\t", xml)
            xml = re.sub(r"<w:br[^>]*/>", "\n", xml)
            xml = re.sub(r"</w:p>", "\n", xml)
            xml = re.sub(r"</w:tc>", " | ", xml)
            text = re.sub(r"<[^>]+>", "", xml)
            parts.append(html.unescape(text))
    return "\n".join(parts)


# ── Helpers ──────────────────────────────────────────────────────────────
def _clean(line: str) -> str:
    return re.sub(r"\s+", " ", line or "").strip()


def _strip_bullet(line: str) -> str:
    return _clean(BULLET_RE.sub("", line))


def _heading_of(line: str):
    key = re.sub(r"[^a-z& ]", "", line.lower()).strip()
    key = re.sub(r"\s+", " ", key)
    if not key or len(key) > 40:
        return None
    return _HEADING_LOOKUP.get(key)


def _merge_wrapped_lines(lines: list[str]) -> list[str]:
    """Re-join bullet points that PDF extraction wrapped onto several lines."""
    merged = []
    for raw in lines:
        line = raw.rstrip()
        if not line.strip():
            merged.append("")
            continue
        stripped = line.strip()
        prev = merged[-1] if merged else ""
        continuation = (
            prev and BULLET_RE.match(prev) and not BULLET_RE.match(stripped)
            and not _heading_of(stripped) and not DATE_RANGE_RE.search(stripped)
            and (stripped[0].islower() or not prev.rstrip().endswith((".", ":", ";")))
            and len(stripped) < 140 and stripped[0].islower()
        )
        if continuation:
            merged[-1] = prev.rstrip() + " " + stripped
        else:
            merged.append(line)
    return merged


def split_sections(text: str) -> dict:
    """Return {'header': [...], 'summary': [...], 'experience': [...], ...} keeping line order."""
    sections = {"header": []}
    current = "header"
    for line in _merge_wrapped_lines(text.splitlines()):
        sec = _heading_of(line) if line.strip() else None
        if sec:
            current = sec
            sections.setdefault(current, [])
            continue
        # "Skills: Excel, CRM" style inline headings
        m = re.match(r"^\s*([A-Za-z &]{3,30})\s*[:\-–]\s*(.+)$", line)
        if m and _heading_of(m.group(1)) in ("skills", "languages", "certifications"):
            sec = _heading_of(m.group(1))
            sections.setdefault(sec, []).append(m.group(2))
            continue
        sections.setdefault(current, []).append(line)
    return sections


def _parse_date(token: str, today: date):
    t = token.lower().strip()
    if re.match(r"present|current|now|till|to\s*date|date|ongoing|today", t):
        return today.year, today.month
    m = re.match(rf"({_MON})\s*[’',]?\s*(\d{{2,4}})", t)
    if m:
        mon = MONTHS.get(m.group(1)[:3], 1)
        yr = int(m.group(2))
        return (2000 + yr if yr < 100 else yr), mon
    m = re.match(r"(\d{1,2})[/\-.](\d{2,4})", t)
    if m:
        yr = int(m.group(2))
        return (2000 + yr if yr < 100 else yr), max(1, min(12, int(m.group(1))))
    m = re.match(r"((?:19|20)\d{2})", t)
    if m:
        return int(m.group(1)), 1
    return None


def _months_between(start, end) -> int:
    return max(0, (end[0] - start[0]) * 12 + (end[1] - start[1]))


def _merged_months(ranges: list) -> int:
    """Total months covered by possibly-overlapping (start, end) ranges."""
    spans = sorted((s[0] * 12 + s[1], e[0] * 12 + e[1]) for s, e in ranges if s and e)
    total, cur_s, cur_e = 0, None, None
    for s, e in spans:
        if cur_s is None or s > cur_e:
            if cur_s is not None:
                total += cur_e - cur_s
            cur_s, cur_e = s, e
        else:
            cur_e = max(cur_e, e)
    if cur_s is not None:
        total += cur_e - cur_s
    return total


def _looks_like_name(line: str) -> bool:
    s = _clean(line)
    if not s or len(s) > 40 or EMAIL_RE.search(s) or re.search(r"\d", s):
        return False
    if _heading_of(s) or re.search(r"resume|curriculum|vitae|\bcv\b|profile", s, re.I):
        return False
    words = s.replace(".", " ").split()
    if not 1 < len(words) <= 4:
        return False
    if any(w.lower() in kb.ROLE_WORDS for w in words):
        return False
    return all(re.match(r"^[A-Za-z][A-Za-z'\-]*$", w) for w in words)


def _title_case_name(s: str) -> str:
    return " ".join(w.capitalize() if w.isupper() or w.islower() else w for w in _clean(s).split())


def _split_fragments(text: str) -> list[str]:
    parts = re.split(r"\s*(?:\||•|–|—|\t| - |,| @ | at )\s*", text)
    return [_clean(p) for p in parts if _clean(p)]


def _classify_header(fragments: list[str]):
    title, company, location = "", "", ""
    for frag in fragments:
        low = frag.lower()
        if not location and kb.detect_cities(frag) and len(frag.split()) <= 3:
            location = kb.detect_cities(frag)[0]
            continue
        words = set(re.findall(r"[a-z.]+", low))
        strong_company = bool(words & STRONG_COMPANY_SUFFIXES)
        if not title and kb.is_role_like(frag) and not strong_company:
            title = frag
        elif not company and (strong_company or words & kb.COMPANY_HINTS):
            company = frag
        elif not company and len(frag.split()) <= 6 and not kb.is_role_like(frag):
            company = frag
    return title, company, location


# ── Main analysis ────────────────────────────────────────────────────────
def analyze_resume(text: str, today: date | None = None) -> dict:
    today = today or date.today()
    text = text or ""
    sections = split_sections(text)
    all_lines = [l for l in (_clean(x) for x in text.splitlines()) if l]
    header = [l for l in (_clean(x) for x in sections.get("header", [])) if l]

    profile = {
        "name": "", "email": "", "phone": "", "location": "",
        "total_experience": "", "total_experience_years": None,
        "current_role": "", "job_titles": [], "companies": [], "employment_dates": [],
        "experience_entries": [], "responsibilities": [], "achievements": [],
        "strongest_achievements": [], "skills": [], "technical_skills": [], "business_skills": [],
        "tools": [], "crm_tools": [], "ai_tools": [], "industries": [],
        "leadership_experience": [], "sales_experience": [], "customer_experience": [],
        "education": [], "certifications": [], "languages": [], "keywords": [],
        "domain_knowledge": [], "job_families": [], "summary": "", "evidence": [],
    }

    # Contact details
    m = EMAIL_RE.search(text)
    profile["email"] = m.group(0) if m else ""
    for pm in PHONE_RE.finditer(text):
        cand = pm.group(1)
        digits = re.sub(r"\D", "", cand)
        if 10 <= len(digits) <= 13 and not DATE_RANGE_RE.search(cand):
            profile["phone"] = _clean(cand)
            break
    for line in (header + all_lines)[:8]:
        if _looks_like_name(line):
            profile["name"] = _title_case_name(line)
            break
    loc_line = next((l for l in all_lines if re.match(r"^(location|address|city|current location)\s*[:\-]", l, re.I)), "")
    cities = kb.detect_cities(loc_line) or kb.detect_cities(" ".join(header[:10]))
    profile["location"] = cities[0] if cities else ""

    # Summary
    summary_lines = [_strip_bullet(l) for l in sections.get("summary", []) if _clean(l)]
    profile["summary"] = " ".join(summary_lines)

    # Experience entries (only the experience section, so education dates are ignored)
    exp_lines = [l for l in sections.get("experience", [])]
    if not exp_lines:  # some resumes have no headings — fall back to lines outside education
        edu = set(sections.get("education", []))
        exp_lines = [l for l in text.splitlines() if l not in edu]
    entries, current, pending_header = [], None, []
    for raw in exp_lines:
        line = _clean(raw)
        if not line:
            continue
        dr = DATE_RANGE_RE.search(line)
        if dr:
            start, end = _parse_date(dr.group(1), today), _parse_date(dr.group(2), today)
            rest = _clean(line[:dr.start()] + " " + line[dr.end():]).strip("|,–- ()")
            frags = [f for l in pending_header[-2:] for f in _split_fragments(l)] + _split_fragments(rest)
            title, company, location = _classify_header(frags)
            current = {"title": title, "company": company, "location": location,
                       "dates": _clean(dr.group(0)), "start": start, "end": end,
                       "is_current": bool(re.match(r"present|current|now|till|to\s*date|ongoing|today",
                                                   dr.group(2).strip(), re.I)),
                       "responsibilities": []}
            entries.append(current)
            pending_header = []
        elif BULLET_RE.match(raw) or (current and len(line) > 60) or (
                current and current["title"] and current["company"] and len(line.split()) >= 5
                and not kb.is_role_like(line.split("|")[0][:40])):
            item = _strip_bullet(raw)
            if current is not None:
                current["responsibilities"].append(item)
            else:
                profile["responsibilities"].append(item)
        else:
            if current and not current["title"] and kb.is_role_like(line) and len(line) < 70:
                current["title"] = line
            elif current and not current["company"] and len(line) < 60 and not kb.is_role_like(line) \
                    and not current["responsibilities"]:
                current["company"] = line
            else:
                pending_header.append(line)
    profile["experience_entries"] = [
        {k: v for k, v in e.items() if k not in ("start", "end")} for e in entries]
    profile["job_titles"] = list(dict.fromkeys(e["title"] for e in entries if e["title"]))
    profile["companies"] = list(dict.fromkeys(e["company"] for e in entries if e["company"]))
    profile["employment_dates"] = [e["dates"] for e in entries]
    for e in entries:
        profile["responsibilities"].extend(e["responsibilities"])

    if entries:
        ordered = sorted(entries, key=lambda e: (e["is_current"], e["end"] or (0, 0), e["start"] or (0, 0)),
                         reverse=True)
        profile["current_role"] = ordered[0]["title"] or ""
    if not profile["current_role"]:
        for line in header[:6]:
            if kb.is_role_like(line) and not _looks_like_name(line) and len(line) < 70 and not EMAIL_RE.search(line):
                profile["current_role"] = _clean(line.split("|")[0])
                break

    # Total experience: an explicit statement in the resume wins over computed dates
    explicit = re.search(
        r"(\d{1,2}(?:\.\d{1,2})?)\s*(\+?)\s*(?:years?|yrs?)\s*(?:and\s*\d+\s*months?\s*)?(?:of\s+)?"
        r"(?:total\s+|overall\s+|professional\s+|rich\s+|hands[- ]on\s+|progressive\s+)*(?:work\s+)?experience",
        text, re.IGNORECASE)
    if not explicit:
        explicit = re.search(r"experience\s*(?:of|:)\s*(\d{1,2}(?:\.\d{1,2})?)\s*(\+?)\s*(?:years?|yrs?)",
                             text, re.IGNORECASE)
    if explicit:
        yrs = float(explicit.group(1))
        profile["total_experience_years"] = yrs
        profile["total_experience"] = f"{explicit.group(1)}{explicit.group(2)} years"
    else:
        months = _merged_months([(e["start"], e["end"]) for e in entries])
        if months:
            yrs = round(months / 12.0, 1)
            profile["total_experience_years"] = yrs
            profile["total_experience"] = f"{yrs:g}+ years" if yrs >= 1 else f"{months} months"

    # Achievements — dedicated section + quantified lines anywhere
    ach = [_strip_bullet(l) for l in sections.get("achievements", []) if _clean(l)]
    for line in profile["responsibilities"] + summary_lines:
        if re.search(r"\d+\s*%|\d+x\b|₹|rs\.?\s?\d|inr|\$\s?\d|lakh|crore|million|\baward|recogni[sz]ed|"
                     r"top performer|best performer|exceed|surpass", line, re.I) and re.search(r"\d|award|recogni|top|best", line, re.I):
            ach.append(line)
    profile["achievements"] = list(dict.fromkeys(a for a in ach if a))

    def strength(s):
        return (3 * bool(re.search(r"\d+\s*%", s)) + bool(re.search(r"\d", s))
                + 2 * bool(re.search(r"award|recogni|top performer|best", s, re.I))
                + bool(re.search(r"achiev|exceed|increas|improv|grew|growth|reduc|generat|won|closed", s, re.I)))
    profile["strongest_achievements"] = sorted(profile["achievements"], key=strength, reverse=True)[:5]

    # Skills
    skill_items = []
    for line in sections.get("skills", []):
        line = _strip_bullet(line)
        if ":" in line:
            line = line.split(":", 1)[1]
        for part in re.split(r"[,|•;/]|\s{2,}|\t", line):
            part = _clean(part).strip(".-")
            if 1 < len(part) <= 40:
                skill_items.append(part)
    detected = kb.find_skills(text)
    profile["technical_skills"] = detected["technical"]
    profile["business_skills"] = detected["business"]
    profile["crm_tools"] = detected["crm"]
    profile["ai_tools"] = detected["ai"]
    profile["tools"] = detected["tools"]
    combined = skill_items + [s for cat in detected.values() for s in cat]
    seen, skills = set(), []
    for s in combined:
        if s.lower() not in seen:
            seen.add(s.lower())
            skills.append(s)
    profile["skills"] = skills

    profile["industries"] = kb.find_industries(text)

    summary_sentences = [_clean(x) for x in re.split(r"(?<=[.!?])\s+", profile["summary"]) if _clean(x)]
    body_lines = profile["responsibilities"] + profile["achievements"] + summary_sentences
    profile["leadership_experience"] = [l for l in body_lines if re.search(
        r"\b(led|leading a|leading the|managed a team|team of|mentor|supervis|coach|trained|headed|team lead|"
        r"team leadership)", l, re.I)]
    profile["sales_experience"] = [l for l in body_lines if re.search(
        r"\b(sales|revenue|target|quota|deal|closing|closure|conversion|pipeline|leads?)\b", l, re.I)]
    profile["customer_experience"] = [l for l in body_lines if re.search(
        r"\b(customer|client|account|satisfaction|retention|stakeholder)", l, re.I)]
    for key in ("leadership_experience", "sales_experience", "customer_experience"):
        profile[key] = list(dict.fromkeys(profile[key]))

    # Education / certifications / languages
    edu = [_strip_bullet(l) for l in sections.get("education", []) if _clean(l)]
    if not edu:
        edu = [l for l in all_lines if kb.DEGREE_PATTERN.search(l) and len(l) < 160]
    profile["education"] = list(dict.fromkeys(edu))
    certs = [_strip_bullet(l) for l in sections.get("certifications", []) if _clean(l)]
    certs += [l for l in all_lines if re.search(r"certif", l, re.I) and not _heading_of(l) and len(l) < 160]
    profile["certifications"] = list(dict.fromkeys(_strip_bullet(c) for c in certs))
    lang_text = " ".join(sections.get("languages", [])) or " ".join(
        l for l in all_lines if re.match(r"^\s*languages?\b", l, re.I))
    profile["languages"] = [lang for lang in kb.LANGUAGES if kb.has_term(lang, lang_text)]

    # Keywords, domain knowledge, job families
    tv = kb.token_vector(" ".join(body_lines + skill_items))
    profile["keywords"] = [t for t, c in sorted(tv.items(), key=lambda kv: -kv[1]) if len(t) > 3][:20]
    cv = kb.concept_vector(text)
    profile["domain_knowledge"] = [c for c, n in sorted(cv.items(), key=lambda kv: -kv[1]) if n >= 2]
    fams = []
    for c in profile["domain_knowledge"][:6]:
        fam = kb.JOB_FAMILY_BY_CONCEPT.get(c)
        if fam and fam not in fams:
            fams.append(fam)
    profile["job_families"] = fams

    # Evidence pool for highlights — every factual line from the resume
    evidence = []
    for e in entries:
        for r in e["responsibilities"]:
            evidence.append(r)
    evidence += profile["achievements"]
    evidence += [r for r in profile["responsibilities"] if r not in evidence]
    for sent in re.split(r"(?<=[.!?])\s+", profile["summary"]):
        if len(sent.split()) >= 6:
            evidence.append(_clean(sent))
    profile["evidence"] = [e for e in dict.fromkeys(_clean(x) for x in evidence) if len(e.split()) >= 3]
    return profile


def analyze_resume_file(path: str, today: date | None = None) -> tuple[dict, str]:
    text = extract_text(path)
    return analyze_resume(text, today), text


def format_profile(profile: dict) -> str:
    """Human-readable profile summary for the Candidate Profile panel."""
    def block(title, items, limit=12):
        items = [i for i in (items or []) if i]
        if not items:
            return ""
        lines = "\n".join(f"  • {i}" for i in items[:limit])
        more = f"\n  … +{len(items) - limit} more" if len(items) > limit else ""
        return f"{title}:\n{lines}{more}\n\n"

    out = [
        f"Candidate: {profile.get('name') or '—'}\n",
        f"Email: {profile.get('email') or '—'}   Phone: {profile.get('phone') or '—'}   "
        f"Location: {profile.get('location') or '—'}\n\n",
        f"Experience: {profile.get('total_experience') or '—'}\n",
        f"Current/Recent Role: {profile.get('current_role') or '—'}\n\n",
    ]
    if profile.get("summary"):
        out.append(f"Summary:\n  {profile['summary'][:600]}\n\n")
    for e in profile.get("experience_entries", []):
        out.append(f"• {e.get('title') or 'Role'} — {e.get('company') or 'Company'} ({e.get('dates')})\n")
    if profile.get("experience_entries"):
        out.append("\n")
    out.append(block("Core Skills", profile.get("skills"), 25))
    out.append(block("Achievements", profile.get("achievements")))
    out.append(block("CRM Tools", profile.get("crm_tools")))
    out.append(block("AI Tools", profile.get("ai_tools")))
    out.append(block("Tools", profile.get("tools")))
    out.append(block("Industry Experience", profile.get("industries")))
    out.append(block("Leadership Experience", profile.get("leadership_experience"), 5))
    out.append(block("Sales Experience", profile.get("sales_experience"), 5))
    out.append(block("Customer / Client Experience", profile.get("customer_experience"), 5))
    out.append(block("Education", profile.get("education")))
    out.append(block("Certifications", profile.get("certifications")))
    out.append(block("Languages", profile.get("languages")))
    out.append(block("Domain Knowledge", profile.get("domain_knowledge")))
    out.append(block("Potential Job Families", profile.get("job_families")))
    out.append(block("Keywords", profile.get("keywords"), 20))
    return "".join(out)
