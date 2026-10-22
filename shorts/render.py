"""Module 2: ShortSmash wrapper.

ShortSmash's own script layer is bypassed: we write our validated script as `plan.json`
(an EditPlan) and call ShortSmash's `resume_project`, which runs the remaining stages:
voice (Edge-TTS) -> footage (Pixabay) -> karaoke captions (faster-whisper) -> music -> FFmpeg 1080x1920.
That is exactly what `shortsmash resume <slug>` does. On failure we call it once more, then raise.
"""
from __future__ import annotations

import re
import subprocess
from datetime import datetime
from pathlib import Path

from .config import MAX_SECONDS, MIN_SECONDS, MUSIC_ATTRIBUTION, TZ, env
from .scriptgen import FunnyScript

WORDS_PER_SEC = 2.6


class RenderError(RuntimeError):
    pass


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]


def build_scenes(script: str, keywords: list[str], target_words: int = 18, max_scenes: int = 12) -> list[dict]:
    """Group sentences into beats of ~target_words and attach stock keywords in order."""
    beats: list[list[str]] = []
    cur: list[str] = []
    for s in _sentences(script):
        cur.append(s)
        if sum(len(x.split()) for x in cur) >= target_words:
            beats.append(cur)
            cur = []
    if cur:
        if beats and sum(len(x.split()) for x in cur) < 8:
            beats[-1].extend(cur)          # don't leave a tiny orphan scene
        else:
            beats.append(cur)
    while len(beats) > max_scenes:         # merge the shortest neighbours
        i = min(range(len(beats) - 1), key=lambda j: sum(len(x.split()) for x in beats[j] + beats[j + 1]))
        beats[i] = beats[i] + beats.pop(i + 1)
    n = len(beats)
    scenes = []
    for i, beat in enumerate(beats):
        text = " ".join(beat)
        scenes.append({
            "id": i + 1,
            "voiceover": text[:500],
            "on_screen_text": "",
            "stock_query": keywords[int(i * len(keywords) / n)],
            "duration": max(1.5, round(len(text.split()) / WORDS_PER_SEC, 2)),
            "transition": "cut",
            "mood": "funny",
        })
    return scenes


def build_plan_dict(fs: FunnyScript) -> dict:
    first = _sentences(fs.script)[0]
    return {
        "title": fs.title,
        "hook": first[:140],
        "description": first[:200],
        "hashtags": ["#Shorts", "#funny", "#comedy", "#standup", "#humor"],
        "scenes": build_scenes(fs.script, fs.visual_keywords),
        "music_mood": "playful",
        "cta": "",
    }


def _shortsmash_config():
    from shortsmash.config import Config
    over = {
        "voice": env("VOICE", "en-US-GuyNeural"),
        "voice_rate": env("VOICE_RATE", "+0%"),
        "stock_provider": env("STOCK_PROVIDER", "pixabay"),
        # ShortSmash's CLIP gate needs torch (~GBs). Off by default; VISION_GATE=1 enables it.
        "stock_verify": env("VISION_GATE", "0") == "1",
        "caption_style": "karaoke",
        "width": 1080, "height": 1920, "timezone": TZ,
        "max_duration": MAX_SECONDS + 5,
    }
    return Config(over)


def probe(path: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height:format=duration,size", "-of", "default=nw=1", str(path)],
        capture_output=True, text=True, check=True).stdout
    kv = dict(line.split("=", 1) for line in out.strip().splitlines() if "=" in line)
    return {"width": int(kv["width"]), "height": int(kv["height"]),
            "duration": float(kv["duration"]), "size_mb": int(kv["size"]) / 1e6}


def validate_output(path: Path) -> dict:
    info = probe(path)
    if (info["width"], info["height"]) != (1080, 1920):
        raise RenderError(f"output is {info['width']}x{info['height']}, expected 1080x1920")
    if not (MIN_SECONDS <= info["duration"] <= MAX_SECONDS):
        raise RenderError(f"output is {info['duration']:.1f}s, required {MIN_SECONDS}-{MAX_SECONDS}s")
    if info["size_mb"] > 64:
        raise RenderError(f"output is {info['size_mb']:.0f} MB; TikTok single-chunk upload limit is 64 MB")
    return info


def check_footage_config() -> None:
    provider = env("STOCK_PROVIDER", "pixabay")
    have_key = bool(env("PIXABAY_API_KEY") if provider == "pixabay" else env("PEXELS_API_KEY"))
    if provider in ("pixabay", "pexels") and not have_key and env("ALLOW_PLACEHOLDER") != "1":
        raise RenderError(f"{provider.upper()}_API_KEY is not set. Without it ShortSmash would silently use "
                          "plain gradient placeholders instead of real footage. Set the key (or ALLOW_PLACEHOLDER=1).")


def render_video(fs: FunnyScript, log=print) -> tuple[Path, dict, str]:
    """Returns (final_mp4, info, slug)."""
    from shortsmash import pipeline
    from shortsmash.schemas import EditPlan

    check_footage_config()
    from . import saferender
    saferender.install()   # memory-safe render stage (see saferender.py for why)
    plan = EditPlan.model_validate(build_plan_dict(fs))
    plan.validate_runtime(MAX_SECONDS + 5)
    slug = "short-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    workdir = pipeline.project_dir(slug)
    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / "plan.json").write_text(plan.model_dump_json(indent=2))
    cfg = _shortsmash_config()

    last: Exception | None = None
    for attempt in (1, 2):                       # first run + exactly one `resume`
        try:
            log(f"shortsmash {'resume' if attempt == 2 else 'run'} {slug}")
            pipeline.resume_project(slug, cfg)   # == `shortsmash resume <slug>`
            final = workdir / "final.mp4"
            if not final.exists():
                cands = sorted(workdir.glob("*.mp4"), key=lambda p: p.stat().st_mtime)
                cands = [c for c in cands if "scene_" not in c.name and "clips" not in str(c)]
                if not cands:
                    raise RenderError("ShortSmash finished but no final video was found")
                final = cands[-1]
            info = validate_output(final)
            return final, info, slug
        except Exception as e:                   # noqa: BLE001
            last = e
            log(f"render attempt {attempt} failed: {e}")
    raise RenderError(f"render failed after resume: {last}")


def attribution() -> str:
    return MUSIC_ATTRIBUTION
