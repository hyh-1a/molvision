"""Create a GitHub repo and upload the MolVision source tree via the REST API.

Usage (PowerShell):
    $env:GITHUB_TOKEN = "ghp_xxx"
    python scripts/upload_to_github.py --repo molvision

The token is read from the environment and never written to disk.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.github.com"
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SRC = Path(r"E:\MolVisionData\molvision-source")
SKIP_DIRS = {".git", "__pycache__", ".venv"}
SKIP_SUFFIX = {".pyc"}


def request(method: str, url: str, token: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", "molvision-submit")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = resp.read()
        return json.loads(body) if body else {}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default="molvision")
    ap.add_argument("--src", default=str(DEFAULT_SRC))
    ap.add_argument("--private", action="store_true")
    ap.add_argument("--description", default="Structure image to SMILES / 3D / descriptors, local-first")
    args = ap.parse_args()

    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        sys.exit("GITHUB_TOKEN is not set")
    src = Path(args.src)
    if not src.exists():
        sys.exit(f"source dir not found: {src}")

    user = request("GET", f"{API}/user", token)
    login = user["login"]
    print(f"authenticated as {login}")

    try:
        repo = request("POST", f"{API}/user/repos", token, {
            "name": args.repo,
            "description": args.description,
            "private": bool(args.private),
            "has_issues": True,
            "has_wiki": False,
            "auto_init": False,
        })
        print("created repo:", repo["html_url"])
    except urllib.error.HTTPError as exc:
        if exc.code == 422:
            repo = request("GET", f"{API}/repos/{login}/{args.repo}", token)
            print("repo already exists:", repo["html_url"])
        else:
            raise

    files = []
    for path in sorted(src.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(src)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        if path.suffix in SKIP_SUFFIX:
            continue
        files.append((path, rel.as_posix()))
    print(f"uploading {len(files)} files ...")

    branch = repo.get("default_branch") or "main"
    first = True
    for i, (path, rel) in enumerate(files, 1):
        content = base64.b64encode(path.read_bytes()).decode()
        payload = {
            "message": f"Add {rel}",
            "content": content,
        }
        if not first:
            payload["branch"] = branch
        url = f"{API}/repos/{login}/{args.repo}/contents/{urllib.parse.quote(rel)}"
        for attempt in range(3):
            try:
                request("PUT", url, token, payload)
                break
            except urllib.error.HTTPError as exc:
                if exc.code in (409, 422) and "sha" in (exc.read().decode(errors="ignore")):
                    # file exists: fetch sha then update
                    info = request("GET", url, token)
                    payload["sha"] = info["sha"]
                    request("PUT", url, token, payload)
                    break
                if attempt == 2:
                    raise
                time.sleep(2)
        first = False
        if i % 20 == 0:
            print(f"  {i}/{len(files)}")

    print("done:", repo["html_url"])
    print("commit:", f"{repo['html_url']}/commits/{branch}")


if __name__ == "__main__":
    import urllib.parse  # noqa: E402  (used in URL quoting)

    main()
