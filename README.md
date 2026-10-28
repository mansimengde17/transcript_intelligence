# Transcript Intelligence

A production-minded Applied AI prototype for 100 enterprise transcripts. It combines deterministic analytics with a gated agent graph, hybrid retrieval, automated evaluations, governance controls, MCP tools, an authenticated API, observability, and deployment assets.

## Key findings

- 100 meetings: 39 external, 30 internal, and 31 support calls.
- Support sentiment averages 2.80/5, compared with 3.90/5 for external calls.
- Reliability and incidents is the primary theme for 24 meetings.
- The pipeline extracts 397 action items.
- Account risk scores prioritize evidence review; they are not churn probabilities.

## What is included

- `src/pipeline.py`: reproducible baseline analytics pipeline
- `src/ti/advanced_pipeline.py`: retrieval index, unsupervised topic validation, and sample agent runs
- `src/ti/agents.py`: durable agent graph with checkpoints and human-review routing
- `src/ti/langgraph_adapter.py`: optional LangGraph compilation of the same tested nodes
- `src/ti/model_gateway.py`: deterministic fallback and budgeted OpenAI Responses adapter
- `src/ti/retrieval.py`: BM25 + TF-IDF + latent semantic retrieval
- `src/ti/governance.py`: RBAC, PII redaction, lineage, injection detection, and audit integrity
- `src/ti/api.py`: FastAPI service with API-key authentication and account scopes
- `src/ti/mcp_server.py`: custom MCP server exposing governed tools
- `evals/`: quality, safety, retrieval, citation, RBAC, cost, and regression gates
- `docs/`: architecture, governance, threat model, and system card
- `deploy/`, `Dockerfile`: container and Kubernetes deployment assets
- `tests/`: unit and integration tests
- `notebooks/transcript_intelligence_analysis.ipynb`: reviewer-friendly walkthrough
- `analysis/`: meeting-level output, aggregate summaries, account risk, action items, findings, and charts
- `data/raw/`: the original JSON dataset from the supplied archive
- `Transcript_Intelligence_Applied_AI_Review.pptx`: leadership presentation with technical appendix

## Run it

```bash
git clone https://github.com/mansimengde17/transcript_intelligence.git
cd transcript_intelligence
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
make all
```

The default path uses no paid APIs or network services. It runs the analytics pipeline, builds the hybrid retrieval index, exercises the agent graph, evaluates the system, and runs the test suite.

## Agent and MCP mode

Install optional agent dependencies when you want LangGraph, the official MCP Python SDK, OpenAI adapters, or OpenTelemetry exporters:

```bash
pip install -r requirements-agentic.txt
make mcp
```

The prototype’s framework-neutral graph keeps core behavior testable offline. Production adapters can wrap the same nodes in LangGraph for durable execution and use OpenTelemetry or an evaluation platform such as Langfuse, LangSmith, or Braintrust.

## API

```bash
export TI_API_KEYS='local-admin=admin:'
make serve
```

Leave the server running. Open [the interactive API demo](http://localhost:8080/docs), or run this in a second terminal:

```bash
curl -H 'X-API-Key: local-admin' 'http://localhost:8080/v1/search?q=threat+visibility&top_k=3'
```

API keys are a local demonstration mechanism. The production design uses OAuth2/OIDC, workload identity, short-lived credentials, and database-enforced tenant scopes.

## Approach

The solution uses a hybrid, explainable method:

1. **Call type** comes from participant email domains and title patterns. All-internal domains become internal calls. External participants with support or escalation patterns become support calls. Other customer conversations become external calls.
2. **Themes** come from a curated multi-label keyword taxonomy applied to titles, summaries, source topics, and key moments. The highest-evidence theme becomes the primary theme; the next becomes secondary.
3. **Sentiment** aggregates the supplied sentence-level labels and meeting-level 1-5 score. The pipeline preserves both because a single average can hide a difficult section inside an otherwise productive meeting.
4. **Risk** combines low meeting sentiment with explicit churn signals, concerns, technical issues, and feature gaps. Positive pivots and praise reduce the score. This score is a prioritization heuristic, not a churn probability.
5. **Retrieval** combines BM25, sparse TF-IDF, and 64-dimensional latent semantic analysis over evidence-preserving transcript chunks.
6. **Agent orchestration** separates policy, classification, retrieval, risk, and synthesis responsibilities. Low confidence, high risk, policy signals, missing evidence, or node failures route to human review.
7. **Governance** applies redaction, account-scoped RBAC, transform lineage, evidence citations, durable checkpoints, and a tamper-evident audit ledger.

## Why agents are selective

Parsing, permissions, redaction, scoring, and audit logging remain deterministic because agents add cost and variance without improving those tasks. Agents add value when the workflow needs evidence gathering, ambiguity resolution, tool selection, synthesis, or a human escalation. The evaluation suite enforces this boundary.

## Evaluation gates

`make eval` produces `analysis/advanced/eval_report.json` and fails when a regression breaches a configured threshold. The suite currently covers:

- Call-type and theme classification accuracy.
- Retrieval recall at three on account-specific evidence queries.
- Evidence citation coverage.
- PII redaction and prompt-injection detection.
- Negative RBAC tests and account isolation.
- Bounded risk scores and hash-chain integrity.
- Deterministic inference-cost regression.

## Validation and limitations

The dataset covers 100 meetings from February 3 through April 28, 2026. The source appears synthetic and already contains generated summaries, topics, and sentiment labels. This project treats those fields as supplied model output and builds an auditable decision layer on top. A production implementation should replace derived golden labels with domain-expert annotations, calibrate risk against actual outcomes, evaluate any LLM provider separately, monitor drift, and add action-item due-date and completion tracking.

## Live demonstration

1. Run `make all` to generate outputs and run checks.
2. Open the included PowerPoint for findings and architecture.
3. Start the API using the commands above and open `/docs`.
4. Use **GET /v1/search**, with `q=API outage`, `top_k=3`, and `X-API-Key=local-admin`.
5. Use **POST /v1/analyze** with the same key and this request:

```json
{"meeting_id":"01KQDD5172176D02DB51360A"}
```

Inspect the actual **Server response** for the workflow status, report, decisions, and policy flags. The lower Responses section contains documentation examples.

The base URL `/` has no page; use `/docs`. The health endpoint is `/healthz`. An invalid API key returns HTTP 401.

## Outputs and checks

| Output | Location |
| --- | --- |
| Meeting classifications and evidence | `analysis/meeting_analysis.csv` |
| Themes and sentiment summaries | `analysis/theme_summary.csv`, `analysis/call_type_summary.csv` |
| Account priorities | `analysis/account_risk.csv` |
| Extracted commitments | `analysis/action_items.csv` |
| Charts | `analysis/charts/` |
| Evaluation report | `analysis/advanced/eval_report.json` |
| Example agent output | `analysis/advanced/sample_agent_reports.json` |

Run individual stages with `make pipeline`, `make advanced`, `make eval`, and `make test`. Current prototype evaluation sizes are eight classification cases and four retrieval queries; perfect scores on these sets do not establish production accuracy.

Local environments, credentials, runtime databases, and command history are excluded from version control.
