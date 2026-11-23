"""Redact credential-shaped strings from scraped web text.

Vendor docs often contain sample (or leaked) tokens: Slack xox*, Discord bot tokens, Twilio SIDs,
Stripe keys, etc. We never need them for research, and they must not be published. composio_tools.py
applies redact() before anything is cached; run this file to clean existing data:

    python pipeline/redact.py data site      # rewrites matching files in place, prints counts
"""
import re
import sys
from pathlib import Path

PATTERNS = {
    "discord_bot_token": r"[MNO][A-Za-z\d]{23,27}\.[\w-]{6}\.[\w-]{27,40}",
    "slack_token": r"xox[abposre]-[A-Za-z0-9-]{10,}",
    "slack_webhook": r"https://hooks\.slack\.com/services/[A-Za-z0-9/]{20,}",
    "twilio_sid": r"\b(?:AC|SK|PN|MG)[a-f0-9]{32}\b",
    "github_token": r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{40,})",
    "stripe_key": r"\b(?:sk|rk|pk|whsec)_(?:live|test)_[A-Za-z0-9]{10,}",
    "aws_access_key": r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b",
    "google_api_key": r"\bAIza[0-9A-Za-z_-]{35}\b",
    "openai_anthropic_key": r"\bsk-(?:ant-|proj-)?[A-Za-z0-9_-]{24,}",
    "jwt": r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}",
    "private_key": r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----",
    "composio_key": r"\bak_[A-Za-z0-9]{16,}",
}
RX = [(k, re.compile(p)) for k, p in PATTERNS.items()]


def redact(text: str) -> tuple[str, dict]:
    hits = {}
    for name, rx in RX:
        text, n = rx.subn(f"[REDACTED_{name.upper()}]", text)
        if n:
            hits[name] = n
    return text, hits


def redact_obj(obj):
    """Recursively redact every string in a JSON-like object."""
    if isinstance(obj, str):
        return redact(obj)[0]
    if isinstance(obj, list):
        return [redact_obj(x) for x in obj]
    if isinstance(obj, dict):
        return {k: redact_obj(v) for k, v in obj.items()}
    return obj


if __name__ == "__main__":
    total, files = {}, 0
    for root in sys.argv[1:] or ["data", "site"]:
        for p in Path(root).rglob("*"):
            if not p.is_file() or p.suffix not in {".json", ".html", ".log", ".md", ".txt"}:
                continue
            t = p.read_text(errors="ignore")
            new, hits = redact(t)
            if hits:
                p.write_text(new)
                files += 1
                for k, v in hits.items():
                    total[k] = total.get(k, 0) + v
    print(f"redacted {sum(total.values())} strings in {files} files:", total)
