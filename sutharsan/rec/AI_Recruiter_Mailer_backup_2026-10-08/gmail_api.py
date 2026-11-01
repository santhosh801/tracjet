import logging
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from oauth import get_authenticated_credentials
from attachment_manager import build_mime_message, encode_message, encode_draft

logger = logging.getLogger(__name__)


def get_gmail_service():
    """Build and return an authenticated Gmail API service."""
    creds = get_authenticated_credentials()
    service = build("gmail", "v1", credentials=creds)
    return service


def get_connected_email() -> str:
    """Return the email address of the connected Gmail account."""
    try:
        service = get_gmail_service()
        profile = service.users().getProfile(userId="me").execute()
        return profile.get("emailAddress", "Unknown")
    except Exception as e:
        logger.error(f"Failed to get Gmail profile: {e}")
        return "Not connected"


def send_email(
    to: str,
    subject: str,
    body: str,
    body_type: str = "html",
    attachment_paths: list[str] = None,
    cc: str = "",
    bcc: str = "",
) -> str:
    """
    Send an email via Gmail API.

    Returns:
        Message ID on success.
    Raises:
        HttpError on Gmail API failure.
        Exception on any other error.
    """
    try:
        service = get_gmail_service()
        msg = build_mime_message(to, subject, body, body_type, attachment_paths, cc, bcc)
        raw = encode_message(msg)
        sent = service.users().messages().send(userId="me", body=raw).execute()
        logger.info(f"Email sent to {to} | Message ID: {sent['id']}")
        return sent["id"]
    except HttpError as e:
        logger.error(f"Gmail API error sending to {to}: {e}")
        raise
    except Exception as e:
        logger.error(f"Failed to send email to {to}: {e}")
        raise


def create_draft(
    to: str,
    subject: str,
    body: str,
    body_type: str = "html",
    attachment_paths: list[str] = None,
    cc: str = "",
    bcc: str = "",
) -> str:
    """
    Create a Gmail draft.

    Returns:
        Draft ID on success.
    Raises:
        HttpError on Gmail API failure.
    """
    try:
        service = get_gmail_service()
        msg = build_mime_message(to, subject, body, body_type, attachment_paths, cc, bcc)
        draft_body = encode_draft(msg)
        draft = service.users().drafts().create(userId="me", body=draft_body).execute()
        logger.info(f"Draft created for {to} | Draft ID: {draft['id']}")
        return draft["id"]
    except HttpError as e:
        logger.error(f"Gmail API error creating draft for {to}: {e}")
        raise
    except Exception as e:
        logger.error(f"Failed to create draft for {to}: {e}")
        raise
