"""Instagram long-lived token expiry check (tokens last 60 days).

Set the repository VARIABLE IG_TOKEN_ISSUED=YYYY-MM-DD on the day you create/refresh the token.
< 7 days left: if GH_PAT is set we refresh it automatically and save it; otherwise we return a reminder
that the workflow sends by email/Slack.
"""
from __future__ import annotations

from datetime import date, datetime

import requests

from .config import env
from .secrets_store import set_secret, set_variable

LIFETIME_DAYS = 60
WARN_DAYS = 7


def days_left(issued: str, today: date | None = None) -> int:
    d = datetime.strptime(issued, "%Y-%m-%d").date()
    return LIFETIME_DAYS - ((today or date.today()) - d).days


def refresh(log=print) -> bool:
    """Extend the token by another 60 days (Instagram Login tokens must be >= 24 h old)."""
    if env("IG_GRAPH_HOST", "https://graph.instagram.com") != "https://graph.instagram.com":
        return False
    r = requests.get("https://graph.instagram.com/refresh_access_token", timeout=60,
                     params={"grant_type": "ig_refresh_token", "access_token": env("IG_ACCESS_TOKEN")})
    d = r.json()
    if "access_token" not in d:
        log(f"Instagram token refresh failed: {str(d)[:200]}")
        return False
    ok = set_secret("IG_ACCESS_TOKEN", d["access_token"], log)
    set_variable("IG_TOKEN_ISSUED", date.today().isoformat(), log)
    return ok


def check(log=print) -> str:
    """Returns a reminder message ('' when nothing to say)."""
    if not (env("IG_USER_ID") and env("IG_ACCESS_TOKEN")):
        return ""
    issued = env("IG_TOKEN_ISSUED")
    if not issued:
        return ("Instagram: set the repository variable IG_TOKEN_ISSUED=YYYY-MM-DD (the date you created the token) "
                "so expiry reminders work.")
    try:
        left = days_left(issued)
    except ValueError:
        return f"Instagram: IG_TOKEN_ISSUED '{issued}' is not YYYY-MM-DD."
    log(f"Instagram token: {left} days left")
    if left >= WARN_DAYS:
        return ""
    if left >= 0 and refresh(log):
        log("Instagram token refreshed automatically")
        return ""
    if left < 0:
        return ("Instagram token has EXPIRED. Create a new one with `python tools/ig_token.py exchange`, "
                "update IG_ACCESS_TOKEN and set IG_TOKEN_ISSUED.")
    return (f"Instagram token expires in {left} day(s). Run `python tools/ig_token.py refresh`, "
            "update the IG_ACCESS_TOKEN secret and the IG_TOKEN_ISSUED variable.")
