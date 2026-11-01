"""
SEND ELIGIBLE EMAILS.

This is the only path the UI uses to send.  Immediately before each email it
re-loads the candidate, re-checks readiness, re-applies the CURRENT filters
and re-runs the quality check — a stale "Eligible" flag can never cause a send.
"""
import logging
import os
import time
from datetime import datetime

import candidate_store as cs
import database as db
from filters import FilterConfig
from pipeline import evaluate_record, load_context
from quality import valid_recipient
from settings import load_settings

logger = logging.getLogger(__name__)


def _sent_today(sender: str) -> int:
    conn = db.get_db()
    n = conn.execute("SELECT COUNT(*) FROM logs WHERE status='Sent' AND date=? AND (sender=? OR sender IS NULL)",
                     (datetime.now().strftime("%Y-%m-%d"), sender)).fetchone()[0]
    conn.close()
    return n


def send_eligible(candidate_id, cfg: FilterConfig, record_ids=None, only_statuses=None, sender_fn=None,
                  delay=None, on_update=None, sleep=time.sleep, should_stop=lambda: False,
                  on_progress=None) -> dict:
    """
    Send every eligible email for the candidate (optionally limited to record_ids / statuses).
    Returns {"sent", "failed", "skipped": [(id, reason)], "attempted", "error"}.
    on_progress(done, total, current) is called before each send (current = recipient) and after
    each record (current = "").
    """
    def progress(done, total, current=""):
        if on_progress:
            on_progress(done, total, current)

    if sender_fn is None:
        from gmail_smtp import send_email as sender_fn
    summary = {"sent": 0, "failed": 0, "skipped": [], "attempted": 0, "error": ""}
    settings = load_settings()
    delay = int(settings.get("delay_between_emails", 3) or 0) if delay is None else delay

    ctx = load_context(candidate_id)
    if ctx is None:
        summary["error"] = "No candidate selected."
        return summary
    if not ctx.readiness.get("ready"):
        summary["error"] = "Candidate not ready: " + "; ".join(ctx.readiness.get("missing", []))
        return summary
    gmail = (ctx.candidate.get("gmail_address") or "").strip()
    app_password = cs.get_app_password(ctx.id)
    max_daily = int(settings.get("max_daily_emails", 50) or 50)
    remaining_today = max(0, max_daily - _sent_today(gmail))

    records = db.get_all_recruiters(ctx.id)
    if record_ids is not None:
        wanted = {int(i) for i in record_ids}
        records = [r for r in records if r["id"] in wanted]
    if only_statuses:
        records = [r for r in records if r["status"] in only_statuses]
    records.sort(key=lambda r: r["id"])
    total = len(records)
    progress(0, total)

    first = True
    for done, r in enumerate(records):
        if done:
            progress(done, total)
        if should_stop():
            summary["error"] = "Sending stopped by user."
            break
        # 1-5: re-validate everything right now
        ctx = load_context(candidate_id)
        if ctx is None or not ctx.readiness.get("ready"):
            summary["error"] = "Candidate became not ready during sending."
            break
        fresh = db.get_recruiter(r["id"])
        ev = evaluate_record(fresh, ctx, cfg)
        db.update_record(fresh["id"], filter_status=ev["filter_status"], quality_status=ev["quality_status"],
                         quality_issues=ev["issues"])
        if not ev["eligible"]:
            summary["skipped"].append((fresh["id"], "; ".join(ev["blocking"]) or "Not eligible"))
            continue
        to = (fresh.get("email") or "").strip()
        if not valid_recipient(to):
            summary["skipped"].append((fresh["id"], "Invalid recruiter email"))
            continue
        resume = ctx.resume_for(ctx.template_by_id(fresh.get("template_id")))["path"]
        if not resume or not os.path.exists(resume):
            summary["skipped"].append((fresh["id"], "Resume file for this template is missing"))
            continue
        if remaining_today <= 0:
            summary["skipped"].append((fresh["id"], f"Daily limit of {max_daily} emails reached"))
            continue
        if not first and delay:
            sleep(delay)
        first = False

        # 6-7: attach resume, send through the candidate's Gmail
        progress(done, total, to)
        summary["attempted"] += 1
        db.update_record(fresh["id"], status="Sending")
        if on_update:
            on_update()
        attachment = os.path.basename(resume)
        try:
            ok, msg = sender_fn(gmail, app_password, to, fresh["generated_subject"], fresh["generated_body"],
                                "plain", [resume])
        except Exception as e:  # keep going with the other emails
            ok, msg = False, str(e)[:200]

        # 8-11: record result, timestamp, recruiter/company/job, template used
        log_args = dict(candidate_id=ctx.id, job_title=fresh.get("job_title") or "",
                        template_name=fresh.get("template_name") or "", sender=gmail, attachment=attachment,
                        recruiter_name=fresh.get("recruiter_name") or "", record_id=fresh["id"])
        if ok:
            db.update_record(fresh["id"], status="Sent", sent_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                             sent_from=gmail, attachment_name=attachment)
            db.log_event(to, fresh.get("company") or "", fresh["generated_subject"], "Sent", "", **log_args)
            summary["sent"] += 1
            remaining_today -= 1
        else:
            db.update_record(fresh["id"], status="Failed")
            db.log_event(to, fresh.get("company") or "", fresh["generated_subject"], "Failed", msg, **log_args)
            summary["failed"] += 1
            logger.error(f"Send failed to {to}: {msg}")
        if on_update:
            on_update()
    else:
        progress(total, total)
    return summary
