"""YouTube Data API v3 videos.insert. Needs the OAuth consent screen set to "In production" (else refresh tokens die in 7 days).

NOTE (my understanding of YouTube's policy, verify): videos uploaded through the API by an *unaudited* API project
are locked to private until you pass YouTube's API compliance audit. If that happens, `privacyStatus` will
come back as "private" and this module reports it so you are not surprised.
"""
from __future__ import annotations

import json
from pathlib import Path

from .config import SYNTHETIC_DISCLOSURE, YOUTUBE_PRIVACY, env

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def configured() -> bool:
    return bool(env("YT_OAUTH_JSON"))


def _service():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    info = json.loads(env("YT_OAUTH_JSON"))
    creds = Credentials.from_authorized_user_info(info, SCOPES)
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def upload(video: Path, title: str, description: str, tags: list[str], log=print) -> dict:
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload

    yt = _service()
    body = {
        "snippet": {"title": title[:100], "description": description[:4900],
                    "tags": [t.lstrip("#") for t in tags][:15], "categoryId": env("YT_CATEGORY_ID", "23")},  # 23 = Comedy
        "status": {"privacyStatus": YOUTUBE_PRIVACY, "selfDeclaredMadeForKids": False,
                   "containsSyntheticMedia": SYNTHETIC_DISCLOSURE},
    }

    def attempt(b):
        media = MediaFileUpload(str(video), mimetype="video/mp4", chunksize=8 * 1024 * 1024, resumable=True)
        req = yt.videos().insert(part="snippet,status", body=b, media_body=media)
        resp = None
        while resp is None:
            _, resp = req.next_chunk()
        return resp

    try:
        resp = attempt(body)
    except HttpError as e:
        if "containsSyntheticMedia" in str(e):   # field rejected: retry without it and say so
            log("WARNING: API rejected containsSyntheticMedia; uploading without it. Tick the box in Studio.")
            body["status"].pop("containsSyntheticMedia")
            resp = attempt(body)
        else:
            raise
    vid = resp["id"]
    privacy = resp.get("status", {}).get("privacyStatus", "?")
    note = ""
    if privacy != YOUTUBE_PRIVACY:
        note = f" (requested {YOUTUBE_PRIVACY} but YouTube set {privacy}: unaudited API project?)"
    return {"id": vid, "url": f"https://youtu.be/{vid}", "detail": f"privacy={privacy}{note}"}
