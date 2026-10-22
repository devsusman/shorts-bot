"""Central settings. Everything comes from environment variables (GitHub Secrets / Variables)."""
from __future__ import annotations

import os
from pathlib import Path


def env(name: str, default: str = "") -> str:
    """Empty string counts as unset (GitHub passes unset secrets as empty strings)."""
    v = os.environ.get(name, "").strip()
    return v if v else default


def env_int(name: str, default: int) -> int:
    try:
        return int(env(name, str(default)))
    except ValueError:
        return default


ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
HISTORY_FILE = DATA_DIR / "history.json"
STATUS_MD = ROOT / "STATUS.md"
WORK_DIR = Path(env("WORK_DIR", str(ROOT / "work")))

# Your local timezone (IANA name). Cron is UTC, so the workflow files are generated from this.
TZ = env("LOCAL_TZ", "Asia/Karachi")

# Slot name -> (hour, minute) in local time. Publishing targets.
SLOTS = {"10am": (10, 0), "11am": (11, 0), "10pm": (22, 0), "11pm": (23, 0)}

# The workflow starts LEAD_MINUTES before the target so rendering is done by the target time
# (it also avoids the busy top-of-the-hour cron congestion). 0 = start exactly on the hour.
LEAD_MINUTES = env_int("LEAD_MINUTES", 20)
# If the run starts later than this after its expected start, skip it (delayed-skip notification).
MAX_DELAY_MINUTES = env_int("MAX_DELAY_MINUTES", 15)
EARLY_TOLERANCE_MINUTES = 10

PLATFORMS = [p.strip() for p in env("PLATFORMS", "youtube,tiktok,instagram").split(",") if p.strip()]
TIKTOK_MODE = env("TIKTOK_MODE", "inbox").lower()  # inbox | publish
YOUTUBE_PRIVACY = env("YOUTUBE_PRIVACY", "public")  # public | unlisted | private
SYNTHETIC_DISCLOSURE = env("SYNTHETIC_DISCLOSURE", "true").lower() == "true"

MIN_SECONDS = 30
MAX_SECONDS = 60
MIN_WORDS = 85    # ~33s at 2.6 words/sec
MAX_WORDS = 135   # ~52s at 2.6 words/sec

MUSIC_ATTRIBUTION = env(
    "MUSIC_ATTRIBUTION",
    "Music: Kevin MacLeod (incompetech.com), licensed under CC BY 4.0.",
)
