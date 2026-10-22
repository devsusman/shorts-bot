"""Healthchecks.io dead-man's-switch pings. Usage: python -m shorts.healthchecks start|success|fail ["message"]
Env HC_URL is the full ping URL of this slot's check (https://hc-ping.com/<uuid>). Missing URL = no-op.
Standard library only, so it still works when the dependency install step is what failed."""
from __future__ import annotations

import os
import sys
import urllib.request

SUFFIX = {"start": "/start", "success": "", "fail": "/fail"}


def ping(kind: str, body: str = "") -> bool:
    url = os.environ.get("HC_URL", "").strip()
    if not url:
        print("HC_URL not set; skipping Healthchecks ping")
        return False
    req = urllib.request.Request(url.rstrip("/") + SUFFIX[kind], data=body[:9000].encode("utf-8"), method="POST")
    for _ in range(3):
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                if 200 <= r.status < 300:
                    return True
        except Exception:  # noqa: BLE001
            pass
    print(f"Healthchecks ping '{kind}' failed")
    return False


if __name__ == "__main__":
    ping(sys.argv[1], " ".join(sys.argv[2:]))
