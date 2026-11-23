"""Stage 5 — assemble everything the case study shows into site/results.json.

    python pipeline/report.py

Inputs: data/apps.json, data/v1, data/v2, data/v2_log, data/v1_flags.json, data/v2_flags.json,
        data/ground_truth.json, data/sample.json.
Output: site/results.json (also consumed by agents — one self-describing file).
"""
import collections as C
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
from score import score  # noqa: E402

GATED = {"paid_plan_required", "approval_required", "partner_or_sales_gated"}


def load_dir(d):
    return {int(p.stem): json.loads(p.read_text()) for p in sorted((ROOT / "data" / d).glob("*.json"))}


def main():
    apps = {a["id"]: a for a in json.loads((ROOT / "data/apps.json").read_text())}
    v1, v2, logs = load_dir("v1"), load_dir("v2"), load_dir("v2_log")
    # final = v2 + human adjudications (browser-settled disputes), written to data/final for scoring
    adj = {int(k): v for k, v in json.loads((ROOT / "data/adjudications.json").read_text()).items() if not k.startswith("_")}
    final = {}
    (ROOT / "data/final").mkdir(exist_ok=True)
    for i, r in ({**v1, **v2}).items():
        r = json.loads(json.dumps(r))
        if i in adj:
            r.update(adj[i].get("set", {}))
            r.setdefault("evidence", {}).update(adj[i].get("evidence", {}))
            r["adjudication"] = adj[i]["verdict_on_dispute"]
        final[i] = r
        (ROOT / f"data/final/{i:03d}.json").write_text(json.dumps(r, indent=1))
    flags1 = json.loads((ROOT / "data/v1_flags.json").read_text())["apps"]
    f2p = ROOT / "data/v2_flags.json"
    flags2 = json.loads(f2p.read_text())["apps"] if f2p.exists() else {}

    rows = []
    for i in sorted(final):
        r, a = final[i], apps[i]
        rows.append({**{k: r.get(k) for k in ["id", "app", "category", "one_liner", "auth_methods", "auth_primary",
                                                "access", "access_notes", "api_types", "api_breadth", "mcp", "mcp_note",
                                                "verdict", "blocker", "blocker_note", "identity_issue", "confidence", "evidence"]},
                     "group": a["given_category"], "hint": a["hint"],
                     "changes": logs.get(i, {}).get("changes", []),
                     "flags_v1": flags1.get(str(i), {}).get("flags", []),
                     "flags_v2": flags2.get(str(i), {}).get("flags", []),
                     "adjudication": r.get("adjudication", "")})

    groups = list(dict.fromkeys(a["given_category"] for a in apps.values()))
    matrix = {g: C.Counter(r["verdict"] for r in rows if r["group"] == g) for g in groups}
    access_by_group = {g: C.Counter(r["access"] for r in rows if r["group"] == g) for g in groups}
    changes = [dict(c, id=i, app=final[i]["app"]) for i, l in logs.items() for c in l.get("changes", [])]
    field_changes = C.Counter(c["field"] for c in changes)

    out = {
        "_about": "Composio take-home: toolkit-feasibility research on 100 apps. rows = final verified records (v2). "
                  "accuracy = per-field scoring vs hand-verified ground truth on a seeded 20-app sample.",
        "rows": rows,
        "summary": {
            "verdict": C.Counter(r["verdict"] for r in rows),
            "access": C.Counter(r["access"] for r in rows),
            "auth_primary": C.Counter(r["auth_primary"] for r in rows),
            "auth_any": C.Counter(m for r in rows for m in (r["auth_methods"] or [])),
            "blocker": C.Counter(r["blocker"] for r in rows if r["blocker"] != "none"),
            "mcp": C.Counter(r["mcp"] for r in rows),
            "api_types": C.Counter(t for r in rows for t in (r["api_types"] or [])),
            "verdict_by_group": matrix,
            "access_by_group": access_by_group,
            "v1_verdict": C.Counter(r["verdict"] for r in v1.values()),
            "v1_mcp": C.Counter(r["mcp"] for r in v1.values()),
            "v1_access": C.Counter(r["access"] for r in v1.values()),
        },
        "verification": {
            "sample": json.loads((ROOT / "data/sample.json").read_text()),
            "v1": score("v1"),
            "v2": score("v2") if len(v2) == 100 else None,
            "final": score("final"),
            "adjudications": {k: v for k, v in adj.items()},
            "flags_v1": sum(1 for v in flags1.values() if v["flags"]),
            "flags_v2": sum(1 for v in flags2.values() if v["flags"]) if flags2 else None,
            "flag_kinds_v1": C.Counter(f.split(":")[0] for v in flags1.values() for f in v["flags"]),
            "flag_kinds_v2": C.Counter(f.split(":")[0] for v in flags2.values() for f in v["flags"]) if flags2 else None,
            "n_changes": len(changes), "apps_changed": len({c["id"] for c in changes}),
            "changes_by_field": field_changes, "changes": changes,
            "gt_corrections": {k: v["gt_correction"] for k, v in json.loads((ROOT / "data/ground_truth.json").read_text()).items()
                               if isinstance(v, dict) and v.get("gt_correction")},
        },
    }
    for extra in ["analysis", "catalog_match", "doccheck"]:
        f = ROOT / f"data/{extra}.json"
        if f.exists():
            out[extra] = json.loads(f.read_text())
    ins = ROOT / "data/insights.json"  # human-written narrative: patterns, where humans were needed
    out["insights"] = json.loads(ins.read_text()) if ins.exists() else {}
    (ROOT / "site").mkdir(exist_ok=True)
    blob = json.dumps(out, indent=1, default=dict)
    (ROOT / "site/results.json").write_text(blob)
    html = (ROOT / "site/template.html").read_text()
    (ROOT / "site/index.html").write_text(html.replace("/*__DATA__*/null", blob.replace("</", "<\\/")))
    print("rows", len(rows), "| v2 complete:", len(v2) == 100, "| changes:", len(changes), dict(field_changes))
    for k in ["verdict", "access", "auth_primary", "mcp", "blocker"]:
        print(k, dict(out["summary"][k]))


if __name__ == "__main__":
    main()
