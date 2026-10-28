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

## How the project works—and why this approach was chosen

Imagine a customer mentions an outage in a support call, engineering discusses the same problem internally, and the issue comes up again during renewal. Reading each meeting separately makes that connection easy to miss. This project organizes those conversations so teams can find recurring problems, inspect the evidence, and decide who should follow up.

The project is a working analysis pipeline and API prototype. It produces spreadsheets, charts, searchable evidence, and meeting reports. The interactive API page lets reviewers try search and analysis; the proposed account timeline and leadership dashboard are future product views.

### 1. Turn meeting records into consistent information

The pipeline reads the supplied meeting files, including participants, transcripts, summaries, topics, sentiment labels, and action items. It creates one consistent analysis row for each meeting.

**Why:** Meetings arrive as several files and contain different kinds of information. A common structure makes comparisons possible and keeps a reference back to the original meeting.

**Benefit:** Reviewers can compare all 100 meetings without opening every source file individually.

### 2. Group conversations into understandable categories

Participant email domains and meeting titles help identify internal, external, and support calls. A defined list of themes groups related language into subjects such as reliability, compliance, and identity. Clear title intent receives extra weight. Meetings may match several themes, while one primary theme supports summary reporting.

**Why:** A consistent set of categories is easier to explain and check than generating a new label for every conversation.

**Benefit:** Support, product, and engineering can discuss the same problem using shared categories, while reviewers can inspect the evidence behind a label.

### 3. Identify where attention may be needed

The project preserves supplied sentiment scores and sentence-level sentiment labels. It combines low sentiment with explicit concerns, technical issues, feature gaps, and churn signals to create a bounded risk score. Praise and positive turns in the conversation reduce that score.

**Why:** An average sentiment score alone can hide a serious problem within an otherwise positive relationship.

**Benefit:** Customer success teams get a starting point for account review. The score is a priority indicator, not a probability that a customer will leave, and should be checked against the underlying conversation.

### 4. Retrieve evidence using both words and meaning

Search combines exact-word matching with statistical methods that recognize related language. Technically, these are BM25, TF-IDF, and latent semantic analysis. Results retain source references and score details.

**Why:** A user searching for an outage may need evidence described using words such as failure or loss of visibility. Combining methods helps cover different ways of expressing a concern.

**Benefit:** Reviewers can move from a broad finding to relevant transcript passages and verify the basis for a decision.

### 5. Coordinate analysis with a controlled workflow

The agent workflow separates policy checks, classification, evidence retrieval, risk assessment, and report synthesis. It records decisions and intermediate progress, and can route cases for human review when configured conditions are met.

**Why:** Separating responsibilities makes failures easier to locate and decisions easier to inspect. Parsing, permissions, redaction, and scoring stay in repeatable code. The default demonstration uses deterministic local behavior; optional adapters support model-backed workflows.

**Benefit:** The prototype is inexpensive to reproduce, works without a paid model API, and provides a controlled foundation for adding more flexible reasoning where it proves useful.

### 6. Check quality and preserve accountability

Automated checks test classification, retrieval, citations, sensitive-information handling, access restrictions, risk bounds, and audit integrity. Source hashes help detect changes, while linked audit events help reveal changes to the recorded history.

**Why:** A convincing demonstration alone does not establish that a system behaves consistently or respects access rules.

**Benefit:** Changes can be checked for regressions, and reviewers have a record to investigate. These prototype controls still need broader validation before production use.

## How different teams can use the results

| Team | What they can learn | Practical next step |
| --- | --- | --- |
| Customer success | Accounts with difficult conversations or repeated concerns | Review the evidence and coordinate follow-up with the account owner |
| Support | Common problems across customer calls | Identify recurring escalations and share examples with engineering |
| Engineering | Reliability issues discussed across teams | Compare transcript evidence with incident records and prioritize investigation |
| Product | Repeated feature gaps and adoption concerns | Review customer examples when planning the backlog |
| Leadership | Themes, sentiment differences, and areas needing attention | Assign owners and ask for evidence-backed updates |

The pipeline also extracts 397 action items. These provide a foundation for commitment tracking; due dates and completion tracking still need to be added.

## A guide to the folders and files

| Folder or file | What it contains | How it is used |
| --- | --- | --- |
| `data/raw/` | The supplied meeting records, organized by meeting | Input to the analysis; preserves the original evidence |
| `src/pipeline.py` | The main analytics process | Reads meetings, assigns categories, summarizes sentiment and risk, and writes tables and charts |
| `src/ti/` | Search, workflow, access controls, API, model adapters, and supporting components | Powers evidence search and meeting analysis |
| `analysis/` | Generated meeting tables, theme summaries, account priorities, action items, and written findings | The main place for a business reviewer to explore results |
| `analysis/charts/` | Images of theme frequency, sentiment, trends, and account risk | Visual explanation of the findings |
| `analysis/advanced/` | Evaluation results, example workflow reports, and additional analysis | Shows how the system performed and examples of its output |
| `notebooks/` | Guided analysis and verification notebooks | Lets a technical reviewer explore the work step by step |
| `evals/` | Quality checks and pass/fail thresholds | Measures whether changes meet the prototype's quality requirements |
| `tests/` | Automated component and integration tests | Checks expected behavior and failure cases |
| `docs/` | Architecture, governance, and model documentation | Explains design choices, controls, and limitations |
| `deploy/` | Kubernetes deployment configuration | A starting point for running the service in a managed environment |
| `.github/workflows/` | Automated GitHub quality-check configuration | Defines checks to run when repository changes trigger the workflow |
| `runtime/` | Locally generated checkpoints, traces, and audit records | Records workflow execution; excluded from GitHub |
| `requirements.txt` | Core Python dependencies | Installs the software needed for the default local demonstration |
| `requirements-agentic.txt` | Optional integration dependencies | Adds support for model and agent-framework integrations |
| `Makefile` | Short commands for building, evaluating, testing, and serving | Provides repeatable ways to run the project |
| `Dockerfile`, `docker-compose.yml` | Container setup | Provides another way to package and run the application |
| `Transcript_Intelligence_Applied_AI_Review.pptx` | Findings, recommendations, and technical appendix | Presentation for stakeholders and interview reviewers |

## Where a nontechnical reviewer should start

1. Open the PowerPoint for the business findings and recommendations.
2. Read `analysis/insights.md` for the written analysis.
3. View `analysis/charts/` for the main comparisons.
4. Open `analysis/account_risk.csv` to explore account priorities and `analysis/action_items.csv` to inspect extracted commitments.
5. Ask for a demonstration of `/docs` to see evidence search and meeting analysis in action. Use the Run it and API instructions in this README to start the local demonstration.

CSV files can be opened in Excel or another spreadsheet application. Scores and summaries should be interpreted alongside the original meeting evidence.

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
