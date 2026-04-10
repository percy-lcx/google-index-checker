import os
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

from config import GOOGLE_CREDENTIALS_PATH, TOKEN_PATH

SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]


def get_credentials(credentials_path: str = None, token_path: str = None) -> Credentials:
    """Load or create OAuth credentials with auto-refresh."""
    credentials_path = credentials_path or GOOGLE_CREDENTIALS_PATH
    token_path = token_path or TOKEN_PATH
    creds = None

    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(credentials_path):
                raise FileNotFoundError(
                    f"credentials.json not found at {credentials_path}. "
                    "Download OAuth client credentials from Google Cloud Console."
                )
            flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(token_path, "w") as f:
            f.write(creds.to_json())

    return creds


def get_searchconsole_service(credentials_path: str = None, token_path: str = None):
    """Build the Search Console API service."""
    creds = get_credentials(credentials_path, token_path)
    return build("searchconsole", "v1", credentials=creds)
