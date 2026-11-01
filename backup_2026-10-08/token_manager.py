import os
import json
import logging
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

TOKEN_FILE = "token.json"
SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
]

logger = logging.getLogger(__name__)


def load_token() -> Credentials | None:
    """Load credentials from token.json if it exists."""
    if not os.path.exists(TOKEN_FILE):
        return None
    try:
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        return creds
    except Exception as e:
        logger.error(f"Failed to load token: {e}")
        return None


def save_token(creds: Credentials):
    """Persist credentials to token.json."""
    try:
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
        logger.info("Token saved successfully.")
    except Exception as e:
        logger.error(f"Failed to save token: {e}")


def delete_token():
    """Remove token.json to force re-authentication."""
    if os.path.exists(TOKEN_FILE):
        os.remove(TOKEN_FILE)
        logger.info("Token deleted (user disconnected).")


def refresh_token(creds: Credentials) -> Credentials | None:
    """Attempt to refresh an expired token."""
    try:
        creds.refresh(Request())
        save_token(creds)
        logger.info("Token refreshed successfully.")
        return creds
    except Exception as e:
        logger.error(f"Token refresh failed: {e}")
        return None


def get_valid_credentials() -> Credentials | None:
    """
    Return valid credentials if available.
    Automatically refreshes expired tokens.
    Returns None if no valid credentials exist.
    """
    creds = load_token()
    if creds is None:
        return None

    if creds.valid:
        return creds

    if creds.expired and creds.refresh_token:
        refreshed = refresh_token(creds)
        return refreshed

    return None


def is_connected() -> bool:
    """Check if a valid token is present without opening a browser."""
    creds = get_valid_credentials()
    return creds is not None and creds.valid
