"""Stage 1 — evidence gathering (deterministic, no LLM).

For each app, run a fixed battery of research queries through Composio
(KEENABLE_SEARCH_WEB_PUBLIC) and save an evidence bundle to data/evidence/<id>.json.
The bundle is the ONLY input the first-pass extraction agent is allowed to see,
so every answer is traceable to a URL + Composio log_id.

    python pipeline/gather.py            # all 100
    python pipeline/gather.py 1 15 99    # specific ids
"""
from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from composio_tools import search  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
EVID = ROOT / "data" / "evidence"
EVID.mkdir(parents=True, exist_ok=True)

QUERIES = {
    "auth":    "{app} API authentication OAuth API key access token developer docs {hint}",
    "access":  "{app} {hint} API access requirements developer account pricing plan free trial partner program approval",
    "surface": "{app} API reference REST GraphQL endpoints documentation {hint}",
    "mcp":     "{app} {hint} MCP server Model Context Protocol official",
}


def gather(app: dict) -> dict:
    out = {**app, "queries": {}}
    for key, tmpl in QUERIES.items():
        hint = app["hint"].replace("(", "").replace(")", "")
        q = tmpl.format(app=app["app"], hint=hint)
        out["queries"][key] = search(q, max_results=5)
    out["n_results"] = sum(len(v["results"]) for v in out["queries"].values())
    out["failed_queries"] = [k for k, v in out["queries"].items() if not v["ok"]]
    (EVID / f"{app['id']:03d}.json").write_text(json.dumps(out, indent=1))
    return out


def main(ids: list[int]):
    apps = json.loads((ROOT / "data" / "apps.json").read_text())
    if ids:
        apps = [a for a in apps if a["id"] in ids]
    with ThreadPoolExecutor(max_workers=6) as ex:
        for r in ex.map(gather, apps):
            flag = f" FAILED={r['failed_queries']}" if r["failed_queries"] else ""
            print(f"{r['id']:3d} {r['app']:<28} results={r['n_results']}{flag}", flush=True)


if __name__ == "__main__":
    main([int(x) for x in sys.argv[1:]])
