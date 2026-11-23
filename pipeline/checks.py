"""Stage 3a — deterministic verification checks (no LLM).

Runs over every record of a version and writes data/<version>_flags.json:
  - citation:     every cited URL must appear in the app's evidence bundle
  - dead_link:    cited URLs are requested live; 4xx/5xx/unreachable are flagged
  - unknown:      any core field left 'unknown'
  - low_conf:     any field with confidence 'low'
  - identity:     extraction agent reported a possible name collision
  - mcp_provenance: mcp='official' but the cited MCP source is not on the vendor's
                  own domain (third-party directories, random GitHub users)
  - consistency:  gated access but verdict 'ready'; caveats verdict with blocker 'none';
                  blocker 'other' (schema escape hatch)

    python pipeline/checks.py v1
"""
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
GATED = {"paid_plan_required", "approval_required", "partner_or_sales_gated", "no_public_api"}
THIRD_PARTY_MCP_HOSTS = ("mcpservers.org", "mcpmarket", "mymcptools", "lobehub", "smithery", "glama", "pulsemcp",
                         "mcp.so", "npmjs.com", "npm.io", "pipedream", "zapier", "activepieces", "composio",
                         "viasocket", "playbooks.com", "mcptoplist", "smallprint.dev", "apify.com/")


def domain(url: str) -> str:
    host = urlparse(url or "").netloc.lower().split(":")[0]
    parts = host.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def http_status(url: str) -> int:
    try:
        out = subprocess.run(["curl", "-s", "-o", "/dev/null", "-L", "-m", "15", "-A", "Mozilla/5.0",
                              "-w", "%{http_code}", url], capture_output=True, text=True, timeout=25)
        return int(out.stdout or 0)
    except Exception:
        return 0


def check(version: str):
    recs = {int(p.stem): json.loads(p.read_text()) for p in sorted((ROOT / "data" / version).glob("*.json"))}
    urls = sorted({u for r in recs.values() for u in r.get("evidence", {}).values() if u})
    with ThreadPoolExecutor(12) as ex:
        status = dict(zip(urls, ex.map(http_status, urls)))
    # every URL any Composio tool call returned (first-pass bundles + verifier searches/fetches, from the cache)
    composio_urls = set()
    for c in (ROOT / "data/cache").glob("*.json"):
        rec = json.loads(c.read_text())
        if rec["tool"].endswith("FETCH_URL_PUBLIC"):
            composio_urls.add(rec["args"]["url"])
        for x in (rec.get("data") or {}).get("results", []) or []:
            composio_urls.add(x.get("url"))
    out = {}
    for i, r in recs.items():
        ev = json.loads((ROOT / f"data/evidence/{i:03d}.json").read_text())
        bundle_urls = {x["url"] for q in ev["queries"].values() for x in q["results"]} | composio_urls
        vendor_domains = {domain(u) for k, u in r.get("evidence", {}).items() if k in ("auth", "surface") and u}
        vendor_domains.add(domain("https://" + ev["hint"].split(" ")[0]))
        flags = []
        for k, u in r.get("evidence", {}).items():
            if not u:
                continue
            if u not in bundle_urls:
                flags.append(f"citation:{k} not seen in any Composio tool output")
            s = status.get(u, 0)
            if s >= 400 or s == 0:
                if s not in (401, 403, 429):  # bot walls are not dead links
                    flags.append(f"dead_link:{k} -> HTTP {s}")
        core = {"auth_primary": r.get("auth_primary"), "access": r.get("access"), "api_breadth": r.get("api_breadth")}
        flags += [f"unknown:{k}" for k, v in core.items() if v == "unknown"]
        flags += [f"low_conf:{k}" for k, v in r.get("confidence", {}).items() if v == "low"]
        if r.get("identity_issue"):
            flags.append("identity: " + r["identity_issue"][:80])
        if r.get("mcp") == "official":
            mu = r.get("evidence", {}).get("mcp") or ""
            if not mu:
                flags.append("mcp_provenance: official but no MCP citation")
            elif any(h in mu for h in THIRD_PARTY_MCP_HOSTS) or domain(mu) not in vendor_domains | {"github.com"}:
                flags.append(f"mcp_provenance: official claimed from third-party source {domain(mu)}")
            elif domain(mu) == "github.com":
                flags.append("mcp_provenance: GitHub source, confirm org belongs to vendor")
        if r.get("access") in GATED and r.get("verdict") == "ready":
            flags.append("consistency: gated access but verdict ready")
        if r.get("verdict") == "ready_with_caveats" and r.get("blocker") == "none":
            flags.append("consistency: caveats verdict but blocker none")
        if r.get("blocker") == "other":
            flags.append("consistency: blocker 'other' (unclassified)")
        out[i] = {"app": r["app"], "flags": flags}
    path = ROOT / f"data/{version}_flags.json"
    path.write_text(json.dumps({"url_status": status, "apps": out}, indent=1))
    n_flagged = sum(1 for v in out.values() if v["flags"])
    kinds = {}
    for v in out.values():
        for f in v["flags"]:
            kinds[f.split(":")[0]] = kinds.get(f.split(":")[0], 0) + 1
    print(f"{version}: {n_flagged}/{len(out)} apps flagged; flags by type: {kinds}")
    print(f"cited URLs checked live: {len(status)}, dead: {sum(1 for s in status.values() if s >= 400 and s not in (401, 403, 429) or s == 0)}")


if __name__ == "__main__":
    check(sys.argv[1])
