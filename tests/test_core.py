import json
from datetime import date, datetime, timedelta, timezone
from unittest import mock

import pytest

from shorts import alert_info, publish_instagram, publish_tiktok, render, run, scriptgen, status, timeguard, tokens
from tools.gen_workflows import cron_for

UTC = timezone.utc


# ---------------------------------------------------------------- time guard + cron
def test_cron_conversion_karachi():
    assert cron_for("10am", "Asia/Karachi", 20)[0] == "40 4 * * *"
    assert cron_for("11am", "Asia/Karachi", 20)[0] == "40 5 * * *"
    assert cron_for("10pm", "Asia/Karachi", 20)[0] == "40 16 * * *"
    assert cron_for("11pm", "Asia/Karachi", 20)[0] == "40 17 * * *"
    assert cron_for("10am", "Asia/Karachi", 0)[0] == "0 5 * * *"      # no lead: 10:00 PKT = 05:00 UTC


def test_guard_on_time_and_boundaries():
    start = datetime(2026, 10, 19, 4, 40, tzinfo=UTC)               # 10am slot expected start
    assert timeguard.evaluate("10am", start).run
    assert timeguard.evaluate("10am", start + timedelta(minutes=15)).run
    g = timeguard.evaluate("10am", start + timedelta(minutes=16))
    assert not g.run and "DELAYED SKIP" in g.message
    assert not timeguard.evaluate("10am", start - timedelta(minutes=11)).run
    assert timeguard.evaluate("10am", start - timedelta(minutes=5)).run


def test_guard_across_midnight_utc_and_local():
    # 11pm slot (23:00 PKT = 18:00 UTC), start 17:40 UTC
    assert timeguard.evaluate("11pm", datetime(2026, 10, 19, 17, 50, tzinfo=UTC)).run
    # a 10am-slot run arriving at 20:00 UTC must be judged against the nearest 10am, i.e. very late -> skip
    assert not timeguard.evaluate("10am", datetime(2026, 10, 19, 20, 0, tzinfo=UTC)).run


# ---------------------------------------------------------------- script generation
GOOD = {"title": "My cat judges me", "script": " ".join(["Cats stare at you like landlords."] * 20),
        "visual_keywords": ["cat staring", "tired man", "kitchen"]}


def test_script_validation():
    fs = scriptgen.FunnyScript.model_validate(GOOD)
    assert fs.title.endswith("#Shorts")
    with pytest.raises(Exception):
        scriptgen.FunnyScript.model_validate({**GOOD, "script": "too short"})
    with pytest.raises(Exception):
        scriptgen.FunnyScript.model_validate({**GOOD, "visual_keywords": ["one"]})


def test_retry_then_success_and_provider_fallthrough():
    calls = {"a": 0}

    def flaky(system, prompt):
        calls["a"] += 1
        return "not json" if calls["a"] < 3 else json.dumps(GOOD)

    def unconfigured(system, prompt):
        raise RuntimeError("no key")

    fs, name = scriptgen.generate("10am", providers=[("none", unconfigured), ("flaky", flaky)], log=lambda *_: None)
    assert name == "flaky" and calls["a"] == 3          # 2 invalid replies, 3rd valid


def test_all_providers_fail():
    def bad(system, prompt):
        return "{}"
    with pytest.raises(RuntimeError, match="All script providers failed"):
        scriptgen.generate("10am", providers=[("bad", bad)], log=lambda *_: None)


def test_theme_is_deterministic_and_varies():
    assert scriptgen.pick_theme("10am", date(2026, 10, 19)) == scriptgen.pick_theme("10am", date(2026, 10, 19))
    themes = {scriptgen.pick_theme(s, date(2026, 10, 19)) for s in ("10am", "11am", "10pm", "11pm")}
    assert len(themes) >= 2


# ---------------------------------------------------------------- scene building
def test_build_scenes_keeps_every_word():
    fs = scriptgen.FunnyScript.model_validate(GOOD)
    scenes = render.build_scenes(fs.script, fs.visual_keywords)
    assert " ".join(s["voiceover"] for s in scenes).split() == fs.script.split()
    assert 3 <= len(scenes) <= 12
    assert {s["stock_query"] for s in scenes} <= set(fs.visual_keywords)
    from shortsmash.schemas import EditPlan
    EditPlan.model_validate(render.build_plan_dict(fs))   # ShortSmash accepts our plan


# ---------------------------------------------------------------- REAL ShortSmash render (voice replaced by a tone)
def test_real_shortsmash_render(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("STOCK_PROVIDER", "generate")
    import importlib
    import shortsmash.config as sc
    importlib.reload(sc)
    for m in ("shortsmash.pipeline", "shortsmash.music", "shortsmash.stock", "shortsmash.voice"):
        importlib.reload(importlib.import_module(m))
    import subprocess
    import shortsmash.voice as voice

    def fake_tts(text, out, cfg=None):
        out.parent.mkdir(parents=True, exist_ok=True)
        secs = max(1.0, len(text.split()) / 2.6)
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"sine=frequency=220:duration={secs:.2f}",
                        "-c:a", "libmp3lame", str(out)], check=True)
        return out

    monkeypatch.setattr(voice, "synthesize_scene", fake_tts)
    monkeypatch.setattr("shortsmash.music.ensure_library", lambda cfg=None: [])
    fs = scriptgen.FunnyScript.model_validate({**GOOD, "script": " ".join(["Cats stare at you like landlords."] * 20)})
    final, info, slug = render.render_video(fs, log=lambda *_: None)
    assert final.exists()
    assert (info["width"], info["height"]) == (1080, 1920)
    assert 30 <= info["duration"] <= 60


def test_footage_key_guard(monkeypatch):
    monkeypatch.setenv("STOCK_PROVIDER", "pixabay")
    monkeypatch.delenv("PIXABAY_API_KEY", raising=False)
    monkeypatch.delenv("ALLOW_PLACEHOLDER", raising=False)
    with pytest.raises(render.RenderError, match="PIXABAY_API_KEY"):
        render.check_footage_config()


# ---------------------------------------------------------------- publishers (mocked HTTP: tests MY request flow, not the real APIs)
class Resp:
    def __init__(self, js=None, status_code=200, text=""):
        self._js, self.status_code, self.text = js or {}, status_code, text
        self.ok = status_code < 400

    def json(self):
        return self._js


def test_tiktok_inbox_flow(tmp_path, monkeypatch):
    v = tmp_path / "v.mp4"
    v.write_bytes(b"x" * 1000)
    for k in ("TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET", "TIKTOK_REFRESH_TOKEN"):
        monkeypatch.setenv(k, "k")
    posts = []

    def fake_post(url, **kw):
        posts.append((url, kw))
        if url.endswith("/oauth/token/"):
            return Resp({"access_token": "AT", "refresh_token": "k"})
        if url.endswith("/inbox/video/init/"):
            return Resp({"data": {"publish_id": "p1", "upload_url": "https://up/x"}, "error": {"code": "ok"}})
        if url.endswith("/status/fetch/"):
            return Resp({"data": {"status": "SEND_TO_USER_INBOX"}, "error": {"code": "ok"}})
        raise AssertionError(url)

    put = mock.Mock(return_value=Resp(status_code=201))
    monkeypatch.setattr(publish_tiktok.requests, "post", fake_post)
    monkeypatch.setattr(publish_tiktok.requests, "put", put)
    monkeypatch.setattr(publish_tiktok.time, "sleep", lambda s: None)
    r = publish_tiktok.upload(v, "title", log=lambda *_: None, mode="inbox")
    assert r["id"] == "p1" and "inbox" in r["detail"]
    init_body = [kw for u, kw in posts if u.endswith("/inbox/video/init/")][0]["json"]
    assert init_body["source_info"] == {"source": "FILE_UPLOAD", "video_size": 1000, "chunk_size": 1000, "total_chunk_count": 1}
    assert put.call_args.kwargs["headers"]["Content-Range"] == "bytes 0-999/1000"


def test_tiktok_default_mode_is_inbox():
    from shorts import config
    assert config.TIKTOK_MODE == "inbox"


def test_instagram_flow(tmp_path, monkeypatch):
    v = tmp_path / "v.mp4"
    v.write_bytes(b"x")
    monkeypatch.setenv("IG_USER_ID", "123")
    monkeypatch.setenv("IG_ACCESS_TOKEN", "tok")
    monkeypatch.setattr(publish_instagram, "upload_public", lambda video, log=print: "https://files.catbox.moe/a.mp4")
    seen = []

    def fake_post(url, **kw):
        seen.append(url)
        if url.endswith("/123/media"):
            assert kw["data"]["media_type"] == "REELS" and kw["data"]["video_url"].startswith("https://files.catbox.moe")
            return Resp({"id": "c9"})
        if url.endswith("/123/media_publish"):
            assert kw["data"]["creation_id"] == "c9"
            return Resp({"id": "m1"})
        raise AssertionError(url)

    def fake_get(url, **kw):
        if url.endswith("/c9"):
            return Resp({"status_code": "FINISHED"})
        return Resp({"permalink": "https://instagram.com/reel/x"})

    monkeypatch.setattr(publish_instagram.requests, "post", fake_post)
    monkeypatch.setattr(publish_instagram.requests, "get", fake_get)
    monkeypatch.setattr(publish_instagram.time, "sleep", lambda s: None)
    r = publish_instagram.upload(v, "cap", log=lambda *_: None)
    assert r["id"] == "m1" and r["url"].endswith("/reel/x")
    assert seen[0].endswith("/media") and seen[1].endswith("/media_publish")


def test_instagram_error_is_surfaced(tmp_path, monkeypatch):
    v = tmp_path / "v.mp4"
    v.write_bytes(b"x")
    monkeypatch.setenv("IG_USER_ID", "123")
    monkeypatch.setenv("IG_ACCESS_TOKEN", "tok")
    monkeypatch.setattr(publish_instagram, "upload_public", lambda video, log=print: "https://x/y.mp4")
    monkeypatch.setattr(publish_instagram.requests, "post",
                        lambda url, **kw: Resp({"error": {"message": "bad token", "code": 190}}))
    with pytest.raises(RuntimeError, match="bad token"):
        publish_instagram.upload(v, "cap", log=lambda *_: None)


# ---------------------------------------------------------------- IG token expiry
def test_token_days_left_and_reminder(monkeypatch):
    assert tokens.days_left("2026-10-01", date(2026, 10, 19)) == 42
    monkeypatch.setenv("IG_USER_ID", "1")
    monkeypatch.setenv("IG_ACCESS_TOKEN", "t")
    monkeypatch.setenv("IG_TOKEN_ISSUED", (date.today() - timedelta(days=30)).isoformat())
    assert tokens.check(lambda *_: None) == ""
    monkeypatch.setenv("IG_TOKEN_ISSUED", (date.today() - timedelta(days=56)).isoformat())
    monkeypatch.setattr(tokens, "refresh", lambda log=print: False)      # no GH_PAT -> manual reminder
    msg = tokens.check(lambda *_: None)
    assert "expires in 4 day" in msg
    monkeypatch.delenv("IG_ACCESS_TOKEN")
    assert tokens.check(lambda *_: None) == ""


# ---------------------------------------------------------------- orchestration / status / alerts
def test_overall_logic():
    assert run.overall({"youtube": {"status": "ok"}, "tiktok": {"status": "skipped"}}) == "ok"
    assert run.overall({"youtube": {"status": "ok"}, "tiktok": {"status": "failed"}}) == "failed"
    assert run.overall({"youtube": {"status": "skipped"}}) == "failed"      # nothing posted = failure


def test_publish_all_isolates_failures(tmp_path, monkeypatch):
    monkeypatch.setattr(run, "PLATFORMS", ["youtube", "tiktok", "instagram"])
    monkeypatch.setattr(run.publish_youtube, "configured", lambda: True)
    monkeypatch.setattr(run.publish_tiktok, "configured", lambda: True)
    monkeypatch.setattr(run.publish_instagram, "configured", lambda: False)
    monkeypatch.setattr(run.publish_youtube, "upload", lambda *a, **k: {"url": "https://youtu.be/x", "id": "x"})

    def boom(*a, **k):
        raise RuntimeError("tiktok exploded")
    monkeypatch.setattr(run.publish_tiktok, "upload", boom)
    res = run.publish_all(tmp_path / "v.mp4", {"yt_title": "t", "yt_desc": "d", "yt_tags": [], "tt_title": "t", "ig_caption": "c"}, False)
    assert res["youtube"]["status"] == "ok"
    assert res["tiktok"]["status"] == "failed" and "exploded" in res["tiktok"]["detail"]
    assert res["instagram"]["status"] == "skipped"
    assert run.overall(res) == "failed"


def test_status_files(tmp_path, monkeypatch):
    from shorts import config
    monkeypatch.setattr(status, "HISTORY_FILE", tmp_path / "h.json")
    monkeypatch.setattr(status, "STATUS_MD", tmp_path / "STATUS.md")
    status.record({"slot": "10am", "title": "A|B", "overall": "ok", "seconds": 41.2,
                   "platforms": {"youtube": {"status": "ok", "url": "https://youtu.be/x"}}})
    status.record({"slot": "11am", "title": "", "overall": "failed", "error": "boom\nline2", "platforms": {}})
    md = (tmp_path / "STATUS.md").read_text()
    assert "https://youtu.be/x" in md and "boom line2" in md and "Last fully successful run" in md
    assert status.recent_titles() == ["A|B"]


def test_alert_names_failed_step_slot_and_link():
    steps = json.dumps({"guard": {"outcome": "success"}, "pip": {"outcome": "success"}, "run": {"outcome": "failure"}})
    subject, body = alert_info.build("failure", "10pm", steps, "https://github.com/o/r/actions/runs/5")
    assert "10pm" in subject and "Generate + render + publish video" in subject
    assert "https://github.com/o/r/actions/runs/5" in body
    s2, b2 = alert_info.build("skip", "11am", "{}", "https://x", "late 20 min")
    assert "SKIPPED" in s2 and "late 20 min" in b2
