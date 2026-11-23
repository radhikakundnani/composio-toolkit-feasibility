"""Thin wrapper over Composio tool-router sessions for web research.

Every call is cached on disk (data/cache/) keyed by tool + arguments, and every
cached record keeps Composio's log_id so any piece of evidence can be traced back
to the exact tool execution that produced it.

CLI (used by the extraction/verifier subagents when they need more evidence):
    python pipeline/composio_tools.py search "Gladly API authentication"
    python pipeline/composio_tools.py search "Gladly API" --site gladly.com
    python pipeline/composio_tools.py fetch https://developer.gladly.com/rest
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))
from redact import redact_obj  # noqa: E402  — never cache credential-shaped strings from scraped pages

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "cache"
CACHE.mkdir(parents=True, exist_ok=True)
load_dotenv(ROOT / ".env")

SEARCH_TOOL = "KEENABLE_SEARCH_WEB_PUBLIC"   # discovered at runtime via session.search()
FETCH_TOOL = "KEENABLE_FETCH_URL_PUBLIC"
USER_ID = "takehome-pipeline"

_session = None


def session():
    global _session
    if _session is None:
        from composio import Composio
        _session = Composio().create(user_id=USER_ID)
    return _session


def _key(tool: str, args: dict) -> Path:
    h = hashlib.sha1(json.dumps([tool, args], sort_keys=True).encode()).hexdigest()[:16]
    return CACHE / f"{tool.lower()}_{h}.json"


def _execute(tool: str, args: dict, retries: int = 3) -> dict:
    path = _key(tool, args)
    if path.exists():
        return json.loads(path.read_text())
    last = None
    for attempt in range(retries):
        try:
            r = session().execute(tool, arguments=args)
            d = r.model_dump() if hasattr(r, "model_dump") else dict(r)
            data = d.get("data") or {}
            status = data.get("status_code") if isinstance(data, dict) else None
            rec = {"tool": tool, "args": args, "log_id": d.get("log_id"),
                   "ok": status in (None, 200) and not d.get("error"),
                   "error": d.get("error") or (data.get("message") if status not in (None, 200) else None),
                   "data": redact_obj(data), "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
            if rec["ok"]:  # only cache successes, so rate-limited calls are retried later
                path.write_text(json.dumps(rec))
            return rec
        except Exception as e:  # network / 5xx
            last = str(e)
            time.sleep(2 * (attempt + 1))
    return {"tool": tool, "args": args, "ok": False, "error": last, "data": {}}


def search(query: str, max_results: int = 5, site: str | None = None, snippet_chars: int = 1200) -> dict:
    args = {"query": query, "keenable_title": query[:60], "max_results": max_results}
    if site:
        args["site"] = site
    rec = _execute(SEARCH_TOOL, args)
    results = [{"url": x.get("url"), "title": x.get("title"),
                "snippet": (x.get("snippet") or x.get("description") or "")[:snippet_chars]}
               for x in (rec.get("data") or {}).get("results", [])] if rec["ok"] else []
    return {"query": query, "log_id": rec.get("log_id"), "ok": rec["ok"], "error": rec.get("error"), "results": results}


def fetch(url: str, max_chars: int = 15000, prompt: str | None = None) -> dict:
    args = {"url": url, "keenable_title": url[:60], "max_chars": max_chars}
    if prompt:
        args["prompt"] = prompt
    rec = _execute(FETCH_TOOL, args)
    data = rec.get("data") or {}
    return {"url": url, "log_id": rec.get("log_id"), "ok": rec["ok"], "error": rec.get("error"),
            "content": data.get("content") or data.get("markdown") or data.get("text") or ""}


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search"); s.add_argument("query"); s.add_argument("--site"); s.add_argument("-n", type=int, default=5)
    f = sub.add_parser("fetch"); f.add_argument("url"); f.add_argument("--max", type=int, default=12000)
    a = p.parse_args()
    out = search(a.query, a.n, a.site) if a.cmd == "search" else fetch(a.url, a.max)
    json.dump(out, sys.stdout, indent=1)
    print()
