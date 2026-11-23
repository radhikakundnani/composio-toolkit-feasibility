"""Cross-check #2 — Composio's own catalog as an independent source.

Pulls Composio's toolkit catalog (composio.toolkits.list → data/composio_catalog.json) and, for each of
the 100 apps, records whether Composio already ships a toolkit, its auth schemes, tool count, and
whether a provider-MCP toolkit (<slug>_mcp) also exists. Then compares Composio's auth schemes with the
agent's auth answer.

    python pipeline/catalog.py            # writes data/catalog_match.json
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
norm = lambda s: re.sub(r"[^a-z0-9]", "", (s or "").lower())

# Human-reviewed overrides: names whose catalog slug differs from the app name, or that need disambiguation.
# None = verified absent (searched the catalog by hand).
MANUAL = {
    "Zoho CRM": "zoho", "Close": "close", "Lark (Larksuite)": "lark", "WhatsApp Business": "whatsapp",
    "Google Ads": "googleads", "Meta Ads": "metaads", "LinkedIn Ads": "linkedin_ads", "GoHighLevel": "highlevel_location", "Threads (Meta)": "threads",
    "Magento (Adobe Commerce)": None, "Amazon Selling Partner": None,  # catalog "amazon" is a 0-tool stub, not SP-API
    "Salesforce Commerce Cloud": None,
    "Monday.com": "monday", "MongoDB Atlas": "mongodb", "Help Scout": "help_scout", "Zoho Cliq": "zoho_cliq",
    "YouTube Transcript": "youtube_transcript", "Mermaid CLI": None,  # catalog mermaid_chart_mcp is Mermaid Chart (SaaS), a different product
    "Sherlock": None, "Paygent Connect": None,
    "Otter AI": "otter_ai_mcp", "Pylon": "pylon_mcp", "Netlify": "netlify_mcp", "Devin": "devin_mcp",
    "Ecwid": None,  # catalog "lightspeed" is Lightspeed Retail, not Ecwid
    "Waterfall.io": None, "SE Ranking": None, "Bright Data": "brightdata",
}

AUTH_MAP = {"OAUTH2": "oauth2", "OAUTH1": "oauth2", "API_KEY": "api_key", "BEARER_TOKEN": "bearer_token",
            "BASIC": "basic", "BASIC_WITH_JWT": "basic", "SERVICE_ACCOUNT": "jwt_service_account",
            "GOOGLE_SERVICE_ACCOUNT": "jwt_service_account", "NO_AUTH": "none", "SAML": "other", "DCR_OAUTH": "oauth2"}
KEYISH = {"api_key", "bearer_token", "basic"}


def main():
    cat = json.loads((ROOT / "data/composio_catalog.json").read_text())
    by_slug = {t["slug"]: t for t in cat}
    by_norm = {}
    for t in cat:
        for k in {norm(t["slug"]), norm(t["name"])}:
            by_norm.setdefault(k, t)
    apps = json.loads((ROOT / "data/apps.json").read_text())
    final = {int(p.stem): json.loads(p.read_text()) for p in (ROOT / "data/final").glob("*.json")}
    out, unmatched = {}, []
    for a in apps:
        name = a["app"]
        if name in MANUAL:
            t = by_slug.get(MANUAL[name]) if MANUAL[name] else None
            how = "manual"
        else:
            base = norm(re.sub(r"\(.*?\)", "", name))
            t = by_norm.get(base)
            how = "auto"
            if t is None:
                unmatched.append(name)
        mcp_t = by_slug.get((t["slug"] if t else norm(name)) + "_mcp") if True else None
        rec = {"app": name, "match": how, "in_composio": bool(t), "slug": t and t["slug"],
               "auth_schemes": t and t.get("auth_schemes"), "managed_auth": t and t.get("composio_managed_auth_schemes"),
               "tools": t and (t.get("meta") or {}).get("tools_count"),
               "triggers": t and (t.get("meta") or {}).get("triggers_count"),
               "provider_mcp_toolkit": bool(mcp_t) or bool(t and t["slug"].endswith("_mcp")),
               "mcp_only": bool(t and t["slug"].endswith("_mcp")),
               "provider_mcp_slug": (mcp_t and mcp_t["slug"]) or (t and t["slug"].endswith("_mcp") and t["slug"]) or None}
        # auth agreement: does Composio support the agent's primary auth? does it support the same family?
        r = final[a["id"]]
        if t and t.get("auth_schemes"):
            cs = {AUTH_MAP.get(s, "other") for s in t["auth_schemes"]}
            agent = set(r.get("auth_methods") or []) - {"unknown"}
            prim = r.get("auth_primary")
            fam = lambda s: "oauth" if s == "oauth2" else ("key" if s in KEYISH else s)
            rec["composio_auth"] = sorted(cs)
            rec["primary_supported"] = prim in cs or fam(prim) in {fam(x) for x in cs}
            rec["oauth_agree"] = ("oauth2" in cs) == ("oauth2" in agent)
            rec["agent_only"] = sorted({fam(x) for x in agent} - {fam(x) for x in cs})
            rec["composio_only"] = sorted({fam(x) for x in cs} - {fam(x) for x in agent})
        out[a["id"]] = rec
    (ROOT / "data/catalog_match.json").write_text(json.dumps(out, indent=1))
    inc = [v for v in out.values() if v["in_composio"]]
    print(f"native API toolkit: {sum(1 for v in inc if not v['mcp_only'])} | MCP-only: {sum(v['mcp_only'] for v in inc)} | in Composio: {len(inc)}/100 | provider-MCP toolkits: {sum(v['provider_mcp_toolkit'] for v in out.values())}")
    print("primary auth supported by Composio:", sum(v.get("primary_supported", False) for v in inc), "/", len(inc))
    print("OAuth presence agrees:", sum(v.get("oauth_agree", False) for v in inc), "/", len(inc))
    print("auto-unmatched (need a human look):", unmatched)
    print("NOT in Composio:", [v["app"] for v in out.values() if not v["in_composio"]])
    print("disagree oauth:", [(v["app"], v.get("composio_auth"), final[k].get("auth_methods")) for k, v in out.items() if v["in_composio"] and not v.get("oauth_agree")])


if __name__ == "__main__":
    main()
