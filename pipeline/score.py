"""Score a pipeline version against the hand-verified ground truth.

    python pipeline/score.py v1
    python pipeline/score.py v2 --json   # machine-readable, used by the report

Fields scored per app: auth (agent's primary auth is an accepted method), access,
mcp (skipped where ground truth is null), verdict.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIELDS = ["auth", "access", "mcp", "verdict"]


def score(version: str) -> dict:
    gt = {k: v for k, v in json.loads((ROOT / "data/ground_truth.json").read_text()).items() if not k.startswith("_")}
    rows, hits, totals = [], {f: 0 for f in FIELDS}, {f: 0 for f in FIELDS}
    for k, t in gt.items():
        rec = json.loads((ROOT / f"data/{version}/{int(k):03d}.json").read_text())
        got = {"auth": rec.get("auth_primary"), "access": rec.get("access"), "mcp": rec.get("mcp"), "verdict": rec.get("verdict")}
        res = {}
        for f in FIELDS:
            if t[f] is None:
                res[f] = None
                continue
            ok = got[f] in t[f]
            res[f] = ok
            totals[f] += 1
            hits[f] += ok
        rows.append({"id": int(k), "app": t["app"], "how": t["how"], "got": got, "truth": {f: t[f] for f in FIELDS}, "ok": res})
    n_hit, n_tot = sum(hits.values()), sum(totals.values())
    return {"version": version, "overall": round(100 * n_hit / n_tot, 1), "hits": n_hit, "total": n_tot,
            "by_field": {f: f"{hits[f]}/{totals[f]}" for f in FIELDS}, "rows": rows}


if __name__ == "__main__":
    s = score(sys.argv[1])
    if "--json" in sys.argv:
        print(json.dumps(s, indent=1))
    else:
        print(f"{s['version']}: {s['overall']}%  ({s['hits']}/{s['total']})  {s['by_field']}")
        for r in s["rows"]:
            miss = [f"{f}: got {r['got'][f]!r} want {r['truth'][f]}" for f in FIELDS if r["ok"][f] is False]
            if miss:
                print(f"  ✗ {r['id']:3d} {r['app']:<16} " + " | ".join(miss))
