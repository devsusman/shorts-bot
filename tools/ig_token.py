#!/usr/bin/env python3
"""Instagram token helper (Instagram API with Instagram Login).
  python tools/ig_token.py exchange   -> turn the short-lived token from the dashboard into a 60-day token
  python tools/ig_token.py refresh    -> extend a 60-day token (must be at least 24 h old)
  python tools/ig_token.py whoami     -> show the Instagram user id and username for a token
"""
import getpass
import sys
from datetime import date

import requests

HOST = "https://graph.instagram.com"


def exchange():
    secret = getpass.getpass("Instagram app secret: ").strip()
    short = getpass.getpass("Short-lived token: ").strip()
    r = requests.get(f"{HOST}/access_token", timeout=60,
                     params={"grant_type": "ig_exchange_token", "client_secret": secret, "access_token": short}).json()
    show(r)


def refresh():
    tok = getpass.getpass("Current long-lived token: ").strip()
    r = requests.get(f"{HOST}/refresh_access_token", timeout=60,
                     params={"grant_type": "ig_refresh_token", "access_token": tok}).json()
    show(r)


def whoami():
    tok = getpass.getpass("Token: ").strip()
    r = requests.get(f"{HOST}/v23.0/me", timeout=60, params={"fields": "user_id,username,account_type", "access_token": tok}).json()
    print(r)
    print("IG_USER_ID is the 'user_id' value above.")


def show(r):
    if "access_token" not in r:
        sys.exit(f"Failed: {r}")
    print("\nIG_ACCESS_TOKEN =", r["access_token"])
    print(f"expires_in = {r.get('expires_in')} seconds (~{int(r.get('expires_in', 0)) // 86400} days)")
    print(f"Set repository variable IG_TOKEN_ISSUED = {date.today().isoformat()}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    {"exchange": exchange, "refresh": refresh, "whoami": whoami}.get(cmd, lambda: sys.exit(__doc__))()
