# AI governance and threat model

## Controls implemented

- Role-based permissions for search, analysis, raw evidence, feedback, and administration.
- Optional account scopes for row-level customer isolation.
- Redaction for email addresses, phone numbers, IPv4 addresses, and common API-key patterns.
- Prompt-injection screening before agent reasoning or tool use.
- SHA-256 lineage for source objects, transforms, and outputs.
- Hash-chained append-only audit events.
- Human review for high-risk, low-confidence, policy-flagged, or failed runs.
- Evidence IDs on every synthesized report.

## Threats considered

| Threat | Control | Residual risk |
|---|---|---|
| Cross-account data exposure | RBAC plus account scopes before retrieval | Incorrect identity-to-scope mapping |
| Prompt injection in transcripts | Treat transcript text as data, scan patterns, restrict tools | Novel or obfuscated injection strings |
| Hallucinated conclusions | Evidence-required synthesis and citation coverage gate | Evidence may still be misinterpreted |
| Sensitive data in logs | Redaction before retrieval and output; metadata-only traces | Names and uncommon identifiers need NER |
| Audit modification | Hash chain and source hashes | Host administrator can delete the entire log |
| Model or taxonomy drift | Regression evaluations and human feedback store | Evaluation set can become stale |

## Production additions

Use enterprise identity through OAuth2/OIDC, short-lived workload credentials, encryption with managed keys, centralized secrets, tenant-aware Postgres policies, private networking, and retention schedules. Add a trained entity recognizer for sensitive data and send immutable audit records to write-once storage.
