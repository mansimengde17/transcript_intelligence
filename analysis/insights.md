# Transcript Intelligence findings

## Executive findings

- The dataset contains **100 meetings** and **4,313 utterances**. The call mix is external 39, internal 30, support 31.
- **Support calls carry the weakest sentiment** at 2.80/5, compared with 3.90/5 for external calls. Their negative utterance share is 27.1%.
- **Reliability & incidents is the largest theme** with 24 meetings. **Integrations & APIs has the highest average risk** among themes with at least three meetings (6.87/10).
- **16 customer accounts reached a risk score of 6 or higher**. The highest-priority account is trailheadmkt.com with 2 churn signal(s) and a maximum risk score of 10.0/10.
- Internal calls contain 10 meetings below 3/5 sentiment. This gives leaders a leading indicator of delivery pressure before it appears in customer conversations.

## Recommended product views

1. **Account risk timeline.** Combine sentiment, churn signals, recurring technical issues, and unresolved feature gaps by customer. Customer success leaders can triage accounts before renewal discussions.
2. **Incident propagation map.** Link internal incident calls to support escalations and later renewal concerns by theme and date. Engineering and support leaders can see how operational failures spread into commercial risk.
3. **Commitment tracker.** Extract action owners and due-date language, then flag repeated or overdue commitments. Product and engineering leaders can distinguish recurring discussion from completed follow-through.
4. **Voice-of-customer backlog.** Rank feature gaps by account risk, frequency, and affected segment. Product managers can prioritize requests with both product and revenue context.

## Action ownership

The source summaries contain **397 action items**. The five most frequent named owners are Maria Santos (31), David Kim (24), Sarah Chen (23), Elena Vasquez (20), Kevin O'Brien (19). This concentration can identify overloaded coordinators, but due dates and completion status would be needed before treating it as a workload measure.

## Method and limitations

The pipeline uses participant domains and title patterns for call type, a curated keyword taxonomy for themes, and the supplied sentence-level and meeting-level sentiment labels. This is easy to audit and works offline. It does not claim causal relationships. The source data appears synthetic and covers only about three months, so trends should be treated as directional. A production version should add human-reviewed evaluation sets, multi-label model calibration, due-date extraction, and monitoring for taxonomy drift.
