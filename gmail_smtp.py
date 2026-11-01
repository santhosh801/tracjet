"""
Gmail SMTP Email Sender
Uses Gmail's SMTP server with App Password authentication.
No OAuth, no credentials.json, no browser popups needed.

Setup:
1. Go to https://myaccount.google.com/security
2. Enable 2-Step Verification
3. Go to https://myaccount.google.com/apppasswords
4. Create an App Password for "Mail"
5. Copy the 16-character password
6. Paste it in the app's Settings
"""

import smtplib
import os
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import mimetypes

logger = logging.getLogger(__name__)

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587


def test_connection(email: str, app_password: str) -> tuple[bool, str]:
    """Test SMTP connection. Returns (success, message)."""
    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=10)
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(email, app_password)
        server.quit()
        return True, f"Connected as {email}"
    except smtplib.SMTPAuthenticationError:
        return False, "Authentication failed. Check your email and App Password."
    except Exception as e:
        return False, f"Connection failed: {str(e)}"


def build_email(
    sender: str,
    to: str,
    subject: str,
    body: str,
    body_type: str = "html",
    attachment_paths: list[str] = None,
    cc: str = "",
    bcc: str = "",
) -> MIMEMultipart:
    """Build a MIME email with attachments."""
    msg = MIMEMultipart("mixed")
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject
    if cc:
        msg["Cc"] = cc

    # Body
    body_part = MIMEText(body, body_type, "utf-8")
    msg.attach(body_part)

    # Attachments
    if attachment_paths:
        for path in attachment_paths:
            if not path or not os.path.exists(path):
                logger.warning(f"Attachment not found: {path}")
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
                logger.error(f"Attachment error {path}: {e}")

    return msg


def send_email(
    sender_email: str,
    app_password: str,
    to: str,
    subject: str,
    body: str,
    body_type: str = "html",
    attachment_paths: list[str] = None,
    cc: str = "",
    bcc: str = "",
) -> tuple[bool, str]:
    """
    Send an email via Gmail SMTP.
    Returns (success, message_or_error).
    """
    try:
        msg = build_email(sender_email, to, subject, body, body_type, attachment_paths, cc, bcc)

        recipients = [to]
        if cc:
            recipients += [addr.strip() for addr in cc.split(",")]
        if bcc:
            recipients += [addr.strip() for addr in bcc.split(",")]

        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=30)
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(sender_email, app_password)
        server.sendmail(sender_email, recipients, msg.as_string())
        server.quit()

        logger.info(f"Email sent to {to}")
        return True, "Sent successfully"

    except smtplib.SMTPAuthenticationError:
        error = "SMTP Auth failed. Check App Password."
        logger.error(error)
        return False, error
    except smtplib.SMTPRecipientsRefused:
        error = f"Recipient refused: {to}"
        logger.error(error)
        return False, error
    except Exception as e:
        error = str(e)[:200]
        logger.error(f"Send failed to {to}: {error}")
        return False, error
