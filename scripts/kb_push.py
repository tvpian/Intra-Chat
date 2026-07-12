#!/usr/bin/env python3
"""
kb_push.py — Push knowledge into Intra-Chat's Knowledge Base API.

Reads configuration from the environment:
  INTRA_CHAT_URL      Base URL of the server, e.g. http://localhost:5656
  INTRA_CHAT_KEY      Your project's API key (ic_<project>_<hex>)
  INTRA_CHAT_PROJECT  Your project_id (must match the key's project)

Examples:
  # Single note from a file
  python3 kb_push.py --title "Deploy steps" --file NOTES.md

  # Inline content, tagged, made team-visible
  python3 kb_push.py --title "Ping" --content "hello" --tag ops --team

  # Push every *.md under a directory as separate private entries
  python3 kb_push.py --scan docs --tag docs
"""
import argparse
import json
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path


def _env(name: str) -> str:
    val = os.environ.get(name, "").strip()
    if not val:
        sys.exit(f"error: environment variable {name} is not set")
    return val


def post_entry(base_url: str, api_key: str, project_id: str,
               title: str, content: str, tags, visibility: str):
    payload = {
        "title": title,
        "content": content,
        "tags": tags,
        "project_id": project_id,
        "visibility": visibility,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        base_url.rstrip("/") + "/api/braindump",
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return True, body
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read().decode("utf-8"))
        except Exception:
            err = {"error": str(e)}
        return False, {"status": e.code, **err}
    except urllib.error.URLError as e:
        return False, {"error": f"connection failed: {e.reason}"}


def main():
    ap = argparse.ArgumentParser(description="Push notes to Intra-Chat Knowledge Base")
    ap.add_argument("--title", help="Entry title")
    ap.add_argument("--content", help="Inline content (markdown)")
    ap.add_argument("--file", help="Read content from this file")
    ap.add_argument("--scan", help="Directory: push every *.md file as its own entry")
    ap.add_argument("--tag", action="append", default=[], help="Tag (repeatable)")
    ap.add_argument("--team", action="store_true",
                    help="Make entry team-visible (default is private)")
    args = ap.parse_args()

    base_url = _env("INTRA_CHAT_URL")
    api_key = _env("INTRA_CHAT_KEY")
    project_id = _env("INTRA_CHAT_PROJECT")
    visibility = "team" if args.team else "private"

    entries = []
    if args.scan:
        root = Path(args.scan)
        if not root.is_dir():
            sys.exit(f"error: --scan path is not a directory: {root}")
        for md in sorted(root.rglob("*.md")):
            entries.append((md.stem, md.read_text(encoding="utf-8", errors="replace")))
        if not entries:
            sys.exit(f"error: no *.md files found under {root}")
    else:
        if args.file:
            content = Path(args.file).read_text(encoding="utf-8", errors="replace")
            title = args.title or Path(args.file).stem
        else:
            content = args.content
            title = args.title
        if not content:
            sys.exit("error: provide --content, --file, or --scan")
        if not title:
            sys.exit("error: provide --title (or use --file/--scan to derive it)")
        entries.append((title, content))

    failures = 0
    for title, content in entries:
        ok, result = post_entry(base_url, api_key, project_id,
                                 title, content, args.tag, visibility)
        if ok:
            print(f"[ok] {result.get('id')}  {title}  ({visibility})")
        else:
            failures += 1
            print(f"[FAIL] {title}: {result}", file=sys.stderr)

    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
