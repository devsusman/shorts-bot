#!/usr/bin/env python3
"""One-time, run on YOUR computer. Gets the TikTok refresh token.
1) Prints a login URL. Open it, log in with the TikTok account, approve.
2) TikTok redirects to your Redirect URI with ?code=... in the address bar. The page may be a 404, that's fine.
3) Paste the full redirected URL here. The script exchanges the code and prints the values for your secrets.
Your Redirect URI must be an https URL registered in your TikTok developer app."""
import getpass
import secrets
import sys
import urllib.parse

import requests

key = input("TikTok Client key: ").strip()
secret = getpass.getpass("TikTok Client secret: ").strip()
redirect = input("Redirect URI (exactly as registered): ").strip()
scopes = "user.info.basic,video.upload,video.publish"
state = secrets.token_urlsafe(8)
url = ("https://www.tiktok.com/v2/auth/authorize/?" + urllib.parse.urlencode(
    {"client_key": key, "scope": scopes, "response_type": "code", "redirect_uri": redirect, "state": state}))
print("\nOpen this URL in your browser and approve:\n\n" + url + "\n")
back = input("Paste the full URL you were redirected to: ").strip()
q = urllib.parse.parse_qs(urllib.parse.urlparse(back).query)
if "code" not in q:
    sys.exit(f"No code in that URL. TikTok said: {q}")
if q.get("state", [state])[0] != state:
    sys.exit("State mismatch; start again.")
r = requests.post("https://open.tiktokapis.com/v2/oauth/token/", timeout=60,
                  headers={"Content-Type": "application/x-www-form-urlencoded"},
                  data={"client_key": key, "client_secret": secret, "code": q["code"][0],
                        "grant_type": "authorization_code", "redirect_uri": redirect})
d = r.json()
if "refresh_token" not in d:
    sys.exit(f"Token exchange failed: {d}")
print("\n=== SAVE THESE AS GITHUB SECRETS ===")
print("TIKTOK_CLIENT_KEY    =", key)
print("TIKTOK_CLIENT_SECRET = (the secret you typed)")
print("TIKTOK_REFRESH_TOKEN =", d["refresh_token"])
print(f"\n(refresh token valid ~{d.get('refresh_expires_in', '?')} seconds; scopes granted: {d.get('scope')})")
