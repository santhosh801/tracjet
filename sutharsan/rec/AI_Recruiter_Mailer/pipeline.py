"""
Candidate-based processing pipeline:

  bulk LinkedIn paste → split into jobs → full JD analysis → rank all 5 templates
  → candidate↔JD match → 5 JD-specific highlights → personalised email
  → filters + quality check → Ready / Needs Review / Filtered Out
"""
import json
import re
from dataclasses import dataclass, field

import candidate_store as cs
import database as db
from email_composer import compose_email
from filters import ELIGIBLE, FilterConfig, evaluate_filters
from jd_analyzer import analyze_jd, extract_company, split_bulk_posts
from quality import candidate_issues, check_email_content
from settings import load_settings
from template_matcher import candidate_match, explain_choice, rank_templates

SENDABLE_STATUSES = {"Generated", "Failed"}
READY = "Ready"
READY_APPROVED = "Ready (Approved)"
NEEDS_REVIEW = "Needs Review"


@dataclass
class CandidateContext:
    candidate: dict
    profile: dict
    resume_text: str
    templates: list = field(default_factory=list)   # configured templates only
    readiness: dict = field(default_factory=dict)

    @property
    def id(self):
        return self.candidate["id"]

    def template_by_id(self, tid):
        return next((t for t in self.templates if t.get("id") == tid), None)

    def resume_for(self, template) -> dict:
        """{path, name, profile, text} of the resume for a job drafted with this template."""
        return cs.resume_for(self.candidate, template)


def load_context(cid) -> CandidateContext | None:
    c = cs.get_candidate(cid)
    if not c:
        return None
    templates = [t for t in cs.get_templates(cid) if cs.template_configured(t)]
    profile, resume_text = c.get("profile") or {}, c.get("resume_text") or ""
    if not profile:  # no main resume — fall back to the first template resume for general matching
        own = next((t for t in templates if t.get("profile")), None)
        if own:
            profile, resume_text = own["profile"], own.get("resume_text") or ""
    return CandidateContext(candidate=c, profile=profile, resume_text=resume_text,
                            templates=templates, readiness=cs.readiness(c))


def _loads(v, default):
    if isinstance(v, (list, dict)):
        return v
    try:
        return json.loads(v) if v else default
    except Exception:
        return default


# ── Bulk ingest ──────────────────────────────────────────────────────────
def parse_jobs(raw_text: str) -> list[dict]:
    """Split a bulk paste and analyse every job independently.  One record per recruiter email."""
    chunks, explicit = split_bulk_posts(raw_text)
    records = []
    seen = set()
    for chunk in chunks:
        if len(chunk.strip()) < 30:
            continue
        a = analyze_jd(chunk)
        if not a["emails"]:
            # keep jobs without an email visible (they can never be sent) — but only real job posts
            if not (explicit and a["is_job_post"]) and not (a["job_title"] and (a["experience"] or a["cities"])):
                continue
            emails = [""]
        else:
            emails = a["emails"]
        for email in emails:
            key = (email.lower(), a["job_title"].lower(), chunk[:80] if not email else "")
            if key in seen:
                continue
            seen.add(key)
            rec = {**a, "email": email}
            if len(emails) > 1 and not name_matches_email(a.get("recruiter_name", ""), email):
                rec["recruiter_name"] = ""  # greet "Dear Hiring Team" rather than the wrong person
            if len(emails) > 1 and a.get("company_source") == "email_domain":
                rec["company"], rec["company_source"] = extract_company("", [email])
            records.append(rec)
    return records


def name_matches_email(name: str, email: str) -> bool:
    """True when a part of the person's name (3+ letters) appears in the email's local part."""
    local = re.sub(r"[^a-z]", "", (email or "").split("@")[0].lower())
    parts = [p for p in re.split(r"[^a-z]+", (name or "").lower()) if len(p) >= 3]
    return bool(local and parts and any(p in local for p in parts))


def record_from_analysis(a: dict, cid) -> dict:
    analysis = {k: v for k, v in a.items() if k != "text"}
    return {
        "candidate_id": cid, "recruiter_name": a.get("recruiter_name", ""), "company": a.get("company", ""),
        "email": a.get("email", ""), "job_title": a.get("job_title", ""), "location": a.get("location", ""),
        "experience": a.get("experience", ""), "skills_required": ", ".join(a.get("required_skills", [])[:15]),
        "jd": a.get("text", ""), "location_cities": a.get("cities", []), "exp_min": a.get("exp_min"),
        "exp_max": a.get("exp_max"), "seniority": a.get("seniority", ""), "jd_analysis": analysis,
        "status": "Pending",
    }


def jd_for_record(record: dict) -> dict:
    """Re-analyse the stored post, letting user-edited record fields win."""
    jd = analyze_jd(record.get("jd") or "")
    stored = _loads(record.get("jd_analysis"), {}) or {}
    if stored.get("company_source"):
        jd["company_source"] = stored["company_source"]
    if (record.get("company") or "") != (stored.get("company") or jd.get("company") or ""):
        jd["company_source"] = "manual"  # the user typed a company — always use it
    for key in ("recruiter_name", "company", "job_title", "email", "location", "experience"):
        if record.get(key) is not None:
            jd[key] = record.get(key) or ""
    cities = _loads(record.get("location_cities"), None)
    if cities is not None:
        jd["cities"] = cities
    if record.get("exp_min") is not None or record.get("exp_max") is not None or record.get("experience") == "":
        jd["exp_min"], jd["exp_max"] = record.get("exp_min"), record.get("exp_max")
    return jd


def generate_for_job(jd: dict, ctx: CandidateContext, api_key: str = "", use_openai: bool = False,
                     template_id=None) -> dict:
    """Template selection + candidate matching + email generation for one job → DB fields."""
    ranked = rank_templates(jd, ctx.templates, ctx.profile)
    fields = {"template_scores": [{k: r[k] for k in ("template_id", "slot", "name", "score", "parts")}
                                  for r in ranked]}
    if not ranked:
        cm = candidate_match(ctx.profile, jd, ctx.resume_text)
        fields.update(match_percentage=cm["match_percentage"], matched_skills=", ".join(cm["matched_skills"]),
                      missing_skills=", ".join(cm["missing_skills"]), candidate_match=cm, template_name="",
                      template_reason="No templates configured in the Template Library.",
                      template_match_score=0, status="Pending")
        return fields
    chosen = next((r for r in ranked if r["template_id"] == template_id), None) if template_id else None
    chosen = chosen or ranked[0]
    template = ctx.template_by_id(chosen["template_id"])
    resume = ctx.resume_for(template)  # facts + attachment come from this template's resume
    cm = candidate_match(resume["profile"], jd, resume["text"])
    fields.update(match_percentage=cm["match_percentage"], matched_skills=", ".join(cm["matched_skills"]),
                  missing_skills=", ".join(cm["missing_skills"]), candidate_match=cm)
    comp = compose_email(ctx.candidate, resume["profile"], jd, template, resume["text"], api_key, use_openai)
    reason = explain_choice(ranked) if chosen is ranked[0] else \
        f"Manually selected “{chosen['name']}” ({chosen['score']}%)."
    fields.update(
        generated_subject=comp["subject"], generated_body=comp["body"], status="Generated",
        template_id=chosen["template_id"], template_name=chosen["name"], category=chosen["name"],
        template_match_score=chosen["score"], template_reason=reason, recommendation=reason,
        highlights=comp["highlights"], uses_bullets=1 if comp["uses_bullets"] else 0,
        generation_mode=comp["mode"], review_approved=0,
    )
    return fields


def ingest_bulk_text(raw_text: str, ctx: CandidateContext, api_key: str = "", use_openai: bool = False,
                     progress=None, cancelled=lambda: False) -> dict:
    jobs = parse_jobs(raw_text)
    if not jobs:
        return {"parsed": 0, "new": 0, "ids": []}
    if progress:
        progress(0.3, f"📂 Saving {len(jobs)} jobs…")
    ids, flags = db.insert_recruiters_bulk([record_from_analysis(j, ctx.id) for j in jobs], return_new_flags=True)
    updates = []
    new_ids = [rid for rid, new in zip(ids, flags) if new]
    for i, (rid, is_new, job) in enumerate(zip(ids, flags, jobs)):
        if cancelled():
            break
        if not is_new:
            continue  # same job pasted again — keep the existing record and any edits
        if progress:
            progress(0.3 + 0.55 * (i + 1) / len(ids), f"⚡ Matching & drafting {i + 1}/{len(ids)}…")
        updates.append((rid, generate_for_job(job, ctx, api_key, use_openai)))
    db.update_records_bulk(updates)
    return {"parsed": len(jobs), "new": len(new_ids), "ids": ids, "new_ids": new_ids}


def regenerate(ctx: CandidateContext, record_ids=None, api_key: str = "", use_openai: bool = False,
               template_id=None) -> int:
    """Re-draft unsent records (after resume/template/settings changes, or a manual template switch)."""
    count = 0
    for r in db.get_all_recruiters(ctx.id):
        if record_ids is not None and r["id"] not in record_ids:
            continue
        if r["status"] in ("Sent", "Sending"):
            continue
        db.update_record(r["id"], **generate_for_job(jd_for_record(r), ctx, api_key, use_openai, template_id))
        count += 1
    return count


# ── Evaluation (filters + quality + candidate readiness) ─────────────────
RESEND_GUARD_DAYS = 30


def evaluate_record(record: dict, ctx: CandidateContext | None, cfg: FilterConfig,
                    auto_approve: bool | None = None, emailed: dict | None = None) -> dict:
    """auto_approve: treat soft (non-blocking) review notes as approved. Hard issues — including a
    missing/invalid recruiter email — still block. Defaults to the "auto_approve_soft_review" setting.
    emailed: {recipient: date} already emailed by this candidate (looked up when not given)."""
    if auto_approve is None:
        auto_approve = bool(load_settings().get("auto_approve_soft_review"))
    filter_status, filter_reasons = evaluate_filters(record, cfg)
    issues = []
    if ctx is None or record.get("candidate_id") != ctx.id:
        issues.append({"code": "candidate_mismatch", "message": "Record belongs to a different candidate.",
                       "severity": "hard"})
    else:
        template = ctx.template_by_id(record.get("template_id"))
        if template is None:
            issues.append({"code": "template_missing", "message": "No template applied — regenerate the email.",
                           "severity": "hard"})
        highlights = _loads(record.get("highlights"), None)
        rec = dict(record)
        rec["cities"] = _loads(record.get("location_cities"), [])
        resume = ctx.resume_for(template)
        issues += check_email_content(rec, ctx.candidate, resume["profile"], resume["text"], template, highlights,
                                      bool(record.get("uses_bullets", 1)), record.get("template_match_score"),
                                      record.get("match_percentage"))
        issues += candidate_issues(ctx.candidate, ctx.readiness, resume["path"])
        if record.get("status") != "Sent":
            if emailed is None:
                emailed = db.recently_emailed(ctx.id, RESEND_GUARD_DAYS)
            last = emailed.get((record.get("email") or "").strip().lower())
            if last:
                issues.append({"code": "already_emailed", "severity": "hard",
                               "message": f"Already emailed this address on {last} — not sending twice "
                                          f"within {RESEND_GUARD_DAYS} days."})
    hard = [i for i in issues if i["severity"] == "hard"]
    if not issues:
        quality = READY
    elif not hard and (record.get("review_approved") or auto_approve):
        quality = READY_APPROVED
    else:
        quality = NEEDS_REVIEW
    eligible = (filter_status == ELIGIBLE and quality in (READY, READY_APPROVED)
                and record.get("status") in SENDABLE_STATUSES)
    blocking = list(filter_reasons) + [i["message"] for i in issues if quality == NEEDS_REVIEW]
    if record.get("status") not in SENDABLE_STATUSES:
        blocking.append(f"Status is {record.get('status')}")
    return {"filter_status": filter_status, "filter_reasons": filter_reasons, "quality_status": quality,
            "issues": issues, "eligible": eligible, "blocking": blocking}


def refresh_statuses(ctx: CandidateContext | None, cfg: FilterConfig, persist: bool = True) -> dict:
    """Recompute filter + quality status for every record of the candidate and return the counters."""
    counts = {"total": 0, "location_eligible": 0, "experience_eligible": 0, "ready": 0, "filtered": 0,
              "needs_review": 0, "sent": 0, "failed": 0}
    if ctx is None:
        return counts
    updates = []
    from filters import experience_matches, location_matches
    auto_approve = bool(load_settings().get("auto_approve_soft_review"))
    emailed = db.recently_emailed(ctx.id, RESEND_GUARD_DAYS)
    for r in db.get_all_recruiters(ctx.id):
        ev = evaluate_record(r, ctx, cfg, auto_approve, emailed)
        counts["total"] += 1
        counts["location_eligible"] += location_matches(r, cfg)[0]
        counts["experience_eligible"] += experience_matches(r, cfg)[0]
        if r["status"] == "Sent":
            counts["sent"] += 1
        if r["status"] == "Failed":
            counts["failed"] += 1
        if ev["filter_status"] != ELIGIBLE:
            counts["filtered"] += 1
        elif ev["eligible"]:
            counts["ready"] += 1
        elif r["status"] not in ("Sent", "Sending") and ev["quality_status"] == NEEDS_REVIEW:
            counts["needs_review"] += 1
        updates.append((r["id"], {"filter_status": ev["filter_status"], "quality_status": ev["quality_status"],
                                  "quality_issues": ev["issues"]}))
    if persist:
        db.update_records_bulk(updates)
    return counts


def send_status_label(record: dict) -> str:
    """Send Status column: Pending only for eligible unsent emails; filtered/review rows show Not Sent."""
    st = record.get("status") or ""
    if st == "Generated" or st == "Pending":
        if record.get("filter_status") == ELIGIBLE and (record.get("quality_status") or "").startswith(READY):
            return "Pending"
        return "Not Sent"
    return st
