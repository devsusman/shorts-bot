#!/usr/bin/env python3
"""Upload secrets from a local file to GitHub in one go (needs the GitHub CLI: `gh auth login` first).
Usage: copy .env.secrets.example to .env.secrets, fill it in, then:
    python tools/set_secrets.py OWNER/REPO
Lines starting with VAR_ become repository *variables* (without the prefix); everything else becomes a *secret*.
Empty values are skipped. Never commit .env.secrets (it is in .gitignore)."""
import pathlib
import subprocess
import sys

if len(sys.argv) != 2 or "/" not in sys.argv[1]:
    sys.exit(__doc__)
repo = sys.argv[1]
f = pathlib.Path(".env.secrets")
if not f.exists():
    sys.exit(".env.secrets not found")
for line in f.read_text().splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, v = line.split("=", 1)
    k, v = k.strip(), v.strip().strip('"').strip("'")
    if not v:
        continue
    kind = "variable" if k.startswith("VAR_") else "secret"
    name = k[4:] if kind == "variable" else k
    p = subprocess.run(["gh", kind, "set", name, "--repo", repo, "--body", v], capture_output=True, text=True)
    print(("OK   " if p.returncode == 0 else "FAIL ") + f"{kind} {name}" + ("" if p.returncode == 0 else f": {p.stderr.strip()}"))
