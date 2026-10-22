"""Orchestrator: script -> render -> publish (YouTube, TikTok, Instagram) -> status.

Usage: python -m shorts.run --slot 10am [--dry-run]
Exit code 1 if anything failed (so the workflow's failure alert fires).
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

from . import publish_instagram, publish_tiktok, publish_youtube, render, scriptgen, status, tokens
from .config import MUSIC_ATTRIBUTION, PLATFORMS, SLOTS, TIKTOK_MODE


def log(msg: str) -> None:
    print(f"[{datetime.now(timezone.utc):%H:%M:%S}] {msg}", flush=True)


def gh_output(key: str, value: str) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{key}={value.replace(chr(10), ' ')}\n")


def wait_until_target(max_wait_min: int = 45) -> None:
    """Sleep until the publish target so posts land on the hour (TARGET_ISO is set by the time guard)."""
    iso = os.environ.get("TARGET_ISO", "")
    if not iso:
        return
    secs = (datetime.fromisoformat(iso) - datetime.now(timezone.utc)).total_seconds()
    if secs <= 0:
        log("publish target already passed; publishing now")
        return
    secs = min(secs, max_wait_min * 60)
    log(f"video ready; waiting {secs / 60:.1f} min until the publish target")
    time.sleep(secs)


def build_texts(fs: scriptgen.FunnyScript) -> dict:
    first = render._sentences(fs.script)[0]
    base_title = fs.title.replace("#Shorts", "").replace("#shorts", "").strip()
    tags = ["#Shorts", "#funny", "#comedy", "#standup", "#humor"]
    credits = f"AI-generated voice. Stock footage: Pixabay.\n{MUSIC_ATTRIBUTION}".strip()
    return {
        "yt_title": fs.title,
        "yt_desc": f"{first}\n\n{' '.join(tags)}\n\n{credits}",
        "yt_tags": tags,
        "tt_title": f"{base_title} #funny #comedy #fyp",
        "ig_caption": f"{first}\n\n#funny #comedy #standup #humor #reels\n\n{credits}",
    }


def publish_all(video: Path, texts: dict, dry_run: bool) -> dict:
    jobs = {
        "youtube": (publish_youtube.configured, lambda: publish_youtube.upload(
            video, texts["yt_title"], texts["yt_desc"], texts["yt_tags"], log)),
        "tiktok": (publish_tiktok.configured, lambda: publish_tiktok.upload(video, texts["tt_title"], log)),
        "instagram": (publish_instagram.configured, lambda: publish_instagram.upload(video, texts["ig_caption"], log)),
    }
    results: dict[str, dict] = {}
    for name in PLATFORMS:
        if name not in jobs:
            results[name] = {"status": "failed", "detail": f"unknown platform '{name}'"}
            continue
        configured, fn = jobs[name]
        if not configured():
            results[name] = {"status": "skipped", "detail": "no credentials set"}
            log(f"{name}: SKIPPED (no credentials)")
            continue
        if dry_run:
            results[name] = {"status": "dry_run", "detail": "dry run"}
            continue
        try:
            r = fn()
            results[name] = {"status": "ok", "url": r.get("url", ""), "detail": r.get("detail", ""), "id": r.get("id", "")}
            log(f"{name}: OK {r.get('url', '')} {r.get('detail', '')}")
        except Exception as e:  # noqa: BLE001 - one platform failing must not stop the others
            results[name] = {"status": "failed", "detail": str(e)[:400]}
            log(f"{name}: FAILED {e}")
    return results


def overall(results: dict) -> str:
    st = [r["status"] for r in results.values()]
    if any(s == "failed" for s in st):
        return "failed"
    if any(s in ("ok", "dry_run") for s in st):
        return "ok"
    return "failed"  # everything skipped: nothing was posted


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slot", required=True, choices=sorted(SLOTS))
    ap.add_argument("--dry-run", action="store_true", default=os.environ.get("DRY_RUN") == "true")
    a = ap.parse_args()
    entry: dict = {"slot": a.slot, "title": "", "platforms": {}, "overall": "failed"}
    try:
        reminder = tokens.check(log)
        gh_output("reminder", reminder)
        fs, provider = scriptgen.generate(a.slot, status.recent_titles(), log=log)
        entry.update(title=fs.title, llm=provider)
        video, info, slug = render.render_video(fs, log)
        entry["seconds"] = round(info["duration"], 1)
        log(f"rendered {video} ({info['duration']:.1f}s, {info['size_mb']:.1f} MB)")
        if not a.dry_run:
            wait_until_target()
        entry["platforms"] = publish_all(video, build_texts(fs), a.dry_run)
        entry["overall"] = overall(entry["platforms"])
        if entry["overall"] == "failed":
            bad = {k: v["detail"] for k, v in entry["platforms"].items() if v["status"] in ("failed", "skipped")}
            entry["error"] = "; ".join(f"{k}: {v}" for k, v in bad.items())[:500]
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        entry["error"] = str(e)[:500]
    status.record(entry)
    log(f"overall: {entry['overall']} {entry.get('error', '')}")
    return 0 if entry["overall"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
