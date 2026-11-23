"""Deep analysis over the verified dataset + the three cross-checks → data/analysis.json

  1. calibration     — did the first-pass agent's self-reported confidence predict which answers the
                       verifier later changed?
  2. evidence        — share of citations on the vendor's own domain, first pass vs final
  3. triangulation   — per app: agent vs Composio catalog (auth) vs fetched docs (auth/access/MCP)
                       vs hand check (sample); agreement counts per source pair
  4. priority        — ease-of-access × API depth quadrant, with Composio coverage → build-next list
  5. error map       — where the verifier changed answers, by category × field
"""
import collections as C
import json
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
VALUE = ["access", "mcp", "auth_primary", "verdict", "blocker"]
CONF_FIELD = {"access": "access", "mcp": "mcp", "auth_primary": "auth"}
EASE = {"self_serve_free": 1.0, "self_serve_trial": 0.85, "paid_plan_required": 0.6, "approval_required": 0.4,
        "partner_or_sales_gated": 0.15, "no_public_api": 0.0, "unknown": 0.3}
# Human classification of what each OAuth hit actually was (read each vendor page; see adjudications.json)
OAUTH_CLASS = {"rest_api_oauth": ["Twenty", "Close", "Copper", "Freshdesk", "Plain", "Twilio", "Pumble", "Firecrawl", "Cloudflare", "MongoDB Atlas", "Grain"],
               "mcp_server_oauth_only": ["DataForSEO", "Bright Data", "Clay", "higgsfield", "Consensus"],
               "weak_or_wrong_product": ["MrScraper", "Apify", "Plaid"], "no_oauth": ["PitchBook"]}
DEPTH = {"broad": 1.0, "moderate": 0.6, "narrow": 0.3, "none": 0.0, "unknown": 0.4}


def load(d):
    return {int(p.stem): json.loads(p.read_text()) for p in sorted((ROOT / "data" / d).glob("*.json"))}


def dom(u):
    h = urlparse(u or "").netloc.lower()
    return ".".join(h.split(".")[-2:]) if h else ""


def main():
    apps = {a["id"]: a for a in json.loads((ROOT / "data/apps.json").read_text())}
    v1, fin = load("v1"), load("final")
    cat = {int(k): v for k, v in json.loads((ROOT / "data/catalog_match.json").read_text()).items()}
    docs = {int(k): v for k, v in json.loads((ROOT / "data/doccheck.json").read_text()).items()}
    gt = {int(k): v for k, v in json.loads((ROOT / "data/ground_truth.json").read_text()).items() if not k.startswith("_")}

    # 1. calibration
    cal = {}
    for f, cf in CONF_FIELD.items():
        by = C.defaultdict(lambda: [0, 0])
        for i in v1:
            lvl = (v1[i].get("confidence") or {}).get(cf, "unknown")
            by[lvl][1] += 1
            by[lvl][0] += v1[i].get(f) != fin[i].get(f)
        cal[f] = {k: {"changed": a, "n": n, "rate": round(a / n, 3)} for k, (a, n) in by.items()}
    allby = C.defaultdict(lambda: [0, 0])
    for f in cal:
        for k, v in cal[f].items():
            allby[k][0] += v["changed"]; allby[k][1] += v["n"]
    cal["all"] = {k: {"changed": a, "n": n, "rate": round(a / n, 3)} for k, (a, n) in allby.items()}

    # 2. evidence quality: vendor-domain share (vendor = hint domain or the auth/surface doc domain in final)
    def vendor_share(recs):
        tot = vend = 0
        third = C.Counter()
        for i, r in recs.items():
            vd = {dom("https://" + apps[i]["hint"].split(" ")[0]), dom(fin[i].get("evidence", {}).get("surface"))}
            name = apps[i]["app"].lower().split(" ")[0].replace(".", "")
            for k, u in (r.get("evidence") or {}).items():
                if not u:
                    continue
                tot += 1
                d = dom(u)
                if d in vd or name[:5] in d or d == "github.com":
                    vend += 1
                else:
                    third[d] += 1
        return {"total": tot, "vendor": vend, "share": round(vend / tot, 3), "top_third_party": third.most_common(8)}
    evidence = {"v1": vendor_share(v1), "final": vendor_share(fin)}

    # 3. triangulation
    tri, pair = {}, C.Counter()
    for i in fin:
        c, d = cat[i], docs.get(i, {})
        row = {"app": apps[i]["app"],
               "composio_auth": None if not c["in_composio"] or c.get("primary_supported") is None else ("agree" if c["primary_supported"] else "disagree"),
               "docs_auth": {"supported": "agree", "primary_not_on_page": "disagree"}.get(d.get("auth"), None),
               "docs_access": {"supported": "agree", "not_stated": "disagree"}.get(d.get("access"), None),
               "docs_mcp": {"supported": "agree", "not_stated": "disagree"}.get(d.get("mcp"), None),
               "hand": None}
        if i in gt:
            g = gt[i]
            oks = [fin[i].get(k2) in g[k] for k, k2 in [("auth", "auth_primary"), ("access", "access"), ("mcp", "mcp"), ("verdict", "verdict")] if g[k]]
            row["hand"] = "agree" if all(oks) else "disagree"
        od = d.get("oauth_dispute")
        if od:
            row["oauth_dispute"] = {"docs_say_oauth": od.get("oauth_on_vendor_docs"), "evidence": od.get("evidence"), "composio_auth": od.get("composio_auth")}
        for k in ["composio_auth", "docs_auth", "docs_access", "docs_mcp", "hand"]:
            pair[(k, row[k])] += 1
        row["sources_checked"] = sum(row[k] is not None for k in ["composio_auth", "docs_auth", "docs_access", "docs_mcp", "hand"])
        row["sources_agree"] = sum(row[k] == "agree" for k in ["composio_auth", "docs_auth", "docs_access", "docs_mcp", "hand"])
        tri[i] = row
    tri_summary = {k: {"agree": pair[(k, "agree")], "disagree": pair[(k, "disagree")], "not_checked": pair[(k, None)]}
                   for k in ["composio_auth", "docs_auth", "docs_access", "docs_mcp", "hand"]}
    dist = C.Counter(r["sources_checked"] for r in tri.values())
    od = [r for r in tri.values() if "oauth_dispute" in r]
    oauth = {"n": len(od), "agent_right": sum(1 for r in od if r["oauth_dispute"]["docs_say_oauth"]),
             "composio_right": sum(1 for r in od if r["oauth_dispute"]["docs_say_oauth"] is False),
             "apps_agent_right": [r["app"] for r in od if r["oauth_dispute"]["docs_say_oauth"]],
             "apps_composio_right": [r["app"] for r in od if r["oauth_dispute"]["docs_say_oauth"] is False],
             "human_classification": OAUTH_CLASS}

    # 4. priority quadrant
    pts = []
    for i, r in fin.items():
        c = cat[i]
        pts.append({"id": i, "app": r["app"], "group": apps[i]["given_category"], "ease": EASE.get(r["access"], .3),
                    "depth": DEPTH.get(r.get("api_breadth"), .4), "verdict": r["verdict"], "in_composio": c["in_composio"],
                    "mcp_only": c.get("mcp_only", False), "tools": c.get("tools"), "access": r["access"]})
    gaps = sorted([p for p in pts if not p["in_composio"] or p["mcp_only"]], key=lambda p: (-p["ease"], -p["depth"]))
    build_next = [p["app"] for p in gaps if p["ease"] >= .85 and p["verdict"] != "not_buildable"]
    outreach_gaps = [p["app"] for p in gaps if p["ease"] < .5]

    # 5. error map: value changes v1→final by category × field
    em = {g: C.Counter() for g in dict.fromkeys(a["given_category"] for a in apps.values())}
    for i in fin:
        for f in VALUE:
            if v1[i].get(f) != fin[i].get(f):
                em[apps[i]["given_category"]][f] += 1

    # coverage stats from Composio catalog
    inc = [c for c in cat.values() if c["in_composio"]]
    coverage = {"in_composio": len(inc), "native": sum(1 for c in inc if not c.get("mcp_only")), "mcp_only": sum(1 for c in inc if c.get("mcp_only")),
                "with_provider_mcp_toolkit": sum(1 for c in cat.values() if c["provider_mcp_toolkit"]),
                "by_group": {g: sum(1 for i, c in cat.items() if c["in_composio"] and apps[i]["given_category"] == g) for g in em},
                "tools_median": sorted([c["tools"] for c in inc if c["tools"]])[len([c for c in inc if c["tools"]]) // 2],
                "missing": [cat[i]["app"] for i in sorted(cat) if not cat[i]["in_composio"]]}

    out = {"calibration": cal, "evidence": evidence, "triangulation": {"rows": tri, "summary": tri_summary, "sources_checked_dist": dist, "oauth_disputes": oauth},
           "priority": {"points": pts, "build_next": build_next, "outreach_gaps": outreach_gaps}, "error_map": em, "coverage": coverage}
    (ROOT / "data/analysis.json").write_text(json.dumps(out, indent=1, default=dict))
    print("calibration (all fields): ", {k: v["rate"] for k, v in cal["all"].items()}, {k: v["n"] for k, v in cal["all"].items()})
    print("evidence vendor share v1→final:", evidence["v1"]["share"], "→", evidence["final"]["share"], evidence["final"]["top_third_party"][:5])
    print("triangulation:", tri_summary)
    print("sources checked per app:", dict(sorted(dist.items())))
    print("oauth disputes:", oauth)
    print("coverage:", {k: v for k, v in coverage.items() if k != "by_group"})
    print("build next:", build_next); print("outreach gaps:", outreach_gaps)
    print("error map:", {g: dict(c) for g, c in em.items()})


if __name__ == "__main__":
    main()
