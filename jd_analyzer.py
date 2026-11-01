"""
Full job-description analysis for LinkedIn posts.

`split_bulk_posts` turns one big paste into independent job chunks and
`analyze_jd` extracts every field the email pipeline needs from the WHOLE
post (not just the first few lines).
"""
import re

import knowledge as kb

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
SKIP_EMAIL_PARTS = ["acte.in", "youtube", "lnkd.in", "tvktechs", "lyl.ai", "example.com", "example.org",
                    "sentry", "noreply", "no-reply", "@2x", ".png", ".jpg"]

# "========== JOB 1 ==========", "----- JOB 2 -----", "JOB 3:", "#####", "Job #4"
SEPARATOR_RE = re.compile(
    r"^\s*(?:[=\-*#_~]{3,}\s*(?:job\s*#?\s*\d+\s*)?[=\-*#_~]*|job\s*#?\s*\d+\s*[:.)\-]?)\s*$", re.IGNORECASE)

POSTER_HEADLINE_RE = re.compile(
    r"(?i)^(?:senior\s+|lead\s+|sr\.?\s+)?(?:talent acquisition|technical recruiter|recruiter|hr|human resources|"
    r"recruitment)[\w &/\-]{0,40}\s(?:at|@)\s.{1,60}$")
EMOJI_RE = re.compile("[\U0001F000-\U0001FAFF☀-➿️‍]")

NOT_NAME_WORDS = {
    "hiring", "job", "jobs", "team", "years", "immediate", "joiner", "joiners", "we", "our", "dear", "hello", "hi",
    "urgent", "opening", "openings", "role", "position", "apply", "location", "experience", "skills", "company",
    "salary", "ctc", "remote", "hybrid", "onsite", "office", "work", "full", "time", "part", "contract",
    "linkedin", "premium", "follow", "connect", "message", "view", "profile", "feed", "post", "like", "comment",
    "repost", "send", "share", "talent", "acquisition", "human", "resources", "recruitment", "hr", "mail", "email",
    "regards", "thanks", "thank", "you", "best", "warm", "kind", "sincerely", "interested", "candidates",
    "requirements", "responsibilities", "qualification", "qualifications", "description", "about", "key",
} | kb.ROLE_WORDS | {m for m in ["january", "february", "march", "april", "may", "june", "july", "august",
                                   "september", "october", "november", "december"]}

NOT_COMPANY = {"we", "us", "our team", "the team", "immediate", "immediately", "the", "a", "an", "our", "you",
               "your", "my", "linkedin", "this", "that", "it", "them", "hiring", "india", "home"}
# job-post field labels that get mistaken for company names ("Job Type", "Work Mode", "Interview", …)
LABEL_WORDS = {"job", "type", "work", "mode", "model", "interview", "full", "part", "time", "full-time", "part-time",
               "from", "office", "home", "remote", "hybrid", "onsite", "location", "experience", "salary", "ctc",
               "shift", "timing", "timings", "notice", "period", "qualification", "openings", "vacancy", "vacancies",
               "employment", "contract", "permanent", "freelance", "internship", "duration", "stipend", "days",
               "walk-in", "walkin", "drive", "date", "venue", "apply", "details", "description", "role", "position"}

SECTION_PATTERNS = {
    "responsibilities": r"(roles?\s*(?:&|and)\s*responsibilit\w*|key responsibilit\w*|responsibilit\w*|"
                        r"what you(?:'|’)?ll do|what you will do|your role|job description|duties|the role|"
                        r"key result areas|kras?)",
    "required": r"(requirements?|must[- ]have\w*|qualifications?|required skills|key skills|skills required|"
                r"eligibility|what we(?:'|’)?re looking for|what we are looking for|who you are|desired profile|"
                r"skills|candidate profile)",
    "preferred": r"(good[- ]to[- ]have|nice[- ]to[- ]have|preferred(?: skills| qualifications)?|bonus|plus points?|"
                 r"added advantage)",
}


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", EMOJI_RE.sub(" ", s or "")).strip()


# ── Bulk splitting ───────────────────────────────────────────────────────
def split_bulk_posts(raw_text: str) -> tuple[list[str], bool]:
    """
    Split a bulk paste into job chunks.
    Returns (chunks, explicit) — explicit is True when user separators were used.
    """
    lines = (raw_text or "").splitlines()
    if any(SEPARATOR_RE.match(l) for l in lines):
        chunks, cur = [], []
        for line in lines:
            if SEPARATOR_RE.match(line):
                if "\n".join(cur).strip():
                    chunks.append("\n".join(cur).strip())
                cur = []
            else:
                cur.append(line)
        if "\n".join(cur).strip():
            chunks.append("\n".join(cur).strip())
        # a separator-like line inside a copied LinkedIn feed must not merge many posts into one job
        out = []
        for c in chunks:
            out += _split_feed(c.splitlines()) if _feed_post_count(c) > 1 else [c]
        return [c.strip() for c in out if c.strip()], True

    return _split_feed(lines), False


def _is_feed_header(line: str) -> bool:
    s = line.strip()
    return s == "Feed post" or (s.lower().startswith("view ") and "profile" in s.lower())


def _feed_post_count(text: str) -> int:
    return sum(1 for l in text.splitlines() if l.strip() == "Feed post")


def _split_feed(lines: list[str]) -> list[str]:
    """LinkedIn feed splitting ("Feed post" / "View X's profile" headers)."""
    chunks, cur = [], []
    for line in lines:
        if _is_feed_header(line):
            if cur:
                chunks.append("\n".join(cur))
                cur = []
        cur.append(line)
    if cur:
        chunks.append("\n".join(cur))
    return [c for c in chunks if c.strip()]


# ── LinkedIn poster header ───────────────────────────────────────────────
DEGREE_LINE_RE = re.compile(r"^\s*[•·]\s*(?:1st|2nd|3rd\+?|following)\b", re.I)
TIME_LINE_RE = re.compile(r"^\s*\d+\s*(?:s|m|h|d|w|mo|yr|yrs)\b", re.I)
HEADER_NOISE = {"follow", "+ follow", "connect", "verified", "premium", "promoted", "edited", "visit my website",
                "view my services", "book an appointment", "view my portfolio", "view my newsletter"}


def split_poster_header(text: str) -> tuple[str, str, str]:
    """
    A copied LinkedIn post starts with the poster's name, connection degree, headline and age:
        Priya Sharma / • 2nd / Talent Acquisition Specialist at X / 16h / Follow / <post>
    Returns (poster_name, poster_designation, post_body).  The headline describes the RECRUITER, never the
    advertised job, so title/company extraction must only look at the body.  Without a header the whole
    text is the body.
    """
    lines = (text or "").splitlines()
    idx = next((i for i, l in enumerate(lines[:40]) if DEGREE_LINE_RE.match(l)), None)
    if idx is None:
        return "", "", text or ""
    name = next((lines[j].strip() for j in range(idx - 1, -1, -1) if lines[j].strip()), "")
    designation, body_start = "", idx + 1
    for j in range(idx + 1, min(len(lines), idx + 14)):
        s = lines[j].strip()
        if not s or s.lower() in HEADER_NOISE:
            continue
        if TIME_LINE_RE.match(s):
            body_start = j + 1
            break
        if designation:  # no age line — the post starts after the headline
            break
        designation, body_start = s, j + 1
    while body_start < len(lines) and (not lines[body_start].strip()
                                       or lines[body_start].strip().lower() in HEADER_NOISE):
        body_start += 1
    return _valid_person_name(name), _clean(designation), "\n".join(lines[body_start:])


def _headline_company(designation: str) -> str:
    """'Talent Acquisition at Infobeans | IT Hiring' -> 'Infobeans'."""
    m = re.search(r"(?:\bat\b|@)\s*([A-Z][\w&.\-]*(?:\s+[A-Z&][\w&.\-]*){0,3})", designation or "")
    return _valid_company(m.group(1)) if m else ""


# ── Field extraction ─────────────────────────────────────────────────────
def extract_emails(text: str) -> list[str]:
    out = []
    for e in EMAIL_RE.findall(text or ""):
        e = e.strip(".")
        if any(p in e.lower() for p in SKIP_EMAIL_PARTS):
            continue
        if e.lower() not in [x.lower() for x in out]:
            out.append(e)
    return out


def _valid_person_name(name: str) -> str:
    name = _clean(name).strip(" ,.-:|")
    name = re.sub(r"\s*[•·]\s*(?:1st|2nd|3rd|3rd\+)?.*$", "", name)
    words = name.split()
    if not 1 <= len(words) <= 3:
        return ""
    for w in words:
        if not re.match(r"^[A-Z][a-zA-Z'\-]*\.?$", w) or w.lower().strip(".") in NOT_NAME_WORDS:
            return ""
        if kb.detect_cities(w):
            return ""
    if len(words) == 1 and len(words[0]) < 3:
        return ""
    return " ".join(words)


def extract_recruiter_name(text: str) -> str:
    """Only return a name when it comes from a reliable pattern; otherwise ''."""
    patterns = [
        r"View\s+([A-Z][\w'\-]+(?:[ \t]+[A-Z][\w'\-.]+){0,2})[’']s?\s*(?:profile|graphic|verified)",
        r"(?im)^\s*(?:recruiter|contact person|contact|hr|poc|point of contact|spoc|posted by)\s*(?:name)?\s*[:\-–]\s*"
        r"([A-Z][a-zA-Z'\-]+(?:[ \t]+[A-Z][a-zA-Z'\-.]+){0,2})",
        r"(?i)(?:reach out to|connect with|contact)[ \t]+([A-Z][a-zA-Z'\-]+(?:[ \t]+[A-Z][a-zA-Z'\-]+)?)[ \t]+"
        r"(?:at|on|via)\b",
        r"(?im)^\s*(?:thanks\s*(?:&|and)\s*regards|regards|best regards|warm regards|thanks)\s*,?\s*\n\s*"
        r"([A-Z][a-zA-Z'\-]+(?:[ \t]+[A-Z][a-zA-Z'\-.]+){0,2})[ \t]*$",
        r"(?m)^\s*Feed post\s*\n\s*([A-Z][a-zA-Z'\-]+(?:[ \t]+[A-Z][a-zA-Z'\-.]+){1,2})[ \t]*$",
    ]
    for pat in patterns:
        for m in re.finditer(pat, text or ""):
            # the contact/recruiter labels are case-insensitive; names must still be capitalised
            name = _valid_person_name(m.group(1))
            if name:
                return name
    return ""


def _valid_company(raw: str) -> str:
    c = _clean(raw)
    c = re.split(r"\s+(?:is|are|for|in|located|based|has|seeks|seeking|looking|hiring|–|-|\|)\s+|[|!,;:(]|\.\s|\s—\s",
                 c)[0]
    c = c.strip(" .-–—:#@*")
    c = re.sub(r"^(?:the)\s+", "", c, flags=re.I)
    if not c or len(c) < 2 or len(c) > 50 or len(c.split()) > 6:
        return ""
    if c.lower() in NOT_COMPANY or kb.detect_cities(c) == [c] or EMAIL_RE.search(c):
        return ""
    if all(w.lower() in kb.ROLE_WORDS or w.lower() in kb.STOPWORDS for w in c.split()):
        return ""
    if all(w.lower().strip(".:") in LABEL_WORDS or w.lower() in kb.STOPWORDS for w in c.split()):
        return ""
    if not re.search(r"[A-Z0-9]", c[0]):
        return ""
    return c


def extract_company(text: str, emails: list[str]) -> tuple[str, str]:
    """Return (company, source)."""
    patterns = [
        r"(?im)^\s*(?:company(?:\s*name)?|organi[sz]ation|client|employer|hiring company)\s*[:\-–]\s*(.+)$",
        r"🏢\s*(?:company\s*[:\-]?\s*)?(.+)",
        r"\b(?:[Hh]iring|[Oo]pening|[Oo]penings|[Vv]acanc(?:y|ies)|[Rr]ole|[Pp]osition|[Oo]pportunity|[Jj]oin us)\s+"
        r"(?:at|@|with)\s+([A-Z][\w&.\-]*(?:\s+[A-Z&][\w&.\-]*){0,4})",
        r"\b([A-Z][\w&.\-]*(?:\s+[A-Z&][\w&.\-]*){0,3})\s+is\s+(?:hiring|looking|expanding|growing)",
        r"(?i:\b(?:" + "|".join(sorted(kb.ROLE_WORDS)) + r"))s?[ \t]+(?:at|@|with)[ \t]+"
        r"([A-Z][\w&.\-]*(?:[ \t]+[A-Z&][\w&.\-]*){0,3})",
        r"(?:^|\s)@\s?([A-Z][\w&.\-]*(?:\s+[A-Z&][\w&.\-]*){0,3})",
        r"\b[Jj]oin\s+(?:our team at\s+|us at\s+)?([A-Z][\w&.\-]*(?:\s+[A-Z&][\w&.\-]*){0,3})",
    ]
    for pat in patterns:
        for m in re.finditer(pat, text or ""):
            c = _valid_company(m.group(1))
            if c:
                return c, "post"
    for e in emails:
        domain = e.split("@", 1)[1].lower()
        label = domain.split(".")[0]
        if label not in kb.GENERIC_EMAIL_DOMAINS and len(label) > 1:
            words = re.split(r"[-_]", label)
            name = " ".join(w.upper() if len(w) <= 3 else w.capitalize() for w in words if w)
            return name, "email_domain"
    return "", ""


def clean_title(raw: str) -> str:
    t = _clean(raw)
    t = re.sub(r"^[\s#*•|:\-–]+", "", t)
    t = re.sub(r"(?i)^(?:we(?:'|’)?re\s+hiring|we\s+are\s+hiring|hiring\s+alert|urgent(?:ly)?\s+hiring|"
               r"urgent\s+requirement|now\s+hiring|hiring|role|position|job\s*title|designation|opening|"
               r"looking\s+for|requirement)\s*(?:for|of)?\s*[:\-–!|]*\s*", "", t)
    t = re.sub(r"(?i)^(?:an?|the|experienced|immediate)\s+", "", t)
    t = re.split(r"(?i)\s+(?:at|@|in|with|for|–|—|-|\|)\s+|[|!(\[]|\.\s|,\s|\s#|:\s", t)[0]
    t = re.sub(r"(?i)\b(role|position|opening|openings|vacancy|vacancies|job)\b\s*$", "", t)
    t = re.split(r"(?i)\s+(?:to\s+join|who\s+(?:can|will|is)|with\s+\d|having|ready\s+to)\b", t)[0]
    half = len(t) // 2  # LinkedIn copies sometimes repeat the line: "AI EngineerAI Engineer"
    if len(t) % 2 == 0 and t[:half].strip() and t[:half] == t[half:]:
        t = t[:half]
    # a duty sentence ("Handle the complete sales cycle…") is not a title
    if re.match(r"(?i)^(?:handle|manage|drive|develop|build|create|support|work|ensure|lead|own|assist|"
                r"coordinate|maintain|conduct|prepare|identify|generate|achieve)\b", t) and len(t.split()) > 4:
        return ""
    # a field label glued onto the end of the title ("Talent Acquisition Specialist Location")
    t = re.sub(r"(?i)\s+(?:location|experience|salary|ctc|work\s+mode|job\s+type|qualification|"
               r"eligibility|skills?|openings?)\s*$", "", t)
    t = re.sub(r"[#*]", "", t).strip(" .-–:")
    if not t or len(t) > 70 or len(t) < 3 or not kb.is_role_like(t):
        return ""
    words = []
    for w in t.split():
        lw = w.lower()
        if lw in ("ai", "ml", "qa", "aws", "gcp", "sde", "bde", "bdm", "hr", "it", "ui", "ux", "sdr", "bdr", "kam"):
            words.append(w.upper())
        elif w.isupper() and len(w) > 3:
            words.append(w.capitalize())
        elif w[:1].islower():
            words.append(w.capitalize())
        else:
            words.append(w)
    return " ".join(words)


def extract_title(text: str) -> str:
    patterns = [
        r"(?im)^\s*[^\w\n]*\s*(?:job\s*title|role|position|designation|job\s*role|opening|profile|post)\s*[:\-–]\s*(.+)$",
        r"(?i)(?:we(?:'|’)?re\s+hiring|we\s+are\s+hiring|now\s+hiring|urgent(?:ly)?\s+hiring|hiring\s+alert|"
        r"#hiring|hiring|looking\s+for|urgent\s+requirement|requirement)\s*(?:for|of)?\s*[:\-–!|]*\s*"
        r"(?:an?\s+|the\s+)?([^\n]{3,90})",
    ]
    for pat in patterns:
        for m in re.finditer(pat, text or ""):
            t = clean_title(m.group(1))
            if t:
                return t
    for line in [l for l in (text or "").splitlines() if l.strip()][:10]:
        if kb.is_role_like(line) and len(line) < 90 and not EMAIL_RE.search(line):
            t = clean_title(line)
            if t:
                return t
    return ""


def extract_location(text: str) -> tuple[str, list[str]]:
    """Return (location_text, canonical_cities)."""
    m = re.search(r"(?im)^\s*[^\w\n]*\s*(?:job\s*)?(?:work\s*)?(?:location|locations|place|city|base location|"
                  r"work mode)\s*[:\-–]\s*(.+)$", text or "")
    if not m:
        m = re.search(r"📍\s*(.+)", text or "")
    if m:
        loc = _clean(m.group(1))[:80]
        cities = kb.detect_cities(loc)
        if cities:
            return loc, cities
    m = re.search(r"(?i)\b(?:based (?:in|out of)|located in|office in|work from|location\s*-)\s+([A-Za-z ,/&]{3,60})",
                  text or "")
    if m and kb.detect_cities(m.group(1)):
        return _clean(m.group(1)), kb.detect_cities(m.group(1))
    cities = kb.detect_cities(text or "")
    return (", ".join(cities[:3]) if cities else ""), cities[:3]


_NUM = r"(\d{1,2}(?:\.\d)?)"
_YRS = r"(?:years?|yrs?|yoe|y\.o\.e)"


def parse_experience(text: str) -> tuple:
    """
    Return (min_years, max_years, label).
    max_years is None for open-ended requirements ("5+ years").
    (None, None, "") when the post does not state experience.
    """
    text = text or ""
    labelled = re.search(r"(?im)^\s*[^\w\n]*\s*(?:experience|exp|work experience|experience required|"
                         r"required experience|yoe)\s*(?:required)?\s*[:\-–]\s*(.+)$", text)
    candidates = []
    if labelled:
        candidates.append(labelled.group(1))
    # sentences mentioning experience come next, then the whole text
    candidates += [s for s in re.split(r"[\n.;]", text) if re.search(r"(?i)exp", s)]
    candidates.append(text)
    for s in candidates:
        if re.search(r"(?i)\bfreshers?\b", s) and not re.search(r"\d\s*(?:\+|-|–|to)?\s*\d*\s*" + _YRS, s, re.I):
            return 0.0, 0.0, "Fresher"
        m = re.search(_NUM + r"\s*\+?\s*(?:-|–|—|to)\s*" + _NUM + r"\s*\+?\s*" + _YRS, s, re.I) or \
            (s is candidates[0] and labelled and re.search(_NUM + r"\s*(?:-|–|—|to)\s*" + _NUM, s))
        if m:
            lo, hi = float(m.group(1)), float(m.group(2))
            if lo > hi:
                lo, hi = hi, lo
            return lo, hi, f"{lo:g}–{hi:g} yrs"
        m = re.search(_NUM + r"\s*\+\s*" + _YRS, s, re.I) or \
            re.search(r"(?i)(?:minimum|min\.?|at\s*least|atleast|over|more\s+than)\s*(?:of\s*)?" + _NUM +
                      r"\s*\+?\s*" + _YRS, s)
        if m:
            lo = float(m.group(1))
            return lo, None, f"{lo:g}+ yrs"
        m = re.search(_NUM + r"\s*" + _YRS, s, re.I)
        if m and (s is not text or re.search(r"(?i)exp", text[max(0, m.start() - 60):m.end() + 60])):
            v = float(m.group(1))
            return v, v, f"{v:g} yrs"
    return None, None, ""


def detect_seniority(title: str, exp_min) -> str:
    t = (title or "").lower()
    if re.search(r"\b(intern|trainee|fresher|graduate)\b", t):
        return "Entry"
    if re.search(r"\b(head|director|vp|vice president|chief|cxo|principal)\b", t):
        return "Executive"
    if re.search(r"\b(manager|lead|team lead|supervisor|architect)\b", t):
        return "Lead / Manager"
    if re.search(r"\b(senior|sr\.?)\b", t):
        return "Senior"
    if re.search(r"\b(junior|jr\.?|associate)\b", t):
        return "Junior"
    if exp_min is None:
        return "Mid"
    if exp_min < 2:
        return "Junior"
    if exp_min < 5:
        return "Mid"
    if exp_min < 8:
        return "Senior"
    return "Lead / Manager"


SENIORITY_RANK = {"Entry": 0, "Junior": 1, "Mid": 2, "Senior": 3, "Lead / Manager": 4, "Executive": 5}


def _section_lines(text: str) -> dict:
    """Group post lines by responsibilities / required / preferred headings."""
    out = {"responsibilities": [], "required": [], "preferred": [], "other": []}
    current = "other"
    for raw in (text or "").splitlines():
        line = _clean(raw).strip("•-*–✔✓➤▶► ")
        if not line:
            continue
        head = re.sub(r"[^a-z&'’ \-]", "", line.lower()).strip()
        matched = None
        if len(head) <= 45:
            for sec, pat in SECTION_PATTERNS.items():
                if re.fullmatch(pat + r"\s*", head):
                    matched = sec
                    break
        if matched:
            current = matched
            continue
        inline = re.match(r"(?i)^(" + "|".join(SECTION_PATTERNS.values()) + r")\s*[:\-–]\s*(.+)$", line)
        if inline:
            head2 = inline.group(1).lower()
            sec = next(s for s, p in SECTION_PATTERNS.items() if re.fullmatch(p, head2))
            out[sec].append(inline.group(inline.lastindex))
            continue
        out[current].append(line)
    return out


def analyze_jd(text: str) -> dict:
    """Complete analysis of one job post."""
    text = text or ""
    emails = extract_emails(text)
    poster_name, designation, body = split_poster_header(text)
    # title and company come from the post itself — never from the recruiter's own headline
    title = extract_title(body)
    company, company_source = extract_company(body, emails)
    if company_source != "post":
        head_co = _headline_company(designation)
        domains = " ".join(e.split("@", 1)[1].lower() for e in emails)
        if head_co and re.sub(r"[^a-z]", "", head_co.lower())[:6] in re.sub(r"[^a-z]", "", domains):
            company, company_source = head_co, "headline"  # recruiter's employer, confirmed by the email
    location, cities = extract_location(text)
    exp_min, exp_max, exp_label = parse_experience(text)
    sections = _section_lines(text)
    all_lines = sections["responsibilities"] + sections["required"] + sections["preferred"] + sections["other"]

    # the poster's own headline ("Talent Acquisition at X") is not a job requirement
    skill_text = "\n".join(l for l in text.splitlines() if not POSTER_HEADLINE_RE.match(l.strip()))
    skills_all = kb.find_skills(skill_text)
    required_text = " ".join(sections["required"] + sections["responsibilities"]) or text
    preferred_text = " ".join(sections["preferred"])
    flat = [s for cat in skills_all.values() for s in cat]
    preferred_skills = [s for s in flat if preferred_text and kb.skill_supported(s, preferred_text)
                        and not kb.skill_supported(s, required_text)]
    required_skills = [s for s in flat if s not in preferred_skills]

    def lines_matching(pattern):
        return [l for l in all_lines if re.search(pattern, l, re.I)][:8]

    tv = kb.token_vector(skill_text)
    repeated = [t for t, c in sorted(tv.items(), key=lambda kv: -kv[1]) if c >= 2 and len(t) > 2][:15]
    bigrams = {}
    toks = kb.tokens(text)
    for a, b in zip(toks, toks[1:]):
        bigrams[f"{a} {b}"] = bigrams.get(f"{a} {b}", 0) + 1
    phrases = [p for p, c in sorted(bigrams.items(), key=lambda kv: -kv[1]) if c >= 2][:10]

    return {
        "recruiter_name": extract_recruiter_name(text) or poster_name,
        "recruiter_designation": designation,
        "emails": emails,
        "email": emails[0] if emails else "",
        "company": company,
        "company_source": company_source,
        "job_title": title,
        "location": location,
        "cities": cities,
        "experience": exp_label,
        "exp_min": exp_min,
        "exp_max": exp_max,
        "seniority": detect_seniority(title, exp_min),
        "responsibilities": sections["responsibilities"][:15],
        "required_skills": required_skills,
        "preferred_skills": preferred_skills,
        "technologies": skills_all["technical"] + skills_all["ai"],
        "crm_requirements": skills_all["crm"] + lines_matching(r"\bcrm\b")[:3],
        "industry": kb.find_industries(text),
        "team_responsibilities": lines_matching(r"\bteam\b"),
        "leadership_requirements": lines_matching(r"\b(lead (?:a|the|and)\b|team lead|leadership|mentor|"
                                                  r"manag(?:e|ing) a team|team handling|supervis|people manag|coach)"),
        "sales_requirements": lines_matching(r"\b(sales|selling|business development|closing|deal)"),
        "customer_requirements": lines_matching(r"\b(customer|client|account)"),
        "revenue_requirements": lines_matching(r"\b(revenue|target|quota|achiev)"),
        "education": [l for l in all_lines if kb.DEGREE_PATTERN.search(l)][:4],
        "other_requirements": lines_matching(r"\b(immediate|notice|two[- ]wheeler|bike|travel|shift|language|"
                                             r"english|hindi|kannada|tamil|telugu)")[:5],
        "repeated_keywords": repeated,
        "important_phrases": phrases,
        "concepts": kb.concept_vector(skill_text),
        "families": kb.family_vector(skill_text),
        "is_job_post": bool(title or emails) and bool(
            title or re.search(r"(?i)hiring|opening|vacanc|apply|job|role|position|resume|cv", text)),
        "text": text.strip(),
    }


def format_jd_analysis(a: dict) -> str:
    def lst(items, n=8):
        items = [i for i in (items or []) if i]
        return ", ".join(items[:n]) if items else "—"

    lines = [
        f"Recruiter: {a.get('recruiter_name') or '— (will use “Dear Hiring Team”)'}",
        f"Recruiter Designation: {a.get('recruiter_designation') or '—'}  (not used as the job title)",
        f"Email(s): {lst(a.get('emails'))}",
        f"Company: {a.get('company') or '—'}" + {
            "email_domain": " (guessed from email domain — not named in the email)",
            "headline": " (recruiter's employer, confirmed by email domain)"}.get(a.get("company_source"), ""),
        f"Job Title: {a.get('job_title') or '— (not detected)'}",
        f"Location: {a.get('location') or '—'}   Cities: {lst(a.get('cities'))}",
        f"Experience: {a.get('experience') or '— (not stated)'}   Seniority: {a.get('seniority')}",
        f"Required Skills: {lst(a.get('required_skills'), 15)}",
        f"Preferred Skills: {lst(a.get('preferred_skills'), 10)}",
        f"Technologies: {lst(a.get('technologies'), 12)}",
        f"Industry: {lst(a.get('industry'))}",
        f"Key Concepts: {lst(sorted(a.get('concepts', {}), key=lambda k: -a['concepts'][k]), 8)}",
        f"Repeated Keywords: {lst(a.get('repeated_keywords'), 12)}",
        f"Important Phrases: {lst(a.get('important_phrases'), 6)}",
    ]
    for label, key in (("Responsibilities", "responsibilities"), ("Sales Requirements", "sales_requirements"),
                       ("Customer/Client Requirements", "customer_requirements"),
                       ("Revenue/Target Requirements", "revenue_requirements"),
                       ("Leadership Requirements", "leadership_requirements"),
                       ("Education", "education"), ("Other Requirements", "other_requirements")):
        items = a.get(key) or []
        if items:
            lines.append(f"{label}:")
            lines += [f"  • {i}" for i in items[:6]]
    return "\n".join(lines)
