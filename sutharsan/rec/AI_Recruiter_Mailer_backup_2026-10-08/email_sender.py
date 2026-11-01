import logging
import time
import threading
from datetime import datetime
from database import get_all_recruiters, update_status, log_event
from gmail_api import send_email, create_draft
from settings import load_settings

logger = logging.getLogger(__name__)


def _get_attachments() -> list[str]:
    settings = load_settings()
    resume = settings.get("resume_path", "")
    return [resume] if resume else []


def send_single(recruiter_id: int, recruiter: dict, on_update=None) -> bool:
    """
    Send one email for a recruiter.
    Returns True on success, False on failure.
    """
    to = recruiter.get("email", "")
    subject = recruiter.get("generated_subject", "")
    body = recruiter.get("generated_body", "")
    company = recruiter.get("company", "")

    if not to or not subject or not body:
        logger.warning(f"Skipping recruiter {recruiter_id}: missing email, subject, or body.")
        update_status(recruiter_id, "Skipped")
        log_event(to, company, subject, "Skipped", "Missing required fields.")
        return False

    try:
        attachments = _get_attachments()
        update_status(recruiter_id, "Sending")
        if on_update:
            on_update()

        send_email(to=to, subject=subject, body=body, body_type="plain", attachment_paths=attachments)
        update_status(recruiter_id, "Sent")
        log_event(to, company, subject, "Sent", "")
        if on_update:
            on_update()
        return True

    except Exception as e:
        error_msg = str(e)[:200]
        logger.error(f"Failed to send to {to}: {error_msg}")
        update_status(recruiter_id, f"Failed")
        log_event(to, company, subject, "Failed", error_msg)
        if on_update:
            on_update()
        return False


def draft_single(recruiter_id: int, recruiter: dict, on_update=None) -> bool:
    """Create a Gmail draft for one recruiter."""
    to = recruiter.get("email", "")
    subject = recruiter.get("generated_subject", "")
    body = recruiter.get("generated_body", "")
    company = recruiter.get("company", "")

    if not to or not subject or not body:
        update_status(recruiter_id, "Skipped")
        log_event(to, company, subject, "Skipped", "Missing required fields.")
        return False

    try:
        attachments = _get_attachments()
        create_draft(to=to, subject=subject, body=body, body_type="plain", attachment_paths=attachments)
        update_status(recruiter_id, "Draft Created")
        log_event(to, company, subject, "Draft Created", "")
        if on_update:
            on_update()
        return True

    except Exception as e:
        error_msg = str(e)[:200]
        update_status(recruiter_id, "Failed")
        log_event(to, company, subject, "Failed", error_msg)
        if on_update:
            on_update()
        return False


def send_all_background(on_update=None, on_complete=None):
    """
    Send all 'Generated' emails in a background thread.
    Respects the delay_between_emails and max_daily_emails settings.
    """
    def task():
        settings = load_settings()
        delay = int(settings.get("delay_between_emails", 5))
        max_daily = int(settings.get("max_daily_emails", 50))

        recruiters = get_all_recruiters()
        targets = [r for r in recruiters if r["status"] == "Generated"][:max_daily]

        sent_count = 0
        for r in targets:
            success = send_single(r["id"], r, on_update)
            if success:
                sent_count += 1
            time.sleep(delay)

        logger.info(f"Bulk send complete. Sent: {sent_count}/{len(targets)}")
        if on_complete:
            on_complete(sent_count, len(targets))

    thread = threading.Thread(target=task, daemon=True)
    thread.start()


def draft_all_background(on_update=None, on_complete=None):
    """Create drafts for all 'Generated' recruiters in a background thread."""
    def task():
        recruiters = get_all_recruiters()
        targets = [r for r in recruiters if r["status"] == "Generated"]

        drafted = 0
        for r in targets:
            success = draft_single(r["id"], r, on_update)
            if success:
                drafted += 1

        logger.info(f"Bulk draft complete. Drafted: {drafted}/{len(targets)}")
        if on_complete:
            on_complete(drafted, len(targets))

    thread = threading.Thread(target=task, daemon=True)
    thread.start()


def retry_failed_background(on_update=None, on_complete=None):
    """Retry all 'Failed' emails in a background thread."""
    def task():
        settings = load_settings()
        delay = int(settings.get("delay_between_emails", 5))
        retry_count = int(settings.get("retry_count", 3))

        recruiters = get_all_recruiters()
        targets = [r for r in recruiters if r["status"] == "Failed"]

        retried = 0
        for r in targets:
            for attempt in range(retry_count):
                success = send_single(r["id"], r, on_update)
                if success:
                    retried += 1
                    break
                time.sleep(delay)

        if on_complete:
            on_complete(retried, len(targets))

    thread = threading.Thread(target=task, daemon=True)
    thread.start()
