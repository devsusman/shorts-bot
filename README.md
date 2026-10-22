# shorts-bot

Free funny-Shorts factory on GitHub Actions. 4 videos a day, published to YouTube, TikTok and Instagram.

```
cron (UTC) ─► time guard ─► Gemini/Groq script ─► ShortSmash (Edge-TTS voice, Pixabay footage,
  captions, music, FFmpeg 1080x1920) ─► wait until publish time ─► YouTube + TikTok + Instagram
  ─► STATUS.md + Healthchecks ping    (any failure: email/Slack alert + Healthchecks /fail)
```

**Start here: [docs/SETUP.md](docs/SETUP.md).**

## Layout
```
.github/workflows/video-10am.yml  video-11am.yml  video-10pm.yml  video-11pm.yml   (generated)
shorts/config.py         settings from env vars
shorts/timeguard.py      "started too late? skip" check
shorts/scriptgen.py      Gemini -> Groq -> Ollama, pydantic + 3 retries
shorts/render.py         ShortSmash wrapper (plan.json -> resume_project, retry once)
shorts/saferender.py     memory-safe replacement for ShortSmash's render stage
shorts/publish_youtube.py  publish_tiktok.py  publish_instagram.py  hosting.py (catbox)
shorts/tokens.py         Instagram 60-day token check/refresh
shorts/status.py         data/history.json + STATUS.md dashboard
shorts/healthchecks.py   start/success/fail pings
shorts/alert_info.py     alert text: slot, failing step, run link
shorts/run.py            orchestrator
tools/                   gen_workflows.py, youtube_auth.py, tiktok_auth.py, ig_token.py, set_secrets.py
tests/test_core.py       19 tests (python -m pytest)
```

## Local test
```
pip install -r requirements.txt pytest
python -m pytest -q          # needs ffmpeg installed
```
