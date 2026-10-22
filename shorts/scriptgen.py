"""Module 1: funny script generation. Gemini free -> Groq free -> Ollama local. Pydantic-validated, 3 retries each."""
from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import date

import requests
from pydantic import BaseModel, Field, ValidationError, field_validator

from .config import MAX_WORDS, MIN_WORDS, env

THEMES = [
    "awkward elevator small talk", "my pet judging my life choices", "adult life vs childhood expectations",
    "tech support phone calls", "gym motivation that lasts three days", "cooking disasters",
    "pointless office meetings", "airport security theater", "trying to sleep early", "grocery store self-checkout",
    "smartphone battery anxiety", "talking about the weather as a hobby", "group chat chaos", "online shopping regret",
    "learning to drive", "doing laundry wrong for years", "the one friend who is always late", "diet plans vs midnight snacks",
    "waking up before the alarm", "parking lot politics", "trying to be productive", "new year resolutions in february",
    "weird things said on hold music", "assembling furniture without the manual", "the wifi going down at the worst moment",
    "pretending to understand cryptic instructions", "overthinking a text message", "my houseplants dying again",
    "road trip snack negotiations", "the microwave countdown that makes you stare",
]


class FunnyScript(BaseModel):
    title: str = Field(min_length=5, max_length=100)
    script: str
    visual_keywords: list[str] = Field(min_length=3, max_length=12)

    @field_validator("title")
    @classmethod
    def _shorts_tag(cls, v: str) -> str:
        v = v.strip()
        if "#shorts" not in v.lower():
            v = (v[:90].rstrip() + " #Shorts")
        return v

    @field_validator("script")
    @classmethod
    def _length(cls, v: str) -> str:
        v = re.sub(r"\s+", " ", v).strip()
        n = len(v.split())
        if not (MIN_WORDS <= n <= MAX_WORDS):
            raise ValueError(f"script has {n} words; need {MIN_WORDS}-{MAX_WORDS} (30-60 s of speech)")
        return v

    @field_validator("visual_keywords")
    @classmethod
    def _kw(cls, v: list[str]) -> list[str]:
        out = [k.strip() for k in v if isinstance(k, str) and k.strip()]
        if len(out) < 3:
            raise ValueError("need at least 3 non-empty visual keywords")
        return out


SYSTEM = (
    "You are a stand-up comedy writer for YouTube Shorts, TikTok and Reels. "
    "Everything must be family-friendly: no profanity, slurs, real people, brand names, politics, "
    "tragedy or anything that mocks a group. Reply with ONE strict JSON object and nothing else."
)


def pick_theme(slot: str, today: date | None = None) -> str:
    today = today or date.today()
    h = int(hashlib.sha256(f"{today.isoformat()}-{slot}".encode()).hexdigest(), 16)
    return THEMES[h % len(THEMES)]


def build_prompt(theme: str, recent_titles: list[str]) -> str:
    avoid = "; ".join(recent_titles[-25:]) or "none yet"
    return (
        f"Write a funny stand-up style monologue about: {theme}.\n"
        f"- Spoken length {MIN_WORDS + 10}-{MAX_WORDS - 15} words (about 30-45 seconds).\n"
        "- A punchline roughly every 8 seconds (about every 20 words). Open with a hook, end on the biggest laugh.\n"
        "- First-person, deadpan, short sentences, plain narration text only (no stage directions, no emojis, no hashtags).\n"
        "- visual_keywords: 6-10 concrete English stock-footage search terms (1-3 words each, things a camera can film, "
        "e.g. 'tired man office', 'cat staring'), in the order they fit the script.\n"
        "- title: English, under 85 characters, ends with #Shorts.\n"
        f"- Do not repeat these recent titles or their jokes: {avoid}\n"
        'JSON shape: {"title": str, "script": str, "visual_keywords": [str]}'
    )


def _extract_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    m = re.search(r"\{.*\}", text, flags=re.S)
    if not m:
        raise ValueError("no JSON object in model reply")
    return json.loads(m.group(0))


def _post(url: str, **kw) -> requests.Response:
    for i in range(3):
        r = requests.post(url, timeout=120, **kw)
        if r.status_code in (429, 500, 502, 503):
            time.sleep(10 * (i + 1))
            continue
        r.raise_for_status()
        return r
    r.raise_for_status()
    return r


def call_gemini(system: str, prompt: str) -> str:
    key = env("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY not set")
    model = env("GEMINI_MODEL", "gemini-2.5-flash")
    r = _post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
              headers={"x-goog-api-key": key},
              json={"systemInstruction": {"parts": [{"text": system}]},
                    "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": 0.95, "responseMimeType": "application/json"}})
    return r.json()["candidates"][0]["content"]["parts"][0]["text"]


def call_groq(system: str, prompt: str) -> str:
    key = env("GROQ_API_KEY")
    if not key:
        raise RuntimeError("GROQ_API_KEY not set")
    r = _post("https://api.groq.com/openai/v1/chat/completions",
              headers={"Authorization": f"Bearer {key}"},
              json={"model": env("GROQ_MODEL", "llama-3.3-70b-versatile"), "temperature": 0.95,
                    "response_format": {"type": "json_object"},
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}]})
    return r.json()["choices"][0]["message"]["content"]


def call_ollama(system: str, prompt: str) -> str:
    host = env("OLLAMA_HOST")
    if not host:
        raise RuntimeError("OLLAMA_HOST not set")
    r = _post(f"{host.rstrip('/')}/api/chat",
              json={"model": env("OLLAMA_MODEL", "llama3.1:8b"), "stream": False, "format": "json",
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}]})
    return r.json()["message"]["content"]


PROVIDERS = [("gemini", call_gemini), ("groq", call_groq), ("ollama", call_ollama)]


def generate(slot: str, recent_titles: list[str] | None = None, providers=None,
             today: date | None = None, log=print) -> tuple[FunnyScript, str]:
    """Returns (script, provider_name). Each provider gets up to 3 validated attempts."""
    theme = pick_theme(slot, today)
    prompt = build_prompt(theme, recent_titles or [])
    errors: list[str] = []
    for name, fn in (providers or PROVIDERS):
        for attempt in range(1, 4):
            try:
                raw = fn(SYSTEM, prompt)
                fs = FunnyScript.model_validate(_extract_json(raw))
                log(f"script ok via {name} (attempt {attempt}, {len(fs.script.split())} words)")
                return fs, name
            except RuntimeError as e:          # provider not configured: skip it
                errors.append(f"{name}: {e}")
                break
            except (ValidationError, ValueError, KeyError, json.JSONDecodeError) as e:
                errors.append(f"{name} attempt {attempt}: invalid output ({str(e)[:160]})")
                prompt += "\nYour previous reply was invalid: " + str(e)[:200] + ". Return valid JSON that follows every rule."
            except requests.RequestException as e:
                errors.append(f"{name} attempt {attempt}: request failed ({str(e)[:160]})")
                time.sleep(3)
    raise RuntimeError("All script providers failed:\n" + "\n".join(errors[-9:]))
