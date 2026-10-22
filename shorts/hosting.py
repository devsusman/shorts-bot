"""Free public hosting so Instagram's servers can fetch the video. catbox.moe first, litterbox as fallback."""
from __future__ import annotations

from pathlib import Path

import requests

from .config import env

CATBOX = "https://catbox.moe/user/api.php"
LITTERBOX = "https://litterbox.catbox.moe/resources/internals/api.php"


def upload_public(video: Path, log=print) -> str:
    errors = []
    userhash = env("CATBOX_USERHASH")  # optional: ties uploads to your catbox account
    try:
        with open(video, "rb") as f:
            r = requests.post(CATBOX, data={"reqtype": "fileupload", "userhash": userhash},
                              files={"fileToUpload": (video.name, f, "video/mp4")}, timeout=600)
        url = r.text.strip()
        if r.ok and url.startswith("https://"):
            log(f"catbox url: {url}")
            return url
        errors.append(f"catbox: HTTP {r.status_code} {url[:150]}")
    except requests.RequestException as e:
        errors.append(f"catbox: {e}")
    try:  # temporary (72h) fallback; Instagram only needs the file for a few minutes
        with open(video, "rb") as f:
            r = requests.post(LITTERBOX, data={"reqtype": "fileupload", "time": "72h"},
                              files={"fileToUpload": (video.name, f, "video/mp4")}, timeout=600)
        url = r.text.strip()
        if r.ok and url.startswith("https://"):
            log(f"litterbox url: {url}")
            return url
        errors.append(f"litterbox: HTTP {r.status_code} {url[:150]}")
    except requests.RequestException as e:
        errors.append(f"litterbox: {e}")
    raise RuntimeError("public hosting failed: " + " | ".join(errors))
