import json
import os
from typing import Optional

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
]


def _client_config() -> dict:
    redirect_uri = f"{os.environ['PUBLIC_URL']}/oauth/callback"
    return {
        "web": {
            "client_id": os.environ["GOOGLE_CLIENT_ID"],
            "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [redirect_uri],
        }
    }


def generate_auth_url(state: str) -> tuple[str, str]:
    """Returns (auth_url, code_verifier)."""
    config = _client_config()
    flow = Flow.from_client_config(config, scopes=SCOPES)
    flow.redirect_uri = config["web"]["redirect_uris"][0]
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        state=state,
        prompt="consent",
    )
    return auth_url, flow.code_verifier


def exchange_code(code: str, code_verifier: Optional[str] = None) -> tuple:
    """Returns (tokens_dict, email_address)."""
    config = _client_config()
    flow = Flow.from_client_config(config, scopes=SCOPES)
    flow.redirect_uri = config["web"]["redirect_uris"][0]
    flow.fetch_token(code=code, code_verifier=code_verifier)
    creds = flow.credentials

    service = build("oauth2", "v2", credentials=creds)
    user_info = service.userinfo().get().execute()
    email = user_info["email"]

    tokens = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes) if creds.scopes else SCOPES,
    }
    return tokens, email


def get_credentials(tokens_json: str) -> Credentials:
    tokens = json.loads(tokens_json)
    return Credentials(
        token=tokens["token"],
        refresh_token=tokens["refresh_token"],
        token_uri=tokens["token_uri"],
        client_id=tokens["client_id"],
        client_secret=tokens["client_secret"],
        scopes=tokens["scopes"],
    )


def get_gmail_service(credentials: Credentials):
    return build("gmail", "v1", credentials=credentials)
