"""Optional: write rotated tokens back to GitHub secrets/variables. Needs a fine-grained PAT in secret GH_PAT
(repository permissions: Secrets read/write, Variables read/write). GITHUB_TOKEN cannot write secrets."""
from __future__ import annotations

import os
import subprocess

from .config import env


def _gh(args: list[str]) -> bool:
    pat, repo = env("GH_PAT"), env("GITHUB_REPOSITORY")
    if not (pat and repo):
        return False
    e = {**os.environ, "GH_TOKEN": pat}
    p = subprocess.run(["gh", *args, "--repo", repo], env=e, capture_output=True, text=True)
    return p.returncode == 0


def set_secret(name: str, value: str, log=print) -> bool:
    ok = _gh(["secret", "set", name, "--body", value])
    if not ok:
        log(f"(could not save secret {name}: GH_PAT/GITHUB_REPOSITORY missing or gh failed)")
    return ok


def set_variable(name: str, value: str, log=print) -> bool:
    ok = _gh(["variable", "set", name, "--body", value])
    if not ok:
        log(f"(could not save variable {name})")
    return ok
