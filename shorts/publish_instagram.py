"""Instagram Reels via the Graph API. Needs a Business/Creator account and a PUBLIC video URL (catbox).

Flow: upload to catbox -> POST /{ig-user-id}/media (REELS, video_url) -> poll status_code -> POST /media_publish.
Defaults to the "Instagram API with Instagram Login" host (graph.instagram.com). If your token came from
Facebook Login, set IG_GRAPH_HOST=https://graph.facebook.com.
"""
from __future__ import annotations

import time
from pathlib import Path

import requests

from .config import env
from .hosting import upload_public


def configured() -> bool:
    return bool(env("IG_USER_ID") and env("IG_ACCESS_TOKEN"))


def _base() -> str:
    return f"{env('IG_GRAPH_HOST', 'https://graph.instagram.com')}/{env('IG_API_VERSION', 'v23.0')}"


def _check(r: requests.Response, what: str) -> dict:
    d = r.json()
    if "error" in d:
        e = d["error"]
        raise RuntimeError(f"Instagram {what} failed: {e.get('message')} (code {e.get('code')}, subcode {e.get('error_subcode')})")
    return d


def upload(video: Path, caption: str, log=print) -> dict:
    uid, token, base = env("IG_USER_ID"), env("IG_ACCESS_TOKEN"), _base()
    public_url = upload_public(video, log)
    r = requests.post(f"{base}/{uid}/media", timeout=120, data={
        "media_type": "REELS", "video_url": public_url, "caption": caption[:2200],
        "share_to_feed": "true", "access_token": token})
    container = _check(r, "create container")["id"]

    status = "IN_PROGRESS"
    for _ in range(40):                                      # up to ~7 minutes of transcoding
        time.sleep(10)
        s = _check(requests.get(f"{base}/{container}", timeout=60,
                                params={"fields": "status_code,status", "access_token": token}), "status")
        status = s.get("status_code", "?")
        if status == "FINISHED":
            break
        if status in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Instagram processing {status}: {s.get('status')}")
    if status != "FINISHED":
        raise RuntimeError(f"Instagram processing timed out (last status {status})")

    p = _check(requests.post(f"{base}/{uid}/media_publish", timeout=120,
                             data={"creation_id": container, "access_token": token}), "publish")
    media_id = p["id"]
    permalink = ""
    try:
        permalink = requests.get(f"{base}/{media_id}", timeout=30,
                                 params={"fields": "permalink", "access_token": token}).json().get("permalink", "")
    except requests.RequestException:
        pass
    return {"id": media_id, "url": permalink, "detail": f"hosted at {public_url}"}
