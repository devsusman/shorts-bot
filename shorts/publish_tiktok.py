"""TikTok Content Posting API (FILE_UPLOAD).

TIKTOK_MODE=inbox   -> /v2/post/publish/inbox/video/init/  (goes to your TikTok inbox/drafts; you tap Post once in the app)
TIKTOK_MODE=publish -> /v2/post/publish/video/init/        (direct post; REQUIRES TikTok app audit, 2-4 weeks. Unaudited apps
                       can only post with privacy SELF_ONLY, which this module will use until you set TIKTOK_PRIVACY.)

Access tokens last 24 h, so every run refreshes one from TIKTOK_REFRESH_TOKEN. If TikTok rotates the refresh token
we store the new one back into the GitHub secret when GH_PAT is set; otherwise we warn loudly.
"""
from __future__ import annotations

import time
from pathlib import Path

import requests

from .config import TIKTOK_MODE, env
from .secrets_store import set_secret

API = "https://open.tiktokapis.com"


def configured() -> bool:
    return all(env(k) for k in ("TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET", "TIKTOK_REFRESH_TOKEN"))


def refresh_access_token(log=print) -> str:
    r = requests.post(f"{API}/v2/oauth/token/", timeout=60,
                      headers={"Content-Type": "application/x-www-form-urlencoded"},
                      data={"client_key": env("TIKTOK_CLIENT_KEY"), "client_secret": env("TIKTOK_CLIENT_SECRET"),
                            "grant_type": "refresh_token", "refresh_token": env("TIKTOK_REFRESH_TOKEN")})
    d = r.json()
    if "access_token" not in d:
        raise RuntimeError(f"TikTok token refresh failed: {str(d)[:300]}")
    new_rt = d.get("refresh_token")
    if new_rt and new_rt != env("TIKTOK_REFRESH_TOKEN"):
        if set_secret("TIKTOK_REFRESH_TOKEN", new_rt, log):
            log("TikTok refresh token rotated and saved to GitHub secrets")
        else:
            log("WARNING: TikTok issued a NEW refresh token but GH_PAT is not set, so it was not saved. "
                "If uploads start failing with token errors, re-run tools/tiktok_auth.py and update TIKTOK_REFRESH_TOKEN.")
    return d["access_token"]


def _check(d: dict, what: str) -> dict:
    err = d.get("error", {})
    if err and err.get("code") not in (None, "ok"):
        raise RuntimeError(f"TikTok {what} failed: {err.get('code')}: {err.get('message')}")
    return d.get("data", {})


def upload(video: Path, title: str, log=print, mode: str | None = None) -> dict:
    mode = (mode or TIKTOK_MODE).lower()
    if mode not in ("inbox", "publish"):
        raise RuntimeError("TIKTOK_MODE must be 'inbox' or 'publish'")
    token = refresh_access_token(log)
    size = video.stat().st_size
    if size > 64 * 1024 * 1024:
        raise RuntimeError("video over 64 MB; single-chunk upload not allowed")
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"}
    source = {"source": "FILE_UPLOAD", "video_size": size, "chunk_size": size, "total_chunk_count": 1}

    if mode == "inbox":
        url = f"{API}/v2/post/publish/inbox/video/init/"
        body = {"source_info": source}
    else:
        url = f"{API}/v2/post/publish/video/init/"
        body = {"post_info": {"title": title[:2200], "privacy_level": env("TIKTOK_PRIVACY", "SELF_ONLY"),
                              "disable_duet": False, "disable_comment": False, "disable_stitch": False,
                              "is_aigc": True},
                "source_info": source}
    r = requests.post(url, headers=headers, json=body, timeout=60)
    data = _check(r.json(), "init")
    publish_id, upload_url = data["publish_id"], data["upload_url"]

    with open(video, "rb") as f:
        put = requests.put(upload_url, data=f, timeout=600, headers={
            "Content-Type": "video/mp4", "Content-Length": str(size),
            "Content-Range": f"bytes 0-{size - 1}/{size}"})
    if put.status_code not in (200, 201, 206):
        raise RuntimeError(f"TikTok upload PUT failed: HTTP {put.status_code} {put.text[:200]}")

    status = "UNKNOWN"
    for _ in range(18):                                    # ~3 minutes
        time.sleep(10)
        s = requests.post(f"{API}/v2/post/publish/status/fetch/", headers=headers, timeout=60,
                          json={"publish_id": publish_id}).json()
        d = _check(s, "status")
        status = d.get("status", "UNKNOWN")
        if status in ("PUBLISH_COMPLETE", "SEND_TO_USER_INBOX"):
            break
        if status == "FAILED":
            raise RuntimeError(f"TikTok processing failed: {d.get('fail_reason')}")
    where = "your TikTok inbox: open the app and tap Post" if mode == "inbox" else "TikTok (check privacy level)"
    return {"id": publish_id, "url": "", "detail": f"mode={mode} status={status}; delivered to {where}"}
