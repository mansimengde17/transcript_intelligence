# Model and system card

## Intended use

Prioritize transcript evidence for support, customer success, product, and engineering leaders. The system classifies conversations, retrieves related evidence, summarizes supplied signals, and routes uncertain or sensitive cases to human review.

## Out-of-scope use

- Automated employment, credit, insurance, or legal decisions.
- Automatic customer-renewal actions without human review.
- Security-incident conclusions without source-system validation.
- Surveillance or employee performance scoring.

## Components

The default mode uses deterministic rules, scikit-learn retrieval, and source-provided sentiment. Optional adapters may use LLMs for ambiguous classification and synthesis. Provider, prompt, model, token counts, and cost must enter the trace record when enabled.

## Evaluation gates

- Call-type and theme accuracy on a reviewed golden set.
- Retrieval recall at three for evidence queries.
- Citation coverage for synthesized output.
- PII leakage, prompt-injection, RBAC, risk-bound, and audit-integrity tests.
- Cost and latency regression thresholds.

## Limitations

The sample data appears synthetic and spans roughly three months. Source summaries and sentiment labels may contain upstream model errors. The current risk score prioritizes review; it does not estimate churn probability. LSA improves topical matching but does not match modern embedding quality.
