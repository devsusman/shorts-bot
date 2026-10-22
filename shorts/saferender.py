"""Memory-safe replacement for `shortsmash.edit.render`.

Why: ShortSmash 0.3.0 builds ONE giant FFmpeg filter graph (all scenes + xfade chain). FFmpeg then buffers
every later scene's decoded 1080x1920 frames while it waits for earlier ones; measured here, a 7-scene ~42 s
video made ffmpeg grow past 6 GB and get OOM-killed. A free GitHub runner has 7-16 GB, so that is not safe.

This version keeps ShortSmash's look (slow push-in, grade, karaoke/hook captions via libass, ducked music,
"never ship silent" check) but renders ONE scene at a time, joins them, then does a single captions+audio pass.
Peak memory no longer grows with video length. It also LOOPS a stock clip that is shorter than its narration
(the original only trims, which would freeze/cut short).
"""
from __future__ import annotations

import subprocess
from pathlib import Path

FPS = 30
ENC = ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS)]


def _run(cmd: list[str]) -> None:
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"ffmpeg failed ({p.returncode}): {p.stderr[-800:]}")


def _esc(p: Path) -> str:
    return str(p).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def render(plan, clips, voiceovers, captions_ass, words, workdir, music_track=None, cfg=None) -> Path:
    from shortsmash.config import Config
    from shortsmash.edit import _assert_audible
    from shortsmash.music import prepare_music
    from shortsmash.voice import concat_audio, probe_duration

    cfg = cfg or Config()
    W, H = cfg.get("width", 1080), cfg.get("height", 1920)
    n = len(plan.scenes)
    assert len(clips) == n and len(voiceovers) == n
    durs = [probe_duration(a) for a in voiceovers]
    total = sum(durs)
    seg_dir = Path(workdir) / "segments"
    seg_dir.mkdir(exist_ok=True)

    # 1) one scene at a time (video only)
    segs = []
    for i in range(n):
        frames = max(1, int(durs[i] * FPS))
        vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,"
              f"zoompan=z='1+0.06*on/{frames}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={W}x{H}:fps={FPS},"
              f"eq=contrast=1.06:saturation=1.12:brightness=0.01,fps={FPS}")
        seg = seg_dir / f"seg_{i + 1:02d}.mp4"
        _run(["ffmpeg", "-y", "-v", "error", "-stream_loop", "-1", "-i", str(clips[i]),
              "-vf", vf, "-an", "-t", f"{durs[i]:.3f}", *ENC, "-preset", "veryfast", "-crf", "18", str(seg)])
        segs.append(seg)

    # 2) join (stream copy, identical encode settings)
    lst = seg_dir / "list.txt"
    lst.write_text("".join(f"file '{s.resolve()}'\n" for s in segs))
    body = Path(workdir) / "body.mp4"
    _run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(body)])

    # 3) voice track (+ ducked music) and a single captions pass
    voice = concat_audio(list(voiceovers), Path(workdir) / "voice_all.mp3")
    out = Path(workdir) / "final.mp4"
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(body), "-i", str(voice)]
    vchain = f"[0:v]ass={_esc(Path(captions_ass))}[vout]"
    if music_track:
        music = Path(workdir) / "music_ducked.m4a"
        prepare_music(music_track, total, words, music, cfg)
        cmd += ["-i", str(music)]
        fc = f"{vchain};[1:a][2:a]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[aout]"
    else:
        fc = f"{vchain};[1:a]anull[aout]"
    cmd += ["-filter_complex", fc, "-map", "[vout]", "-map", "[aout]", *ENC, "-preset", "fast", "-crf", "20",
            "-maxrate", "16M", "-bufsize", "32M", "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
            "-movflags", "+faststart", "-shortest", str(out)]
    _run(cmd)
    if not out.exists():
        raise RuntimeError("FFmpeg render failed: no output file produced.")
    _assert_audible(out)
    return out


def install() -> None:
    """Swap ShortSmash's render stage for this one."""
    from shortsmash import edit
    edit.render = render
