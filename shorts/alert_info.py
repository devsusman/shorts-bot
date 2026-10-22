"""Builds the failure/skip alert text: which time slot, which step failed, link to the run log.
Reads the job `steps` context (JSON) from env STEPS_JSON. Writes subject/body to $GITHUB_OUTPUT."""
from __future__ import annotations

import json
import os
import uuid

STEP_NAMES = {
    "guard": "Time verification", "apt": "Install ffmpeg", "pip": "Install Python packages",
    "hc_start": "Healthchecks start ping", "run": "Generate + render + publish video",
    "commit": "Commit status page",
}


def failed_step(steps_json: str) -> str:
    try:
        steps = json.loads(steps_json or "{}")
    except json.JSONDecodeError:
        return "unknown (could not read steps)"
    for sid, s in steps.items():
        if s.get("outcome") == "failure":
            return STEP_NAMES.get(sid, sid)
    return "unknown (an earlier step or the job setup failed)"


def build(kind: str, slot: str, steps_json: str, run_url: str, extra: str = "") -> tuple[str, str]:
    if kind == "skip":
        return (f"[Shorts bot] {slot} run SKIPPED (delayed)",
                f"The {slot} workflow started too late and was skipped.\n{extra}\n\nRun log: {run_url}")
    if kind == "reminder":
        return (f"[Shorts bot] Action needed ({slot})", f"{extra}\n\nRun log: {run_url}")
    step = failed_step(steps_json)
    return (f"[Shorts bot] {slot} run FAILED at: {step}",
            f"Time slot: {slot}\nFailing step: {step}\n{extra}\nRun log: {run_url}")


def _out(key: str, value: str) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        print(f"{key}: {value}")
        return
    delim = "EOF_" + uuid.uuid4().hex
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"{key}<<{delim}\n{value}\n{delim}\n")


def main() -> None:
    kind = os.environ.get("ALERT_KIND", "failure")
    slot = os.environ.get("SLOT", "?")
    url = f"{os.environ.get('GITHUB_SERVER_URL', 'https://github.com')}/{os.environ.get('GITHUB_REPOSITORY', '')}" \
          f"/actions/runs/{os.environ.get('GITHUB_RUN_ID', '')}"
    subject, body = build(kind, slot, os.environ.get("STEPS_JSON", "{}"), url, os.environ.get("ALERT_EXTRA", ""))
    _out("subject", subject)
    _out("body", body)


if __name__ == "__main__":
    main()
