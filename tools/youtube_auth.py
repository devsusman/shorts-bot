#!/usr/bin/env python3
"""One-time, run on YOUR computer. Opens a browser, you log in, it prints the JSON for the YT_OAUTH_JSON secret.
Needs client_secret.json (OAuth client of type 'Desktop app') in the current folder.
Your consent screen must be published to 'In production' BEFORE you run this, otherwise the refresh token expires in 7 days."""
import json
import pathlib
import sys

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
path = pathlib.Path("client_secret.json")
if not path.exists():
    sys.exit("client_secret.json not found in this folder. See docs/SETUP.md step 6.")
flow = InstalledAppFlow.from_client_secrets_file(str(path), SCOPES)
creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
if not creds.refresh_token:
    sys.exit("No refresh token returned. Revoke the app at myaccount.google.com/permissions and run again.")
info = json.loads(creds.to_json())
out = {k: info[k] for k in ("client_id", "client_secret", "refresh_token", "token_uri") if k in info}
print("\n=== COPY EVERYTHING BELOW INTO THE GITHUB SECRET YT_OAUTH_JSON ===\n")
print(json.dumps(out))
