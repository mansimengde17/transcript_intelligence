#!/usr/bin/env python3
"""Transcript Intelligence pipeline.

The pipeline deliberately uses an explainable hybrid approach:
1. deterministic metadata rules classify call type;
2. curated keyword dictionaries map noisy source topics and text to a stable taxonomy;
3. source sentence-level and meeting-level sentiment are aggregated without inventing labels;
4. risk and execution signals are derived from source key moments and action items.

The code has no network or LLM dependency, so reviewers can reproduce every result.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


INTERNAL_DOMAIN = "aegiscloud.com"

THEME_RULES: dict[str, tuple[str, ...]] = {
    "Reliability & incidents": (
        "outage", "incident", "reliability", "latency", "downtime", "failure",
        "degradation", "data gap", "alerts not firing", "dashboard down", "sla breach",
        "root cause", "post-mortem", "postmortem", "circuit breaker", "scalability",
    ),
    "Compliance & reporting": (
        "compliance", "soc 2", "soc2", "hipaa", "pci dss", "iso 27001", "audit",
        "report", "template", "regulatory", "evidence collection", "multi-framework",
    ),
    "Identity & access": (
        "identity", "sso", "saml", "scim", "ldap", "mfa", "totp", "provisioning",
        "group policy", "login", "access management", "user lockout",
    ),
    "Commercial & renewal": (
        "renewal", "contract", "churn", "retention", "annual review", "business review",
        "account review", "expansion", "upsell", "pricing", "discount", "commercial",
    ),
    "Backup & recovery": (
        "backup", "restore", "recovery", "rpo", "rto", "backup window", "cloudprime",
    ),
    "Product adoption & launch": (
        "adoption", "launch", "early access", "demo", "deployment", "onboarding",
        "preview", "kickoff", "upgrade", "ga", "product update",
    ),
    "Integrations & APIs": (
        "integration", "connector", "api", "siem", "logvault", "webhook", "timeout",
    ),
    "Billing & pricing": (
        "billing", "invoice", "overage", "charge", "license", "pricing", "dispute",
    ),
    "Competitive intelligence": (
        "competitive", "competitor", "vendor comparison", "win/loss", "displacement",
    ),
    "Product planning & delivery": (
        "roadmap", "sprint", "planning", "standup", "design review", "feature request",
        "feature gap", "technical debt", "launch readiness", "quarterly planning",
    ),
}

SUPPORT_HINTS = (
    "support case", "urgent:", "escalation:", "complete loss", "dashboard down",
    "alerts not firing", "invoice discrepancy", "failures", "issue", "bug",
)

RISK_MOMENT_WEIGHTS = {
    "churn_signal": 3.0,
    "concern": 1.2,
    "technical_issue": 1.0,
    "feature_gap": 0.8,
    "pricing_offer": -0.2,
    "positive_pivot": -0.6,
    "praise": -0.8,
    "action_item": 0.0,
}


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def external_domains(emails: Iterable[str]) -> list[str]:
    domains = []
    for email in emails:
        if "@" not in email:
            continue
        domain = email.rsplit("@", 1)[1].lower()
        if domain != INTERNAL_DOMAIN:
            domains.append(domain)
    return sorted(set(domains))


def classify_call_type(title: str, emails: list[str]) -> tuple[str, str]:
    """Return call type and a human-readable rule explanation."""
    title_l = title.lower()
    has_external = bool(external_domains(emails))
    if not has_external:
        return "Internal", "All participant email domains are internal"
    if any(hint in title_l for hint in SUPPORT_HINTS):
        return "Support", "External participant plus support/escalation title pattern"
    return "External", "External participant without a support/escalation title pattern"


def normalize_text(*parts: Any) -> str:
    flattened: list[str] = []
    for part in parts:
        if isinstance(part, list):
            flattened.extend(str(value) for value in part)
        elif part is not None:
            flattened.append(str(part))
    return re.sub(r"\s+", " ", " ".join(flattened)).lower()


def score_themes(text: str) -> list[tuple[str, int, list[str]]]:
    scored = []
    for theme, keywords in THEME_RULES.items():
        matched = sorted({keyword for keyword in keywords if keyword in text})
        if matched:
            # Phrase matches are transparent; multiple independent signals raise confidence.
            scored.append((theme, len(matched), matched))
    return sorted(scored, key=lambda item: (-item[1], item[0]))


def score_themes_weighted(title: str, summary: str, topics: list[str], moments: list[dict[str, Any]]) -> list[tuple[str, float, list[str]]]:
    """Score theme evidence by field reliability.

    Titles carry the strongest intent signal, source topics carry the next strongest signal,
    and free-form summaries/key moments provide recall without dominating clear meeting intent.
    """
    fields = [
        (title.lower(), 8.0),
        (" ".join(topics).lower(), 2.0),
        (summary.lower(), 1.0),
        (" ".join(str(moment.get("text", "")) for moment in moments).lower(), 0.75),
    ]
    results = []
    for theme, keywords in THEME_RULES.items():
        score = 0.0
        matched = set()
        for text, weight in fields:
            for keyword in keywords:
                if keyword in text:
                    score += weight
                    matched.add(keyword)
        if score:
            results.append((theme, score, sorted(matched)))
    return sorted(results, key=lambda item: (-item[1], item[0]))


def sentiment_mix(sentences: list[dict[str, Any]]) -> dict[str, float | int]:
    counts = Counter(str(item.get("sentimentType", "neutral")).lower() for item in sentences)
    total = max(sum(counts.values()), 1)
    return {
        "utterance_count": sum(counts.values()),
        "positive_utterance_pct": round(100 * counts["positive"] / total, 1),
        "negative_utterance_pct": round(100 * counts["negative"] / total, 1),
        "neutral_utterance_pct": round(100 * counts["neutral"] / total, 1),
    }


def owner_from_action_item(item: str) -> str:
    if ":" not in item:
        return "Unassigned"
    candidate = item.split(":", 1)[0].strip()
    return candidate if 1 < len(candidate.split()) <= 4 else "Unassigned"


def build_meeting_record(folder: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    info = read_json(folder / "meeting-info.json")
    summary = read_json(folder / "summary.json")
    transcript = read_json(folder / "transcript.json").get("data", [])
    call_type, rule = classify_call_type(info.get("title", ""), info.get("allEmails", []))
    themes = score_themes_weighted(
        info.get("title", ""),
        summary.get("summary", ""),
        summary.get("topics", []),
        summary.get("keyMoments", []),
    )
    primary_theme = themes[0][0] if themes else "Other"
    secondary_theme = themes[1][0] if len(themes) > 1 else ""
    primary_evidence = ", ".join(themes[0][2]) if themes else "No dictionary match"
    sentiment = sentiment_mix(transcript)
    moments = summary.get("keyMoments", [])
    moment_counts = Counter(moment.get("type", "unknown") for moment in moments)
    score = float(summary.get("sentimentScore", 3.0))
    risk_raw = max(0.0, (3.0 - score) * 2.0)
    risk_raw += sum(RISK_MOMENT_WEIGHTS.get(moment.get("type", ""), 0.0) for moment in moments)
    risk_score = round(min(10.0, max(0.0, risk_raw)), 1)
    domains = external_domains(info.get("allEmails", []))
    start = datetime.fromisoformat(info["startTime"].replace("Z", "+00:00"))
    record = {
        "meeting_id": info.get("meetingId", folder.name),
        "date": start.date().isoformat(),
        "title": info.get("title", ""),
        "call_type": call_type,
        "call_type_rule": rule,
        "customer_domain": ";".join(domains),
        "duration_minutes": round(float(info.get("duration", 0.0)), 1),
        "participant_count": len(info.get("allEmails", [])),
        "primary_theme": primary_theme,
        "secondary_theme": secondary_theme,
        "theme_evidence": primary_evidence,
        "source_topics": "; ".join(summary.get("topics", [])),
        "overall_sentiment": summary.get("overallSentiment", "unknown"),
        "sentiment_score": score,
        **sentiment,
        "action_item_count": len(summary.get("actionItems", [])),
        "churn_signal_count": moment_counts["churn_signal"],
        "feature_gap_count": moment_counts["feature_gap"],
        "technical_issue_count": moment_counts["technical_issue"],
        "concern_count": moment_counts["concern"],
        "praise_count": moment_counts["praise"],
        "positive_pivot_count": moment_counts["positive_pivot"],
        "risk_score": risk_score,
        "summary": summary.get("summary", ""),
        "example_excerpt": next((m.get("text", "") for m in moments if m.get("text")), ""),
    }
    actions = []
    for item in summary.get("actionItems", []):
        actions.append({
            "meeting_id": record["meeting_id"],
            "date": record["date"],
            "call_type": call_type,
            "primary_theme": primary_theme,
            "customer_domain": record["customer_domain"],
            "owner": owner_from_action_item(item),
            "action_item": item,
        })
    return record, actions


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows and not fieldnames:
        return
    names = fieldnames or list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=names)
        writer.writeheader()
        writer.writerows(rows)


def mean(values: Iterable[float]) -> float:
    values = list(values)
    return sum(values) / len(values) if values else 0.0


def summarize(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_theme: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_account: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        by_type[row["call_type"]].append(row)
        by_theme[row["primary_theme"]].append(row)
        for domain in filter(None, row["customer_domain"].split(";")):
            by_account[domain].append(row)

    call_rows = []
    for call_type, rows in sorted(by_type.items()):
        call_rows.append({
            "call_type": call_type,
            "meeting_count": len(rows),
            "avg_sentiment_score": round(mean(r["sentiment_score"] for r in rows), 2),
            "avg_negative_utterance_pct": round(mean(r["negative_utterance_pct"] for r in rows), 1),
            "churn_signals": sum(r["churn_signal_count"] for r in rows),
            "feature_gaps": sum(r["feature_gap_count"] for r in rows),
            "avg_risk_score": round(mean(r["risk_score"] for r in rows), 2),
        })

    theme_rows = []
    for theme, rows in sorted(by_theme.items(), key=lambda item: (-len(item[1]), item[0])):
        example = sorted(rows, key=lambda r: (-r["risk_score"], r["title"]))[0]
        theme_rows.append({
            "theme": theme,
            "meeting_count": len(rows),
            "avg_sentiment_score": round(mean(r["sentiment_score"] for r in rows), 2),
            "avg_risk_score": round(mean(r["risk_score"] for r in rows), 2),
            "call_types": "; ".join(f"{k}:{v}" for k, v in sorted(Counter(r["call_type"] for r in rows).items())),
            "example_meeting_id": example["meeting_id"],
            "example_title": example["title"],
            "example_excerpt": example["example_excerpt"],
        })

    account_rows = []
    for domain, rows in by_account.items():
        account_rows.append({
            "customer_domain": domain,
            "meeting_count": len(rows),
            "avg_sentiment_score": round(mean(r["sentiment_score"] for r in rows), 2),
            "max_risk_score": max(r["risk_score"] for r in rows),
            "churn_signals": sum(r["churn_signal_count"] for r in rows),
            "technical_issues": sum(r["technical_issue_count"] for r in rows),
            "feature_gaps": sum(r["feature_gap_count"] for r in rows),
            "latest_date": max(r["date"] for r in rows),
            "top_theme": Counter(r["primary_theme"] for r in rows).most_common(1)[0][0],
        })
    account_rows.sort(key=lambda r: (-r["max_risk_score"], -r["churn_signals"], r["avg_sentiment_score"]))
    return call_rows, theme_rows, account_rows


def write_insights(path: Path, records: list[dict[str, Any]], call_rows: list[dict[str, Any]], theme_rows: list[dict[str, Any]], account_rows: list[dict[str, Any]], actions: list[dict[str, Any]]) -> None:
    worst_type = min(call_rows, key=lambda r: r["avg_sentiment_score"])
    strongest_type = max(call_rows, key=lambda r: r["avg_sentiment_score"])
    top_theme = max(theme_rows, key=lambda r: r["meeting_count"])
    riskiest_theme = max((r for r in theme_rows if r["meeting_count"] >= 3), key=lambda r: r["avg_risk_score"])
    high_risk_accounts = [r for r in account_rows if r["max_risk_score"] >= 6.0]
    owner_counts = Counter(row["owner"] for row in actions)
    top_owners = owner_counts.most_common(5)
    negative_internal = [r for r in records if r["call_type"] == "Internal" and r["sentiment_score"] < 3]
    lines = [
        "# Transcript Intelligence findings",
        "",
        "## Executive findings",
        "",
        f"- The dataset contains **{len(records)} meetings** and **{sum(r['utterance_count'] for r in records):,} utterances**. The call mix is " + ", ".join(f"{r['call_type'].lower()} {r['meeting_count']}" for r in call_rows) + ".",
        f"- **{worst_type['call_type']} calls carry the weakest sentiment** at {worst_type['avg_sentiment_score']:.2f}/5, compared with {strongest_type['avg_sentiment_score']:.2f}/5 for {strongest_type['call_type'].lower()} calls. Their negative utterance share is {worst_type['avg_negative_utterance_pct']:.1f}%.",
        f"- **{top_theme['theme']} is the largest theme** with {top_theme['meeting_count']} meetings. **{riskiest_theme['theme']} has the highest average risk** among themes with at least three meetings ({riskiest_theme['avg_risk_score']:.2f}/10).",
        f"- **{len(high_risk_accounts)} customer accounts reached a risk score of 6 or higher**. The highest-priority account is {account_rows[0]['customer_domain']} with {account_rows[0]['churn_signals']} churn signal(s) and a maximum risk score of {account_rows[0]['max_risk_score']:.1f}/10.",
        f"- Internal calls contain {len(negative_internal)} meetings below 3/5 sentiment. This gives leaders a leading indicator of delivery pressure before it appears in customer conversations.",
        "",
        "## Recommended product views",
        "",
        "1. **Account risk timeline.** Combine sentiment, churn signals, recurring technical issues, and unresolved feature gaps by customer. Customer success leaders can triage accounts before renewal discussions.",
        "2. **Incident propagation map.** Link internal incident calls to support escalations and later renewal concerns by theme and date. Engineering and support leaders can see how operational failures spread into commercial risk.",
        "3. **Commitment tracker.** Extract action owners and due-date language, then flag repeated or overdue commitments. Product and engineering leaders can distinguish recurring discussion from completed follow-through.",
        "4. **Voice-of-customer backlog.** Rank feature gaps by account risk, frequency, and affected segment. Product managers can prioritize requests with both product and revenue context.",
        "",
        "## Action ownership",
        "",
        f"The source summaries contain **{len(actions)} action items**. The five most frequent named owners are " + ", ".join(f"{name} ({count})" for name, count in top_owners) + ". This concentration can identify overloaded coordinators, but due dates and completion status would be needed before treating it as a workload measure.",
        "",
        "## Method and limitations",
        "",
        "The pipeline uses participant domains and title patterns for call type, a curated keyword taxonomy for themes, and the supplied sentence-level and meeting-level sentiment labels. This is easy to audit and works offline. It does not claim causal relationships. The source data appears synthetic and covers only about three months, so trends should be treated as directional. A production version should add human-reviewed evaluation sets, multi-label model calibration, due-date extraction, and monitoring for taxonomy drift.",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_charts(out_dir: Path, call_rows: list[dict[str, Any]], theme_rows: list[dict[str, Any]], records: list[dict[str, Any]], account_rows: list[dict[str, Any]]) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not available; skipping PNG charts")
        return
    out_dir.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.family": "DejaVu Sans", "axes.spines.top": False, "axes.spines.right": False})
    colors = {"Support": "#E45756", "External": "#4C78A8", "Internal": "#72B7B2"}

    fig, ax = plt.subplots(figsize=(8, 4.5))
    labels = [r["call_type"] for r in call_rows]
    values = [r["avg_sentiment_score"] for r in call_rows]
    bars = ax.bar(labels, values, color=[colors[label] for label in labels], width=0.58)
    ax.set_ylim(0, 5)
    ax.set_ylabel("Average meeting sentiment (1-5)")
    ax.set_title("Sentiment differs sharply by call type", loc="left", fontweight="bold")
    ax.bar_label(bars, fmt="%.2f", padding=3)
    fig.tight_layout()
    fig.savefig(out_dir / "sentiment_by_call_type.png", dpi=180, transparent=False)
    plt.close(fig)

    top = theme_rows[:8]
    fig, ax = plt.subplots(figsize=(9, 5.3))
    names = [r["theme"] for r in reversed(top)]
    counts = [r["meeting_count"] for r in reversed(top)]
    bars = ax.barh(names, counts, color="#4C78A8")
    ax.set_xlabel("Meetings")
    ax.set_title("Primary themes across 100 meetings", loc="left", fontweight="bold")
    ax.bar_label(bars, padding=3)
    fig.tight_layout()
    fig.savefig(out_dir / "theme_frequency.png", dpi=180, transparent=False)
    plt.close(fig)

    monthly: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for row in records:
        monthly[row["date"][:7]][row["call_type"]].append(row["sentiment_score"])
    months = sorted(monthly)
    fig, ax = plt.subplots(figsize=(9, 4.8))
    for call_type in ("Support", "External", "Internal"):
        vals = [mean(monthly[m].get(call_type, [])) or math.nan for m in months]
        ax.plot(months, vals, marker="o", linewidth=2.5, label=call_type, color=colors[call_type])
    ax.set_ylim(1, 5)
    ax.set_ylabel("Average sentiment (1-5)")
    ax.set_title("Support sentiment remains the weakest across the period", loc="left", fontweight="bold")
    ax.legend(frameon=False, ncol=3)
    fig.tight_layout()
    fig.savefig(out_dir / "sentiment_trend.png", dpi=180, transparent=False)
    plt.close(fig)

    top_accounts = account_rows[:10]
    fig, ax = plt.subplots(figsize=(9, 5.2))
    names = [r["customer_domain"].split(".")[0].replace("-", " ").title() for r in reversed(top_accounts)]
    risk = [r["max_risk_score"] for r in reversed(top_accounts)]
    bars = ax.barh(names, risk, color="#E45756")
    ax.set_xlim(0, 10)
    ax.set_xlabel("Maximum meeting risk score (0-10)")
    ax.set_title("Accounts requiring review", loc="left", fontweight="bold")
    ax.bar_label(bars, fmt="%.1f", padding=3)
    fig.tight_layout()
    fig.savefig(out_dir / "account_risk.png", dpi=180, transparent=False)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path(__file__).resolve().parents[1] / "data" / "raw")
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parents[1] / "analysis")
    args = parser.parse_args()
    folders = sorted(path for path in args.data_dir.iterdir() if path.is_dir() and (path / "meeting-info.json").exists())
    if not folders:
        raise SystemExit(f"No meeting folders found in {args.data_dir}")
    records: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []
    for folder in folders:
        record, action_rows = build_meeting_record(folder)
        records.append(record)
        actions.extend(action_rows)
    records.sort(key=lambda row: (row["date"], row["meeting_id"]))
    call_rows, theme_rows, account_rows = summarize(records)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "meeting_analysis.csv", records)
    write_csv(args.output_dir / "call_type_summary.csv", call_rows)
    write_csv(args.output_dir / "theme_summary.csv", theme_rows)
    write_csv(args.output_dir / "account_risk.csv", account_rows)
    write_csv(args.output_dir / "action_items.csv", actions)
    write_insights(args.output_dir / "insights.md", records, call_rows, theme_rows, account_rows, actions)
    write_charts(args.output_dir / "charts", call_rows, theme_rows, records, account_rows)
    print(json.dumps({
        "meetings": len(records),
        "actions": len(actions),
        "call_types": {r["call_type"]: r["meeting_count"] for r in call_rows},
        "output_dir": str(args.output_dir),
    }, indent=2))


if __name__ == "__main__":
    main()
