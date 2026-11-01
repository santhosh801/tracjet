import os
import logging
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from token_manager import SCOPES, TOKEN_FILE, save_token, delete_token, get_valid_credentials

CREDENTIALS_FILE = "credentials.json"
logger = logging.getLogger(__name__)


def authenticate() -> Credentials:
    """
    Run the full OAuth 2.0 flow.
    Opens a browser window for the user to sign in with Google.
    Saves the resulting token to token.json.
    Raises an Exception if credentials.json is missing.
    """
    if not os.path.exists(CREDENTIALS_FILE):
        raise FileNotFoundError(
            f"'{CREDENTIALS_FILE}' not found in the application folder.\n\n"
            "Please follow these steps to get it:\n"
            "1. Go to https://console.cloud.google.com/\n"
            "2. Create a project → Enable Gmail API\n"
            "3. Create OAuth 2.0 credentials (Desktop App)\n"
            "4. Download the JSON and rename it to 'credentials.json'\n"
            "5. Place it in the same folder as this application."
        )

    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
    creds = flow.run_local_server(
        port=0,
        prompt="consent",
        access_type="offline",
    )
    save_token(creds)
    logger.info("OAuth authentication successful.")
    return creds


def get_authenticated_credentials() -> Credentials:
    """
    Returns valid credentials.
    Uses cached token if available and valid.
    Refreshes if expired.
    Raises an exception if user needs to re-authenticate.
    """
    creds = get_valid_credentials()
    if creds:
        return creds
    # Token missing or revoked — needs fresh login
    raise PermissionError(
        "Gmail is not connected. Please click 'Connect Gmail' to authenticate."
    )


def disconnect():
    """Remove the stored token, effectively logging out."""
    delete_token()
    logger.info("Gmail account disconnected.")
