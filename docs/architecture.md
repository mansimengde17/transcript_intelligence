# Production architecture

## Decision principle

Use conventional software for operations that require repeatability: parsing, authorization, redaction, lineage, deterministic scoring, and audit logging. Use agent orchestration where the system must gather evidence, resolve ambiguity, combine tools, or request human judgment.

## Runtime flow

```text
Transcript JSON
    |
    v
Ingestion and immutable source hashes
    |
    v
PII redaction and prompt-injection screening
    |
    +------ policy violation ------> Human review queue
    |
    v
Call-type and theme agents
    |
    v
Hybrid retrieval: BM25 + TF-IDF + latent semantic analysis
    |
    v
Risk agent and evidence-linked synthesis
    |
    +------ low confidence/high risk ------> Human review queue
    |
    v
API or MCP tools with RBAC and tamper-evident audit events
```

## Agent roles

| Agent | Responsibility | Tool access | Failure behavior |
|---|---|---|---|
| Policy | Redaction and injection detection | Redactor | Blocks or routes to review |
| Classification | Call type and multi-label themes | Metadata and taxonomy | Low confidence routes to review |
| Retrieval | Grounded evidence collection | Hybrid index | Weak retrieval routes to review |
| Risk | Prioritization from supplied signals | Sentiment and key moments | Score is bounded and auditable |
| Synthesis | Evidence-linked output | Prior agent decisions | Cannot complete without citations |

## State, memory, and replay

SQLite stores every graph checkpoint and human correction. JSONL spans record node latency, routing, and errors. The audit ledger chains each entry to the previous hash so offline verification can expose modification. In production, move checkpoints to Postgres, traces to OpenTelemetry, and immutable audit records to object storage with retention controls.

## RAG design

The prototype splits transcripts into six-utterance evidence chunks. Retrieval combines:

- BM25 for exact product, account, and incident vocabulary.
- TF-IDF cosine similarity for phrase overlap.
- Latent semantic analysis for lower-dimensional topical similarity.

Each result includes the meeting ID, timestamp range, source hash, authorization scope, and a score breakdown. A production version can replace LSA with managed embeddings while retaining the same evidence contract and evaluation suite.

## Scale and failure modes

- Build indexes asynchronously and version them by source manifest hash.
- Cache retrieval results by normalized query and authorization scope.
- Apply concurrency limits, timeouts, retries with jitter, and per-model circuit breakers.
- Keep model fallbacks explicit. Never silently change providers or quality tiers.
- Use budget policies by workflow and tenant. Route low-value bulk processing to smaller models.
- Require idempotency keys for analysis jobs and persist intermediate state before tool calls.
