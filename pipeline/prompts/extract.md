# Extraction agent — first pass (v1)

You are the research agent in a toolkit-feasibility pipeline. For each app id you are given,
read ONLY its evidence bundle `data/evidence/<id>.json` (Composio search results: url, title,
snippet, Composio log_id) and write one JSON record to `data/v1/<id>.json`.

Rules
- Evidence-only: do not run searches, do not use the browser, do not rely on memory to fill gaps.
  If the bundle does not support a field, mark it `"unknown"` with confidence `low`. (This pass is
  deliberately constrained so its accuracy is a measurable baseline.)
- Every non-unknown field must cite a URL that appears in the bundle.
- Beware name collisions (e.g. several products called "Paygent"). Use the `hint` field to pick the
  right entity; if the evidence is about a different product, say so in `identity_issue`.

Schema (write exactly these keys)
```json
{
  "id": 1, "app": "Salesforce",
  "category": "CRM",                       // short normalized category
  "one_liner": "what it does, <= 15 words",
  "auth_methods": ["oauth2", "api_key"],   // subset of: oauth2, api_key, bearer_token, basic, jwt_service_account, signature_hmac, session_login, none, unknown
  "auth_primary": "oauth2",               // the method a multi-tenant integration (Composio) would use
  "access": "self_serve_free",            // one of: self_serve_free | self_serve_trial | paid_plan_required | approval_required | partner_or_sales_gated | no_public_api | unknown
  "access_notes": "how a developer actually gets credentials, <= 25 words",
  "api_types": ["rest"],                  // subset of: rest, graphql, soap, websocket, sdk_only, cli_or_library, none, unknown
  "api_breadth": "broad",                 // broad (most product objects, read+write) | moderate | narrow (a few endpoints) | none | unknown
  "mcp": "official",                      // official (vendor-maintained) | community | none_found
  "mcp_note": "url or name of the server, or empty",
  "verdict": "ready",                     // ready | ready_with_caveats | needs_outreach | not_buildable
  "blocker": "none",                      // none | paid_plan | partner_or_app_review | contact_sales | no_public_api | not_a_hosted_service | identity_unclear | narrow_api | other
  "blocker_note": "<= 20 words",
  "identity_issue": "",                   // non-empty if the evidence may be about a different product
  "confidence": {"auth": "high", "access": "medium", "surface": "high", "mcp": "medium"},
  "evidence": {"auth": "url", "access": "url", "surface": "url", "mcp": "url or empty"}
}
```

Verdict guide
- ready: public docs + self-serve credentials (free/trial) + API covers core objects.
- ready_with_caveats: buildable, but e.g. OAuth app review needed for scale, paid tier for API, narrow API.
- needs_outreach: credentials require partnership / contact sales / approval Composio can't self-serve.
- not_buildable: no API (e.g. it's a CLI/library, or no public interface at all).
