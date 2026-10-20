#!/usr/bin/env python3
"""
fetch_automation_repo.py - Fetch or sync the automation repository to local cache.

Supports local directories (side-by-side), github.com, *.ghe.com (EU residency), and GHES.
Standard library only (Python 3.9+).
"""

import argparse
import datetime
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.parse
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


def extract_host_from_repo(repo_url: str) -> str:
    """Extracts hostname from git URL (https:// or git@)."""
    if repo_url.startswith("git@"):
        # git@host:org/repo.git
        match = re.match(r'^git@([^:]+):', repo_url)
        return match.group(1) if match else "github.com"
    elif "://" in repo_url:
        parsed = urllib.parse.urlparse(repo_url)
        return parsed.hostname or "github.com"
    return "local"


def is_local_path(repo_target: str) -> bool:
    """Checks whether the target is a local file system path."""
    if os.path.exists(repo_target):
        return True
    if repo_target.startswith(".") or repo_target.startswith("/") or re.match(r'^[a-zA-Z]:\\', repo_target):
        return True
    return False


def get_commit_sha(repo_dir: str) -> str:
    """Retrieves current HEAD commit SHA."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        if res.returncode == 0:
            return res.stdout.strip()
    except Exception:
        pass
    return "local-head"


def fetch_or_clone_repo(
    repo_url_or_path: str,
    branch: str = "main",
    cache_root: Optional[str] = None
) -> Dict[str, Any]:
    """Clones or updates the automation repository, returning metadata."""
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    # Case 1: Local repository path (e.g. side-by-side clone)
    if is_local_path(repo_url_or_path):
        abs_path = os.path.abspath(repo_url_or_path)
        if not os.path.exists(abs_path):
            raise FileNotFoundError(f"Local automation repo path not found: {abs_path}")
        commit = get_commit_sha(abs_path)
        sys.stderr.write(f"Using local automation repo at: {abs_path} (commit: {commit})\n")
        return {
            "path": abs_path,
            "commit": commit,
            "host": "local",
            "branch": branch,
            "fetched_at": now_iso
        }

    # Case 2: Remote repository (HTTPS or SSH)
    host = extract_host_from_repo(repo_url_or_path)

    # Cache directory: ~/.rts-cache/<hash>
    if not cache_root:
        home_dir = os.path.expanduser("~")
        cache_root = os.path.join(home_dir, ".rts-cache")

    repo_hash = hashlib.sha256(repo_url_or_path.encode()).hexdigest()[:16]
    target_cache_dir = os.path.join(cache_root, repo_hash)

    os.makedirs(cache_root, exist_ok=True)

    if os.path.exists(os.path.join(target_cache_dir, ".git")):
        sys.stderr.write(f"Updating existing cache at {target_cache_dir} from {host}...\n")
        # Fetch latest
        fetch_cmd = ["git", "fetch", "--depth=1", "origin", branch]
        res = subprocess.run(fetch_cmd, cwd=target_cache_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode != 0:
            sys.stderr.write(f"Fetch failed: {res.stderr}\n")
            if "Authentication failed" in res.stderr or "Permission denied" in res.stderr or "could not read Username" in res.stderr:
                sys.stderr.write(
                    f"\n[RTS Error] Authentication failed for host '{host}'.\n"
                    f"Hint: Authenticate your GitHub CLI credentials by running:\n"
                    f"    gh auth login --hostname {host}\n\n"
                )
            raise RuntimeError(f"Failed to fetch {repo_url_or_path} (exit code {res.returncode})")

        # Checkout
        checkout_cmd = ["git", "checkout", "FETCH_HEAD"]
        subprocess.run(checkout_cmd, cwd=target_cache_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    else:
        sys.stderr.write(f"Cloning shallow repository into {target_cache_dir} from {host}...\n")
        clone_cmd = [
            "git", "clone", "--depth=1", "--branch", branch,
            "--single-branch", repo_url_or_path, target_cache_dir
        ]
        res = subprocess.run(clone_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode != 0:
            sys.stderr.write(f"Clone failed: {res.stderr}\n")
            if "Authentication failed" in res.stderr or "Permission denied" in res.stderr or "could not read Username" in res.stderr:
                sys.stderr.write(
                    f"\n[RTS Error] Authentication failed for host '{host}'.\n"
                    f"Hint: Authenticate your GitHub CLI credentials by running:\n"
                    f"    gh auth login --hostname {host}\n\n"
                )
            raise RuntimeError(f"Failed to clone {repo_url_or_path} (exit code {res.returncode})")

    commit = get_commit_sha(target_cache_dir)
    return {
        "path": target_cache_dir,
        "commit": commit,
        "host": host,
        "branch": branch,
        "fetched_at": now_iso
    }


def main():
    parser = argparse.ArgumentParser(
        description="Fetch or sync the automation repository for test selection."
    )
    parser.add_argument(
        "--repo",
        type=str,
        required=True,
        help="Automation repository URL or local filesystem path."
    )
    parser.add_argument(
        "--branch",
        type=str,
        default="main",
        help="Branch to fetch (default: main)."
    )
    parser.add_argument(
        "--cache-dir",
        type=str,
        help="Custom cache root directory (defaults to ~/.rts-cache)."
    )

    args = parser.parse_args()

    try:
        result = fetch_or_clone_repo(
            repo_url_or_path=args.repo,
            branch=args.branch,
            cache_root=args.cache_dir
        )
    except Exception as e:
        sys.stderr.write(f"Error: {e}\n")
        sys.exit(1)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
