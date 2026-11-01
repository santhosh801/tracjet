import os
import mimetypes
import base64
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

logger = logging.getLogger(__name__)


def build_mime_message(
    to: str,
    subject: str,
    body: str,
    body_type: str = "html",
    attachment_paths: list[str] = None,
    cc: str = "",
    bcc: str = "",
    sender: str = "me",
) -> MIMEMultipart:
    """
    Build a MIME email message with optional attachments, CC, and BCC.

    Args:
        to: Recipient email address.
        subject: Email subject.
        body: Email body content.
        body_type: 'html' or 'plain'.
        attachment_paths: List of file paths to attach.
        cc: CC email addresses (comma-separated).
        bcc: BCC email addresses (comma-separated).
        sender: Sender email address (default 'me' uses authenticated account).

    Returns:
        A fully constructed MIMEMultipart message object.
    """
    msg = MIMEMultipart("mixed")
    msg["To"] = to
    msg["Subject"] = subject
    if cc:
        msg["Cc"] = cc
    if bcc:
        msg["Bcc"] = bcc

    # Attach the body
    body_part = MIMEText(body, body_type, "utf-8")
    msg.attach(body_part)

    # Attach files
    if attachment_paths:
        for path in attachment_paths:
            if not path or not os.path.exists(path):
                logger.warning(f"Attachment not found, skipping: {path}")
                continue
            try:
                mime_type, _ = mimetypes.guess_type(path)
                if mime_type is None:
                    mime_type = "application/octet-stream"
                main_type, sub_type = mime_type.split("/", 1)

                with open(path, "rb") as f:
                    file_data = f.read()

                part = MIMEBase(main_type, sub_type)
                part.set_payload(file_data)
                encoders.encode_base64(part)
                part.add_header(
                    "Content-Disposition",
                    "attachment",
                    filename=os.path.basename(path),
                )
                msg.attach(part)
                logger.info(f"Attached: {os.path.basename(path)}")
            except Exception as e:
                logger.error(f"Failed to attach {path}: {e}")

    return msg


def encode_message(msg: MIMEMultipart) -> dict:
    """Encode a MIME message to Gmail API raw format."""
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
    return {"raw": raw}


def encode_draft(msg: MIMEMultipart) -> dict:
    """Encode a MIME message into Gmail API draft format."""
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
    return {"message": {"raw": raw}}
