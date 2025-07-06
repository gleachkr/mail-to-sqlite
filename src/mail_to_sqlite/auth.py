import os
import json

import google.oauth2
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
OAUTH2_CREDENTIALS = "credentials.json"
IMAP_CREDENTIALS = "imap_credentials.json"


def get_gmail_credentials(data_dir: str) -> google.oauth2.credentials.Credentials:
    """
    Retrieves the Gmail authentication credentials for the specified data_dir by either loading
    it from the <data_dir>/credentials.json file or by running the authentication flow.

    Args:
        data_dir (str): The path where to store data.

    Returns:
        google.oauth2.credentials.Credentials: The authentication credentials.
    """
    credential_path = os.path.join(data_dir, OAUTH2_CREDENTIALS)
    token_path = os.path.join(data_dir, "token.json")

    if not os.path.exists(credential_path):
        raise ValueError(f"{OAUTH2_CREDENTIALS} not found in {data_dir}")

    creds = None
    if os.path.exists(token_path):
        try:
            creds = Credentials.from_authorized_user_file(token_path, GMAIL_SCOPES)
        except ValueError:
            # Token is corrupt, let the flow re-run
            pass

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            try:
                flow = InstalledAppFlow.from_client_secrets_file(
                    credential_path, GMAIL_SCOPES
                )
                creds = flow.run_local_server(port=0)
            except ValueError:
                raise ValueError(
                    f"Your '{OAUTH2_CREDENTIALS}' file is not a valid OAuth2 "
                    "credentials file."
                )
        with open(token_path, "w") as token:
            token.write(creds.to_json())

    return creds


def get_imap_credentials(data_dir: str) -> dict:
    """
    Retrieves the IMAP authentication credentials from the imap_credentials.json file.

    Args:
        data_dir (str): The path where credentials are stored.

    Returns:
        dict: The IMAP credentials with server, username, and password.
    """
    credential_path = os.path.join(data_dir, IMAP_CREDENTIALS)
    
    if not os.path.exists(credential_path):
        raise ValueError(f"{IMAP_CREDENTIALS} not found in {data_dir}")
    
    try:
        with open(credential_path, 'r') as f:
            credentials = json.load(f)
    except json.JSONDecodeError:
        raise ValueError(
            f"Your '{IMAP_CREDENTIALS}' file is not a valid JSON file."
        )

    required_keys = {"server", "username", "password"}
    missing_keys = required_keys - set(credentials.keys())
    if missing_keys:
        raise ValueError(
            f"Your '{IMAP_CREDENTIALS}' file is missing the following "
            f"required keys: {', '.join(missing_keys)}"
        )
        
    return credentials
