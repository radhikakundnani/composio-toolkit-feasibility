"""Cross-check #3 — do the cited docs actually say what the agent claims?

For every app, fetch the cited auth / access / MCP pages through Composio (KEENABLE_FETCH_URL_PUBLIC)
and look for the specific claim in the page text:
  auth   — each claimed method must be named on the auth page (oauth, api key, bearer/token, basic, jwt)
  access — the claimed access level must be stated (free plan / trial / pricing / contact sales / approval)
  mcp    — an 'official' MCP claim must mention MCP on the cited page
Then, for the apps where Composio's catalog and the agent disagree about OAuth, run a targeted
"<app> OAuth" search on the vendor's own domain and record which side the docs support.

    python pipeline/doccheck.py      # writes data/doccheck.json
"""
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from composio_tools import fetch, search  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
AUTH_TERMS = {
    "oauth2": r"oauth", "api_key": r"api[\s_-]?key|x-api-key|apikey", "bearer_token": r"bearer|access token|personal access token|api token",
    "basic": r"basic auth|basic authentication|http basic|-u\s", "jwt_service_account": r"jwt|key[\s-]?pair|service account|client credentials",
    "signature_hmac": r"hmac|signature",
}
ACCESS_TERMS = {
    "self_serve_free": r"\bfree\b", "self_serve_trial": r"\btrial\b", "paid_plan_required": r"\bplan\b|pricing|\$\d|per month|/mo",
    "approval_required": r"review|approv|apply|application|developer token|access level",
    "partner_or_sales_gated": r"contact (us|sales)|partner|account manager|customers? only|request access",
    "no_public_api": r"cli|command[- ]line|install|npm|pip",
}


def page(url):
    if not url:
        return None
    r = fetch(url, max_chars=20000)
    return r["content"].lower() if r["ok"] and r["content"] else None


def check(rec):
    ev = rec.get("evidence", {})
    out = {"app": rec["app"]}
    pa, pc, pm = page(ev.get("auth")), page(ev.get("access")), page(ev.get("mcp"))
    if pa is None:
        out["auth"] = "unreachable"
    else:
        claimed = [m for m in rec.get("auth_methods") or [] if m in AUTH_TERMS]
        found = {m: bool(re.search(AUTH_TERMS[m], pa)) for m in claimed}
        out["auth_methods_found"] = found
        out["auth"] = "supported" if found.get(rec.get("auth_primary"), False) else "primary_not_on_page"
    if pc is None:
        out["access"] = "unreachable"
    else:
        a = rec.get("access")
        out["access"] = "supported" if a in ACCESS_TERMS and re.search(ACCESS_TERMS[a], pc) else "not_stated"
    if rec.get("mcp") == "official":
        out["mcp"] = "unreachable" if pm is None else ("supported" if re.search(r"\bmcp\b|model context protocol", pm) else "not_stated")
    return out


def oauth_tiebreak(app, vendor_domain):
    r = search(f"{app} OAuth 2.0 authorization code client_id developer app", max_results=5, site=vendor_domain)
    hits = [x for x in r["results"] if re.search(r"oauth", (x["snippet"] or "").lower())]
    return {"query_log_id": r["log_id"], "vendor_domain": vendor_domain, "oauth_on_vendor_docs": bool(hits),
            "evidence": hits[0]["url"] if hits else None}


def main():
    final = {int(p.stem): json.loads(p.read_text()) for p in sorted((ROOT / "data/final").glob("*.json"))}
    with ThreadPoolExecutor(6) as ex:
        res = dict(zip(final, ex.map(check, final.values())))
    cat = json.loads((ROOT / "data/catalog_match.json").read_text())
    disputes = [int(k) for k, v in cat.items() if v["in_composio"] and v.get("oauth_agree") is False]
    for i in disputes:
        u = final[i].get("evidence", {}).get("auth") or ""
        host = urlparse(u).netloc
        dom = ".".join(host.split(".")[-2:]) if host else None
        res[i]["oauth_dispute"] = {"composio_auth": cat[str(i)]["composio_auth"], "agent_auth": final[i].get("auth_methods"),
                                   **(oauth_tiebreak(final[i]["app"], dom) if dom else {"oauth_on_vendor_docs": None})}
    (ROOT / "data/doccheck.json").write_text(json.dumps(res, indent=1))
    for f in ["auth", "access", "mcp"]:
        c = {}
        for v in res.values():
            if f in v:
                c[v[f]] = c.get(v[f], 0) + 1
        print(f, c)
    d = [v for v in res.values() if "oauth_dispute" in v]
    print(f"OAuth disputes: {len(d)} | vendor docs mention OAuth (agent right): {sum(1 for v in d if v['oauth_dispute']['oauth_on_vendor_docs'])}"
          f" | no OAuth found (Composio's key-only reading stands): {sum(1 for v in d if v['oauth_dispute']['oauth_on_vendor_docs'] is False)}")
    for v in d:
        print("  ", v["app"], "->", v["oauth_dispute"]["oauth_on_vendor_docs"], v["oauth_dispute"].get("evidence"))


if __name__ == "__main__":
    main()
