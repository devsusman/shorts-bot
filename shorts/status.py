"""Run history (data/history.json) and the human-readable dashboard (STATUS.md). Committed back to the repo by the workflow."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from .config import HISTORY_FILE, STATUS_MD, TZ

ICON = {"ok": "✅", "failed": "❌", "skipped": "⏭️", "dry_run": "🧪"}


def load() -> list[dict]:
    try:
        return json.loads(HISTORY_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def recent_titles(n: int = 40) -> list[str]:
    return [r.get("title", "") for r in load()[-n:] if r.get("title")]


def record(entry: dict, keep: int = 300) -> None:
    hist = load()
    entry = {"time": datetime.now(timezone.utc).isoformat(timespec="seconds"), **entry}
    hist.append(entry)
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_FILE.write_text(json.dumps(hist[-keep:], indent=1))
    render_md(hist[-keep:])


def _cell(p: dict | None) -> str:
    if not p:
        return "–"
    s = ICON.get(p.get("status", ""), "?")
    return f"[{s}]({p['url']})" if p.get("url") else s


def render_md(hist: list[dict]) -> None:
    z = ZoneInfo(TZ)
    rows = []
    for r in reversed(hist[-60:]):
        t = datetime.fromisoformat(r["time"]).astimezone(z).strftime("%m-%d %H:%M")
        pl = r.get("platforms", {})
        err = (r.get("error") or "").replace("|", "/").replace("\n", " ")[:90]
        rows.append(f"| {t} | {r.get('slot', '')} | {(r.get('title') or '–')[:60].replace('|', '/')} | "
                    f"{_cell(pl.get('youtube'))} | {_cell(pl.get('tiktok'))} | {_cell(pl.get('instagram'))} | "
                    f"{r.get('seconds', '')} | {err} |")
    ok = [r for r in hist if r.get("overall") == "ok"]
    last_ok = datetime.fromisoformat(ok[-1]["time"]).astimezone(z).strftime("%Y-%m-%d %H:%M") if ok else "never"
    md = [
        "# Shorts bot status", "",
        f"Times shown in {TZ}. Last fully successful run: **{last_ok}**. "
        f"Total runs logged: {len(hist)}, successful: {len(ok)}.", "",
        "✅ done · ❌ failed · ⏭️ skipped (no credentials) · 🧪 dry run", "",
        "| Time | Slot | Title | YouTube | TikTok | Instagram | Sec | Error |",
        "|---|---|---|---|---|---|---|---|", *rows, "",
        "_Dead-man's-switch alerts come from Healthchecks.io; failure alerts from the workflow._", "",
    ]
    STATUS_MD.write_text("\n".join(md))
