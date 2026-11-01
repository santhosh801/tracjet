"""
Generates a personalised recruiter email from:

    example subject + example Gmail draft (style / structure / tone)
  + candidate profile                    (the ONLY source of candidate facts)
  + analysed LinkedIn JD                 (job requirements)
  + candidate settings                   (phone, CTC, availability, signature)

The local generator never copies factual sentences from the example draft:
example sentences are reused only when they contain no claims, numbers,
names or unsupported skills.  If an OpenAI key is configured and enabled the
draft can be written by the model instead, but the closing/signature/CTC
block is always rebuilt deterministically and the result must pass the
quality checks, otherwise the local draft is used.
"""
import hashlib
import json
import re

import knowledge as kb
from template_matcher import profile_fact_text

CLOSING_SENTENCE = ("I’ve attached my resume for your review and would welcome the opportunity "
                    "to discuss the role.")
DEFAULT_EXPECTED_CTC = "Negotiable"
DEFAULT_AVAILABILITY = "Immediate Joiner"
HIGHLIGHT_COUNT = 5

GREETING_RE = re.compile(r"^\s*(dear|hi|hello|greetings|good morning|good afternoon|good evening)\b", re.I)
SIGNOFF_RE = re.compile(r"^\s*(kind regards|best regards|warm regards|regards|sincerely|thanks\s*(?:&|and)\s*regards|"
                        r"thank you|thanks|best|cheers|yours (?:sincerely|truly|faithfully))\s*[,!.]?\s*$", re.I)
BULLET_RE = re.compile(r"^\s*([•●▪◦▶►➢➤✓✔✦■\-\*–]|\d{1,2}[.)])\s+(.*)$")
CLAIM_RE = re.compile(
    r"\b(i have|i've|i had|i am a|i'm a|my experience|experience in|experience with|i led|i managed|i built|"
    r"i developed|i worked|i handled|skilled|expertise|proficient|track record|years?|i achieved|i delivered|"
    r"i drove|i spearheaded|background in|hands-on|certified|my role|currently|previously)\b", re.I)
PLACEHOLDER_TOKENS = {
    "job title": "title", "role": "title", "position": "title", "job role": "title",
    "company": "company", "company name": "company", "organisation": "company", "organization": "company",
    "recruiter name": "recruiter", "recruiter": "recruiter", "hiring manager": "recruiter",
    "name": "candidate", "your name": "candidate", "candidate name": "candidate", "my name": "candidate",
    "experience": "experience", "years": "experience", "phone": "phone", "phone number": "phone",
    "mobile": "phone", "availability": "availability", "notice period": "availability",
    "location": "location", "city": "location",
}
PLACEHOLDER_RE = re.compile(r"[\[{<]\s*([A-Za-z _]{2,25})\s*[\]}>]")


# ── Candidate settings → fixed lines ─────────────────────────────────────
def ctc_line(candidate: dict) -> str:
    expected = (candidate.get("expected_ctc") or "").strip() or DEFAULT_EXPECTED_CTC
    availability = (candidate.get("availability") or "").strip() or DEFAULT_AVAILABILITY
    current = (candidate.get("current_ctc") or "").strip()
    if candidate.get("include_current_ctc") and current:
        return f"Current CTC: {current} | Expected CTC: {expected} | Availability: {availability}"
    return f"Expected CTC: {expected} | Availability: {availability}"


def signature_block(candidate: dict) -> str:
    lines = ["Kind Regards,", (candidate.get("name") or "").strip()]
    phone = (candidate.get("phone") or "").strip()
    if phone:
        lines.append(phone)
    extra = (candidate.get("extra_signature") or "").strip()
    if extra:
        lines += [l.rstrip() for l in extra.splitlines()]
    return "\n".join(l for l in lines if l is not None) + "\n\n" + ctc_line(candidate)


def closing_block(candidate: dict) -> str:
    return CLOSING_SENTENCE + "\n\n" + signature_block(candidate)


# ── Example-draft style analysis ─────────────────────────────────────────
def analyze_style(example_subject: str, example_body: str) -> dict:
    body = (example_body or "").replace("\r\n", "\n")
    lines = body.split("\n")
    style = {"greeting": "Dear", "uses_bullets": False, "bullet_marker": "•", "numbered": False,
             "label_style": False, "label_sep": " – ", "bullet_period": False, "heading": "",
             "pre_paragraphs": [], "post_paragraphs": [], "opening_kind": "", "subject": example_subject or ""}
    first = next((l for l in lines if l.strip()), "")
    g = GREETING_RE.match(first)
    if g:
        style["greeting"] = g.group(1).strip().title() if g.group(1).lower() != "hi" else "Hi"

    bullet_idx = [i for i, l in enumerate(lines) if BULLET_RE.match(l)]
    if bullet_idx:
        style["uses_bullets"] = True
        m = BULLET_RE.match(lines[bullet_idx[0]])
        marker = m.group(1)
        style["numbered"] = bool(re.match(r"\d", marker))
        style["bullet_marker"] = marker if not style["numbered"] else "1."
        items = [BULLET_RE.match(lines[i]).group(2) for i in bullet_idx]
        labelled = [it for it in items if re.match(r"^[^:–\-]{2,40}(:|\s[–-]\s)", it)]
        style["label_style"] = len(labelled) >= max(1, len(items) // 2)
        if labelled and ":" in labelled[0].split(" ")[0:6].__str__():
            style["label_sep"] = ": "
        style["bullet_period"] = sum(it.rstrip().endswith(".") for it in items) > len(items) / 2
        prev = next((lines[j].strip() for j in range(bullet_idx[0] - 1, -1, -1) if lines[j].strip()), "")
        if prev.endswith(":") and not GREETING_RE.match(prev):
            style["heading"] = prev

    # paragraphs before / after the bullet block, excluding greeting, heading and sign-off
    paragraphs, cur = [], []
    for i, l in enumerate(lines + [""]):
        if l.strip():
            cur.append((i, l.strip()))
        elif cur:
            paragraphs.append(cur)
            cur = []
    first_b = bullet_idx[0] if bullet_idx else None
    last_b = bullet_idx[-1] if bullet_idx else None
    signed = False
    for para in paragraphs:
        text = " ".join(t for _, t in para)
        idx = para[0][0]
        if signed or SIGNOFF_RE.match(para[0][1]):
            signed = True
            continue
        if GREETING_RE.match(text) and len(text.split()) <= 6:
            continue
        if text == style["heading"] or (bullet_idx and BULLET_RE.match(para[0][1])):
            continue
        if first_b is None or idx < first_b:
            style["pre_paragraphs"].append(text)
        elif idx > last_b:
            style["post_paragraphs"].append(text)
    opening = " ".join(style["pre_paragraphs"][:1]).lower()
    if "came across" in opening or "saw your" in opening:
        style["opening_kind"] = "came_across"
    elif "writing to" in opening or "express my interest" in opening:
        style["opening_kind"] = "writing"
    elif "excited" in opening or "thrilled" in opening:
        style["opening_kind"] = "excited"
    return style


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text or "") if s.strip()]


def safe_example_sentences(paragraphs: list[str], allowed_text: str, extra_allowed_words=()) -> list[str]:
    """Example sentences that are pure style — no facts that could be untrue for this candidate/job."""
    ok_caps = {"i", "linkedin", "thank", "thanks"} | {w.lower() for w in extra_allowed_words}
    out = []
    for para in paragraphs:
        for s in _sentences(para):
            words = s.split()
            if not 4 <= len(words) <= 30:
                continue
            if re.search(r"\d|%|₹|\$", s) or CLAIM_RE.search(s) or PLACEHOLDER_RE.search(s):
                continue
            if re.search(r"(?i)attach|resume|\bcv\b|regards|ctc|notice period|joiner|available", s):
                continue
            if any(w[0].isupper() and re.sub(r"\W", "", w).lower() not in ok_caps for w in words[1:]):
                continue
            vocab_hits = [k for k in kb.all_skill_vocab() if kb.skill_supported(k, s)]
            if any(not kb.skill_supported(k, allowed_text) for k in vocab_hits):
                continue
            if kb.is_role_like(s) and not re.search(r"(?i)\b(this|the) (role|position|opportunity)\b", s):
                continue
            out.append(s)
    return out


def _safe_fragment(text: str, allowed_text: str) -> bool:
    """Short example fragments (e.g. the highlight heading) — reusable if they hold no facts or names."""
    if not text or re.search(r"\d|%|₹|\$", text) or PLACEHOLDER_RE.search(text):
        return False
    if any(w[0].isupper() and re.sub(r"\W", "", w).lower() not in ("i", "linkedin") for w in text.split()[1:]):
        return False
    vocab = [k for k in kb.all_skill_vocab() if kb.skill_supported(k, text)]
    return all(kb.skill_supported(k, allowed_text) for k in vocab)


# ── Highlights (candidate evidence ranked against the JD) ────────────────
def _jaccard(a: str, b: str) -> float:
    ta, tb = set(kb.tokens(a)), set(kb.tokens(b))
    return len(ta & tb) / len(ta | tb) if ta and tb else 0.0


PRODUCTION_RE = re.compile(r"(?i)\b(production|live|deployed|deployment|enterprise|clients?|customers?|users|"
                           r"uptime|released?|shipped|delivered|business units?)\b")


def _is_heading_line(text: str) -> bool:
    """Resume sub-headings ("Full-Stack Web Development, UI/UX & AI Integration") are not achievements."""
    words = [w for w in re.findall(r"[A-Za-z][\w/\-]*", text or "") if w.lower() not in ("and", "of", "the", "for", "to", "in")]
    if not words or re.search(r"\d", text or ""):
        return False
    return sum(w[0].isupper() for w in words) / len(words) >= 0.75


def _trim(text: str, limit: int = 220) -> str:
    t = re.sub(r"\s+", " ", text).strip().rstrip(".;,")
    if len(t) <= limit:
        return t
    cut = max(t.rfind(", ", 0, limit), t.rfind("; ", 0, limit), t.rfind(" and ", 0, limit))
    return t[:cut].rstrip(" ,;") if cut > 60 else t[:limit].rsplit(" ", 1)[0]


def select_highlights(profile: dict, jd: dict, n: int = HIGHLIGHT_COUNT) -> list[dict]:
    """
    Rank every piece of resume evidence by relevance to THIS JD and pick the
    top n distinct items.  Text is always taken from the resume/profile.
    """
    jd_conc = jd.get("concepts") or {}
    jd_skills = (jd.get("required_skills") or []) + (jd.get("preferred_skills") or [])
    jd_kw = set(jd.get("repeated_keywords") or []) | set(kb.tokens(" ".join(jd.get("responsibilities") or [])))
    summary_sentences = set(_sentences(profile.get("summary") or ""))
    scored = []
    for ev in dict.fromkeys(profile.get("evidence") or []):
        if _is_heading_line(ev):
            continue
        ev_conc = kb.concept_vector(ev)
        concept_score = sum(min(jd_conc.get(c, 0), 3) for c in ev_conc)
        skill_hits = [s for s in jd_skills if kb.skill_supported(s, ev)]
        kw_score = 0.4 * len(set(kb.tokens(ev)) & jd_kw)
        relevance = concept_score + 2 * len(skill_hits) + kw_score
        if relevance > 0 and PRODUCTION_RE.search(ev):  # shipped, real-world work beats coursework
            relevance += 0.75
        if ev in summary_sentences:  # concrete experience lines beat the generic summary
            relevance *= 0.4
        shared = [c for c in ev_conc if c in jd_conc]
        label = max(shared, key=lambda c: (ev_conc[c], jd_conc[c])) if shared else \
            (max(ev_conc, key=ev_conc.get) if ev_conc else "")
        quantified = bool(re.search(r"\d", ev)) and ev not in summary_sentences
        scored.append({"text": _trim(ev), "label": label, "relevance": round(relevance, 2),
                       "quantified": quantified, "source": "resume"})
    scored.sort(key=lambda h: (-(h["relevance"] + (0.75 if h["quantified"] and h["relevance"] > 0 else 0)), len(h["text"])))

    chosen, used_labels = [], {}
    pool = list(scored)
    while pool and len(chosen) < n:
        best, best_val = None, None
        for h in pool:
            if any(_jaccard(h["text"], c["text"]) > 0.6 for c in chosen):
                continue
            penalty = 0.6 ** used_labels.get(h["label"], 0)
            val = (h["relevance"] + (0.75 if h["quantified"] and h["relevance"] > 0 else 0)) * penalty
            if best_val is None or val > best_val:
                best, best_val = h, val
        if best is None:
            break
        pool.remove(best)
        chosen.append(best)
        used_labels[best["label"]] = used_labels.get(best["label"], 0) + 1

    if len(chosen) < n:  # resume has few bullet lines — add truthful skill-based lines
        skills = [s for s in (profile.get("skills") or []) if any(s.lower() == j.lower() for j in jd_skills)]
        skills += [s for s in (profile.get("skills") or []) if s not in skills]
        for i in range(0, len(skills), 3):
            if len(chosen) >= n:
                break
            group = skills[i:i + 3]
            if group:
                rel = sum(1 for s in group if s in jd_skills)
                chosen.append({"text": "Skilled in " + _join(group), "label": "Skills", "relevance": rel,
                               "quantified": False, "source": "skills"})
    return chosen[:n]


def _join(items: list[str]) -> str:
    items = [i for i in items if i]
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def _skill_phrase(s: str) -> str:
    if s not in kb.BUSINESS_SKILLS:
        return s
    return " ".join(w.lower() if w[:1].isupper() and w[1:].islower() else w for w in s.split())


def _a_an(word: str) -> str:
    return "an" if (word or "x")[0].lower() in "aeiou" else "a"


def _format_bullet(h: dict, style: dict, i: int) -> str:
    text = h["text"][0].upper() + h["text"][1:] if h["text"] else h["text"]
    if style.get("label_style") and h.get("label") and h["label"] != "Skills":
        text = f"{h['label']}{style.get('label_sep', ' – ')}{text}"
    if style.get("bullet_period") and not text.endswith("."):
        text += "."
    marker = f"{i}." if style.get("numbered") else style.get("bullet_marker", "•")
    return f"{marker} {text}"


# ── Subject adaptation ───────────────────────────────────────────────────
def _fill_placeholders(text: str, values: dict) -> str:
    def rep(m):
        key = PLACEHOLDER_TOKENS.get(m.group(1).strip().lower())
        return values.get(key, "") if key else m.group(0)
    return PLACEHOLDER_RE.sub(rep, text or "")


def adapt_subject(example_subject: str, jd: dict, profile: dict, candidate: dict, template: dict) -> str:
    title = jd.get("job_title") or ""
    # never put the template's role in the subject as if it were the advertised job
    role = title or "the Advertised Opportunity"
    exp = profile.get("total_experience") or ""
    availability = (candidate.get("availability") or "").strip() or DEFAULT_AVAILABILITY
    company = jd.get("company") or ""
    values = {"title": role, "company": company, "candidate": candidate.get("name", ""), "experience": exp,
              "availability": availability, "phone": candidate.get("phone", ""), "recruiter": jd.get("recruiter_name", ""),
              "location": ", ".join(jd.get("cities") or [])}
    subject = (example_subject or "").strip()
    if not subject:
        parts = [f"Application for {role}" if role else "Application", f"{exp} Experience" if exp else "", availability]
        return " | ".join(p for p in parts if p)
    if PLACEHOLDER_RE.search(subject):
        filled = _fill_placeholders(subject, values)
        filled = re.sub(r"\s*([|–-])\s*(?=[|–-]|$)", "", filled)
        return re.sub(r"\s{2,}", " ", filled).strip(" |–-")

    allowed = {w.lower() for w in (candidate.get("name", "") + " " + company + " " + role).split()}
    pieces = re.split(r"(\s*\|\s*|\s+[–—-]\s+|:\s+)", subject)
    out, role_done = [], False
    for piece in pieces:
        if re.fullmatch(r"\s*\|\s*|\s+[–—-]\s+|:\s+", piece or ""):
            out.append(piece)
            continue
        seg = piece.strip()
        low = seg.lower()
        if not seg:
            continue
        if re.search(r"\d+(?:\.\d+)?\s*\+?\s*(?:years?|yrs?)", low):
            if exp:
                unit = "Yrs" if re.search(r"yrs", low) else ("Years" if re.search(r"Years", seg) else "years")
                num = re.match(r"[\d.]+\+?", exp)
                out.append(re.sub(r"\d+(?:\.\d+)?\s*\+?\s*(?:years?|yrs?)", (num.group(0) if num else exp) + " " + unit,
                                  seg, count=1, flags=re.I))
            continue
        if re.search(r"immediate|joiner|notice|available|availability", low):
            out.append(availability)
            continue
        tmpl_words = kb.tokens(template.get("name", "") + " " + template.get("role_category", ""))
        if not role_done and (kb.is_role_like(seg) or (tmpl_words and len(set(kb.tokens(seg)) & set(tmpl_words)) >= 1)):
            prefix = re.match(r"(?i)^((?:application|applying|interest(?:ed)?|candidature|re)"
                              r"(?:\s+(?:for|in|to))?\s*:?\s*(?:the\s+)?)", seg)
            new = (prefix.group(1) if prefix else "") + role
            if re.search(r"(?i)\s(?:at|@)\s", seg) and company:
                new += f" at {company}"
            elif re.search(r"(?i)\brole\b", seg) and not re.search(r"(?i)\brole\b", new):
                new += " Role"
            out.append(new)
            role_done = True
            continue
        # any other segment is kept only if it carries no facts (numbers, names, unsupported skills)
        if re.search(r"\d|%", seg):
            continue
        caps = [w for w in seg.split()[1:] if w[:1].isupper() and w.lower() not in allowed]
        vocab = [k for k in kb.all_skill_vocab() if kb.skill_supported(k, seg)]
        allowed_facts = profile_fact_text(profile)
        jd_skill_set = set((jd.get("required_skills") or []) + (jd.get("preferred_skills") or []))
        if any(not kb.skill_supported(k, allowed_facts) or k not in jd_skill_set for k in vocab):
            continue
        if caps and not vocab:
            continue
        out.append(seg)
    subject = "".join(out)
    subject = re.sub(r"^(\s*\|\s*|\s+[–—-]\s+|:\s+)+|(\s*\|\s*|\s+[–—-]\s+|:\s+)+$", "", subject)
    subject = re.sub(r"(\s*\|\s*|\s+[–—-]\s+)(?=(\s*\|\s*|\s+[–—-]\s+))", "", subject).strip()
    if role and role.lower() not in subject.lower():
        subject = f"{role} | {subject}" if subject else f"Application for {role}"
    return subject


# ── Body composition ─────────────────────────────────────────────────────
def _pick(options: list[str], key: str) -> str:
    h = int(hashlib.md5(key.encode("utf-8")).hexdigest(), 16)
    return options[h % len(options)]


def compose_local(candidate: dict, profile: dict, jd: dict, template: dict, highlights: list[dict],
                  resume_text: str = "") -> tuple[str, str, dict]:
    style = analyze_style(template.get("example_subject", ""), template.get("example_body", ""))
    allowed = profile_fact_text(profile, resume_text)
    title = jd.get("job_title") or ""
    # a company guessed from the email domain ("Randstadusa") is not named in the email
    company = "" if jd.get("company_source") == "email_domain" else (jd.get("company") or "")
    recruiter = jd.get("recruiter_name") or ""
    if recruiter.isupper():
        recruiter = recruiter.title()
    key = (jd.get("email") or "") + title + company

    greeting = f"{style['greeting']} {recruiter}," if recruiter else f"{style['greeting']} Hiring Team,"

    if company:
        role_ref = f"the {title} role" if title else "the advertised opportunity"
    else:  # never invent or leave a gap for the company — refer to the advertised opening instead
        role_ref = f"the advertised {title} opportunity" if title else "the advertised opportunity"
    at_company = f" at {company}" if company else ""
    openings = {
        "came_across": f"I came across your LinkedIn post for {role_ref}{at_company} and would like to be considered for it.",
        "writing": f"I am writing to express my interest in {role_ref}{at_company}, which I saw on LinkedIn.",
        "excited": f"I was excited to see your LinkedIn post for {role_ref}{at_company} and would like to apply.",
    }
    opening = openings.get(style["opening_kind"]) or _pick(list(openings.values()), key)
    if not company:
        # no company in the post — keep it warm without naming one
        opening += " " + _pick([
            "I would really like to be part of your organisation and contribute to its growth.",
            "I would be glad to join your team and add value from day one.",
            "Being part of your organisation would be a great opportunity for me to contribute and grow.",
        ], key)
    safe_pre = safe_example_sentences(style["pre_paragraphs"], allowed)
    if safe_pre:
        opening += " " + safe_pre[0]

    # introduction — only facts from the profile
    cur_role = (profile.get("current_role") or "").strip()
    exp = (profile.get("total_experience") or "").strip()
    jd_skills = (jd.get("required_skills") or []) + (jd.get("preferred_skills") or [])
    supported = [s for s in jd_skills if kb.skill_supported(s, allowed)]
    # business/technical skills read better in the intro than tool names
    focus = []
    for s in sorted(supported, key=lambda s: (s in kb.CRM_TOOLS or s in kb.GENERAL_TOOLS or s in kb.AI_TOOLS,
                                              supported.index(s))):
        if not any(s.lower() in f.lower() or f.lower() in s.lower() for f in focus):
            focus.append(s)
    focus = focus[:3]
    intro = "I am " + (f"{_a_an(cur_role)} {cur_role}" if cur_role else "a professional")
    if exp:
        intro += f" with {exp} of experience"
    if focus:
        intro += (" in " if exp else " experienced in ") + _join([_skill_phrase(s) for s in focus])
    intro += "."

    parts = [greeting, "", opening, "", intro]
    if style["uses_bullets"]:
        heading = style["heading"] if _safe_fragment(style["heading"], allowed) else ""
        parts += ["", heading or "Key highlights relevant to this role:"]
        parts += [_format_bullet(h, style, i + 1) for i, h in enumerate(highlights[:HIGHLIGHT_COUNT])]
    else:
        top = [h["text"][0].lower() + h["text"][1:] if h["text"][1:2].islower() else h["text"] for h in highlights[:3]]
        if top:
            parts += ["", "Some highlights of my experience include: " + "; ".join(top) + "."]

    cand_concepts = kb.concept_vector(allowed)
    req_concepts = [c for c in sorted(jd.get("concepts") or {}, key=lambda c: -(jd.get("concepts") or {})[c])
                    if c in cand_concepts and _safe_fragment(kb.CONCEPT_PHRASES.get(c, c), allowed)][:3]
    if len(req_concepts) >= 2:
        parts += ["", "My background aligns well with your focus on "
                  f"{_join([kb.CONCEPT_PHRASES.get(c, c.lower()) for c in req_concepts])}."]
    safe_post = safe_example_sentences(style["post_paragraphs"], allowed)
    if safe_post:
        parts += ["", " ".join(safe_post[:2])]
    parts += ["", closing_block(candidate)]
    body = "\n".join(parts)
    subject = adapt_subject(template.get("example_subject", ""), jd, profile, candidate, template)
    return subject, body, style


def enforce_closing(body: str, candidate: dict) -> str:
    """Strip any model-written sign-off / CTC lines and append the configured closing block."""
    lines = (body or "").replace("\r\n", "\n").split("\n")
    out = []
    for l in lines:
        if SIGNOFF_RE.match(l):
            break
        if re.search(r"(?i)\bctc\b|notice period|availability\s*:|attached my resume|resume attached|find my resume",
                     l):
            continue
        out.append(l)
    while out and not out[-1].strip():
        out.pop()
    return "\n".join(out) + "\n\n" + closing_block(candidate)


def compose_with_openai(api_key: str, candidate: dict, profile: dict, jd: dict, template: dict,
                        highlights: list[dict], local_subject: str) -> tuple[str, str]:
    from openai import OpenAI
    client = OpenAI(api_key=api_key, timeout=25.0)
    facts = {k: profile.get(k) for k in ("name", "current_role", "total_experience", "skills", "achievements",
                                          "industries", "experience_entries", "education", "certifications")}
    prompt = f"""You write a recruiter email for a job applicant.

SOURCE-OF-TRUTH RULES (strict):
1. Candidate facts may come ONLY from CANDIDATE PROFILE. Never invent skills, companies, titles, numbers,
   achievements, certifications or years of experience. If the example email states a fact the profile does
   not support, do NOT reuse it.
2. Job requirements come ONLY from JOB POST.
3. The EXAMPLE EMAIL is for style, tone, structure, opening and highlight format ONLY.
4. Use exactly these {len(highlights)} highlights as the bullet points (you may lightly rephrase, never add facts):
{json.dumps([h['text'] for h in highlights], ensure_ascii=False)}
5. Greeting: "{'Dear ' + jd['recruiter_name'] if jd.get('recruiter_name') else 'Dear Hiring Team'},"
6. Never output placeholders like [Company Name]. Do not write a sign-off, signature, CTC or availability —
   they are appended automatically. Do not mention the resume attachment.
   If the company is unknown, never name or guess one — refer to "the advertised opportunity" (or "the
   advertised <job title> opportunity") instead.
{('7. Candidate drafting instructions: ' + candidate.get('drafting_instructions')) if candidate.get('drafting_instructions') else ''}

CANDIDATE PROFILE:
{json.dumps(facts, ensure_ascii=False)[:5000]}

JOB POST (title: {jd.get('job_title') or 'unknown'}, company: {jd.get('company') or 'unknown'}):
{(jd.get('text') or '')[:4000]}

EXAMPLE SUBJECT: {template.get('example_subject', '')}
EXAMPLE EMAIL:
{template.get('example_body', '')[:3000]}

Return JSON: {{"subject": "...", "body": "..."}}. Suggested subject: {local_subject}"""
    resp = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}],
                                          response_format={"type": "json_object"})
    data = json.loads(resp.choices[0].message.content)
    subject = (data.get("subject") or local_subject).strip()
    body = enforce_closing(data.get("body") or "", candidate)
    return subject, body


def compose_email(candidate: dict, profile: dict, jd: dict, template: dict, resume_text: str = "",
                  api_key: str = "", use_openai: bool = False) -> dict:
    highlights = select_highlights(profile, jd)
    subject, body, style = compose_local(candidate, profile, jd, template, highlights, resume_text)
    result = {"subject": subject, "body": body, "highlights": highlights, "uses_bullets": style["uses_bullets"],
              "mode": "local"}
    if use_openai and api_key and api_key.strip().startswith("sk-"):
        try:
            from quality import check_email_content
            ai_subject, ai_body = compose_with_openai(api_key, candidate, profile, jd, template, highlights, subject)
            issues = check_email_content(
                {"generated_subject": ai_subject, "generated_body": ai_body, **{k: jd.get(k) for k in
                 ("email", "company", "job_title", "recruiter_name", "cities")}},
                candidate, profile, resume_text, template, highlights, style["uses_bullets"])
            if not any(i["code"] in ("invented_skill", "invented_number", "experience_claim", "placeholder",
                                     "example_leak", "highlights_count") for i in issues):
                result.update(subject=ai_subject, body=ai_body, mode="openai")
        except Exception as e:  # fall back to the local draft
            result["openai_error"] = str(e)[:200]
    return result
