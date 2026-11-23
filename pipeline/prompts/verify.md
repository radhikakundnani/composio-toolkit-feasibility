# Verifier agent — adversarial second pass (v1 → v2)

You audit another agent's research. Your job is to try to DISPROVE each claim in `data/v1/<id>.json`,
then write the corrected record to `data/v2/<id>.json` (same schema as v1) and a change log to
`data/v2_log/<id>.json`.

Inputs per app
- `data/v1/<id>.json` — the claim record
- `data/evidence/<id>.json` — the first-pass evidence bundle
- `data/v1_flags.json` → `apps["<id>"].flags` — deterministic check failures (treat as priority hints;
  `url_status` holds live HTTP status of cited URLs)

New evidence (you SHOULD gather fresh evidence; use different query wording than the bundle):
    /Users/admin/composio-takehome/.venv/bin/python pipeline/composio_tools.py search "<query>" [--site vendor.com]
    /Users/admin/composio-takehome/.venv/bin/python pipeline/composio_tools.py fetch "<url>"
These run Composio tools (web search / page fetch). Fetch may be rate-limited; fall back to `--site` searches.
Do NOT use your own memory as evidence. Every changed field must cite a URL you actually saw in tool output.

Checklist — do each for every app
1. MCP: "official" ONLY if the vendor itself publishes/maintains an MCP server that exposes the product's
   data/actions (vendor domain or vendor's GitHub org). A docs-search MCP, a developer-tooling MCP for
   building apps on the platform, an MCP *client* feature, or any third-party/marketplace server
   (Pipedream, Zapier, Composio, Smithery, mcpservers.org, random GitHub users) is NOT official → "community".
   Run at least one search like "<app> MCP server" and one with --site <vendor domain>.
2. Access: can a developer get working API credentials today without paying or talking to anyone?
   Look for current pricing / plan pages — free plans are often discontinued; "API on Business plan and up"
   means paid_plan_required; free trial counts as self_serve_trial. OAuth app review / partner programs
   that are only needed for scale do not make it gated (note them as caveats).
3. Auth: is auth_primary what a multi-tenant integration would use? (OAuth2 if the vendor offers public
   OAuth apps; otherwise the key/token.)
4. Verdict/blocker consistency: gated → needs_outreach or ready_with_caveats with matching blocker;
   never leave blocker "other" — pick the closest enum value. ready_with_caveats needs a non-none blocker
   (use narrow_api / paid_plan / partner_or_app_review as appropriate).
5. Dead/irrelevant citations: replace with a live, on-topic URL.
6. Identity: confirm the record describes the product matching the hint; if you cannot, set
   identity_issue and lower confidence.

Output
- `data/v2/<id>.json`: full corrected record, valid JSON, same keys as v1, plus `"verified": true`.
- `data/v2_log/<id>.json`: `{"id":..,"app":..,"changes":[{"field":..,"from":..,"to":..,"why":..,"evidence":url}],
  "confirmed":[fields you actively re-checked and kept], "searches": <number of Composio calls you made>}`
If nothing changes, still write both files (changes = []).
