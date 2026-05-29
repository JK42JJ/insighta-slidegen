"""
Google OAuth2 token management for Slides + Drive APIs.

Reads credentials from env vars:
    GOOGLE_OAUTH_CLIENT_ID
    GOOGLE_OAUTH_CLIENT_SECRET
    GOOGLE_OAUTH_REDIRECT_URI

Token cache: ~/.cache/insighta-slidegen/google_token.json
Scopes: https://www.googleapis.com/auth/presentations
        https://www.googleapis.com/auth/drive.file
"""

from __future__ import annotations

import os
from pathlib import Path


SCOPES = [
    "https://www.googleapis.com/auth/presentations",
    "https://www.googleapis.com/auth/drive.file",
]

TOKEN_CACHE_PATH = Path.home() / ".cache" / "insighta-slidegen" / "google_token.json"


def get_credentials():
    """
    Return a valid google.oauth2.credentials.Credentials object.

    Algorithm:
        1. If TOKEN_CACHE_PATH exists, load and refresh if expired.
        2. Otherwise run InstalledAppFlow.run_local_server(port=0) to obtain
           new credentials and persist to TOKEN_CACHE_PATH.
        3. Return credentials.

    Raises:
        EnvironmentError: if GOOGLE_OAUTH_CLIENT_ID or CLIENT_SECRET unset.

    TODO: implement using google_auth_oauthlib.flow.InstalledAppFlow.
    """
    client_id = os.environ.get("GOOGLE_OAUTH_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise EnvironmentError("GOOGLE_OAUTH_CLIENT_ID / GOOGLE_OAUTH_CLIENT_SECRET not set")
    # TODO: implement OAuth2 flow
    raise NotImplementedError("TODO: get_credentials — InstalledAppFlow or token refresh")


def build_slides_service(credentials=None):
    """
    Return a googleapiclient.discovery.Resource for the Slides v1 API.

    TODO: call get_credentials() if credentials is None, then
    return googleapiclient.discovery.build("slides", "v1", credentials=credentials).
    """
    raise NotImplementedError("TODO: build_slides_service")


def build_drive_service(credentials=None):
    """
    Return a googleapiclient.discovery.Resource for the Drive v3 API.

    TODO: same pattern as build_slides_service for drive v3.
    """
    raise NotImplementedError("TODO: build_drive_service")
