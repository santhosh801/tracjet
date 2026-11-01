"""
Email quality checks.

Each issue has a severity:
  hard — the email can never be sent until fixed (even with manual approval)
  soft — the email goes to Needs Review; the user may approve it after reviewing
"""
import json
import os
import re

import knowledge as kb
from jd_analyzer import split_poster_header
from email_composer import BULLET_RE, HIGHLIGHT_COUNT, PLACEHOLDER_RE, SIGNOFF_RE, ctc_line
from template_matcher import POOR_MATCH_THRESHOLD, profile_fact_text

EMAIL_VALID_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}$")
UNRESOLVED_RE = re.compile(r"(?i)\b(?:company name|recruiter name|job title|your name|candidate name|"
                           r"hiring manager name|insert \w+)\b|\bXXX+\b|\bTBD\b")
LOW_CANDIDATE_MATCH = 25
# job-type words in a template subject ("Part-Time / Contract") are style, not leaked facts
EMPLOYMENT_WORDS = {"part", "time", "full", "contract", "freelance", "remote", "hybrid", "flexible", "onsite",
                    "permanent", "temporary", "internship", "availability", "immediate", "joiner"}


def issue(code: str, message: str, severity: str = "soft") -> dict:
    return {"code": code, "message": message, "severity": severity}


def valid_recipient(email: str) -> bool:
    e = (email or "").strip()
    return bool(EMAIL_VALID_RE.match(e)) and "enter-email" not in e.lower() and "example." not in e.lower()


def _digits(s: str) -> str:
    return re.sub(r"\D", "", s or "")


def _content_region(body: str) -> str:
    """Body text before the sign-off (signature and CTC line are checked separately)."""
    lines = (body or "").split("\n")
    out = []
    for l in lines:
        if SIGNOFF_RE.match(l):
            break
        out.append(l)
    return "\n".join(out)


def check_email_content(record: dict, candidate: dict, profile: dict, resume_text: str, template: dict | None,
                        highlights: list | None, uses_bullets: bool, template_score: int | None = None,
                        candidate_match_pct: int | None = None) -> list[dict]:
    issues = []
    subject = (record.get("generated_subject") or "").strip()
    body = (record.get("generated_body") or "").strip()
    title = (record.get("job_title") or "").strip()
    company = (record.get("company") or "").strip()
    recruiter = (record.get("recruiter_name") or "").strip()

    if not valid_recipient(record.get("email")):
        issues.append(issue("email_invalid", "Recruiter email is missing or invalid.", "hard"))
    if not subject:
        issues.append(issue("subject_missing", "Subject is empty.", "hard"))
    if not body:
        issues.append(issue("body_missing", "Email body is empty.", "hard"))
        return issues

    full = subject + "\n" + body
    if PLACEHOLDER_RE.search(full) or UNRESOLVED_RE.search(full):
        m = PLACEHOLDER_RE.search(full) or UNRESOLVED_RE.search(full)
        issues.append(issue("placeholder", f"Unresolved placeholder: “{m.group(0)}”.", "hard"))

    # CTC / availability
    expected_line = ctc_line(candidate)
    if expected_line not in body:
        issues.append(issue("ctc_line", f"CTC/availability line must read: “{expected_line}”.", "hard"))
    current = (candidate.get("current_ctc") or "").strip()
    if not candidate.get("include_current_ctc"):
        if re.search(r"(?i)current\s+ctc", full) or (current and current.lower() in full.lower()):
            issues.append(issue("current_ctc_leak", "Current CTC appears but “Include Current CTC” is off.", "hard"))

    # Signature / candidate details
    name = (candidate.get("name") or "").strip()
    if name and name not in body:
        issues.append(issue("signature", "Candidate name missing from the signature."))
    phone = (candidate.get("phone") or "").strip()
    if phone and _digits(phone) not in _digits(body):
        issues.append(issue("signature", "Candidate phone number missing from the signature."))
    for m in re.finditer(r"\+?\d[\d\s\-()]{8,16}\d", full):
        d = _digits(m.group(0))
        if len(d) >= 10 and d != _digits(phone) and not d.endswith(_digits(phone) or "x"):
            issues.append(issue("phone_invented", f"Unknown phone number in email: {m.group(0)}", "hard"))
            break

    # Job / recruiter / company
    content = _content_region(body)
    if not title:
        issues.append(issue("title_missing", "Job title could not be detected from the post."))
    elif title.lower() not in full.lower():
        issues.append(issue("title_missing", f"Job title “{title}” is not mentioned in the subject or body."))
    analysis = record.get("jd_analysis")
    if isinstance(analysis, str):
        try:
            analysis = json.loads(analysis)
        except ValueError:
            analysis = {}
    guessed = (analysis or {}).get("company_source") == "email_domain" and \
        company == ((analysis or {}).get("company") or company)
    # the job title must come from the post, not from the recruiter's own headline/designation
    stored_title = ((analysis or {}).get("job_title") or "").strip()
    edited_by_user = bool(stored_title) and title.lower() != stored_title.lower()
    if title and record.get("jd") and not edited_by_user:
        _, designation, post_body = split_poster_header(record["jd"])
        if designation and title.lower() in designation.lower() and title.lower() not in post_body.lower():
            issues.append(issue("title_from_designation", f"Job title “{title}” is the recruiter's own designation, "
                                "not the advertised role — correct the Job Title.", "hard"))
    if company and not guessed and company.lower() not in full.lower():
        issues.append(issue("company_missing", f"Company “{company}” is not mentioned."))
    first_line = next((l for l in body.split("\n") if l.strip()), "")
    if recruiter and recruiter.split()[0].lower() not in first_line.lower():
        issues.append(issue("greeting", f"Greeting does not address the recruiter ({recruiter})."))
    if not recruiter and "hiring team" not in first_line.lower() and not re.search(r"(?i)^(dear|hi|hello)\s+\w+",
                                                                                   first_line):
        issues.append(issue("greeting", "Greeting should be “Dear Hiring Team,”."))

    # Facts must come from the resume/profile
    facts = profile_fact_text(profile, resume_text)
    claim_text = content
    for phrase in (title, company):
        if phrase:
            claim_text = re.sub(re.escape(phrase), " ", claim_text, flags=re.I)
    invented = sorted(k for k in kb.skills_in(claim_text) - kb.skills_in(facts) if k != "R")
    if invented:
        issues.append(issue("invented_skill", "Skills not supported by the resume: " + ", ".join(invented[:6])))
    nums = re.findall(r"\d+(?:\.\d+)?\s*%|[₹$]\s?\d[\d,.]*\s*(?:lpa|lakhs?|crores?|k|m)?|\d+(?:\.\d+)?\s*(?:lpa|lakhs?|"
                      r"crores?|x\b)", claim_text, re.I)
    unsupported = [n for n in nums if re.sub(r"\s", "", n).lower() not in re.sub(r"\s", "", facts).lower()]
    if unsupported:
        issues.append(issue("invented_number", "Figures not found in the resume: " + ", ".join(unsupported[:5])))
    exp_claims = re.findall(r"(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)", claim_text, re.I)
    allowed_years = set(re.findall(r"(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)", facts, re.I))
    bad_years = [y for y in exp_claims if y not in allowed_years]
    if bad_years:
        issues.append(issue("experience_claim", f"Experience claim not supported by the resume: {bad_years[0]} years."))

    # Location
    allowed_cities = set(record.get("cities") or kb.detect_cities(record.get("location") or "")) | set(
        kb.detect_cities(profile.get("location") or "")) | set(kb.detect_cities(facts))
    wrong = [c for c in kb.detect_cities(claim_text) if c not in allowed_cities]
    if wrong:
        issues.append(issue("location_mismatch", "Email mentions a location not in the job post: " + ", ".join(wrong)))

    # Template / highlights
    if template_score is not None and template_score < POOR_MATCH_THRESHOLD:
        issues.append(issue("template_poor", f"Poor template match ({template_score}%). Review the chosen template."))
    if uses_bullets:
        bullets = [l for l in content.split("\n") if BULLET_RE.match(l)]
        if len(bullets) != HIGHLIGHT_COUNT:
            issues.append(issue("highlights_count", f"Expected exactly {HIGHLIGHT_COUNT} highlights, found {len(bullets)}."))
    if highlights is not None:
        relevant = [h for h in highlights if (h.get("relevance") or 0) > 0]
        if len(relevant) < 3:
            issues.append(issue("highlights_relevance", "Fewer than 3 highlights are relevant to this JD."))
    if candidate_match_pct is not None and candidate_match_pct < LOW_CANDIDATE_MATCH:
        issues.append(issue("low_candidate_match", f"Low candidate–JD match ({candidate_match_pct}%)."))

    # Example-draft content leaking into this email (names/companies from the example)
    if template:
        ex = (template.get("example_subject") or "") + "\n" + (template.get("example_body") or "")
        ex_names = set(re.findall(r"\b([A-Z][A-Za-z]+(?:[ \t]+[A-Z][A-Za-z]+)*)\b", ex))
        known = (facts + "\n" + (record.get("jd") or "") + "\n" + title + " " + company + " " +
                 " ".join(str(candidate.get(k) or "") for k in ("name", "availability", "expected_ctc",
                                                                "extra_signature")))
        for n in ex_names:
            words = n.lower().split()
            if all(w in kb.GENERIC_CAPS or w in kb.STOPWORDS or w in kb.ROLE_WORDS or w in EMPLOYMENT_WORDS
                   for w in words):
                continue
            if any(n.lower() == s.lower() for s in kb.all_skill_vocab()):
                continue
            if n.lower() not in known.lower() and re.search(r"\b" + re.escape(n) + r"\b", full):
                issues.append(issue("example_leak", f"Text from the example draft leaked into this email: “{n}”."))
                break
    return issues


def candidate_issues(candidate: dict, readiness: dict, resume_path: str | None = None) -> list[dict]:
    """Candidate-level blockers (applied to every email).  resume_path: the resume this email attaches."""
    out = []
    path = (candidate.get("resume_path") if resume_path is None else resume_path) or ""
    if not path or not os.path.exists(path):
        out.append(issue("resume_missing", "Candidate resume file is missing.", "hard"))
    if not readiness.get("gmail_connected"):
        out.append(issue("gmail", "Candidate Gmail is not connected / verified.", "hard"))
    if not readiness.get("ready"):
        out.append(issue("candidate_not_ready", "Candidate not ready: " + "; ".join(readiness.get("missing", [])),
                         "hard"))
    return out
