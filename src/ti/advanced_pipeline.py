"""Build the retrieval index, unsupervised topic validation, and agent runtime artifacts."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import silhouette_score

from .agents import TranscriptAgentSystem
from .corpus import load_corpus, read_json
from .governance import AccessContext
from .retrieval import HybridRetriever


def cluster_meetings(data_dir: Path) -> tuple[list[dict], dict]:
    meetings = []
    for folder in sorted(data_dir.iterdir()):
        if not folder.is_dir() or not (folder / "summary.json").exists():
            continue
        info = read_json(folder / "meeting-info.json")
        summary = read_json(folder / "summary.json")
        text = " ".join([info.get("title", ""), summary.get("summary", ""), " ".join(summary.get("topics", []))])
        meetings.append({"meeting_id": info["meetingId"], "title": info.get("title", ""), "text": text})
    vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), min_df=2, max_features=5000, sublinear_tf=True)
    matrix = vectorizer.fit_transform(row["text"] for row in meetings)
    candidates = []
    for k in range(5, 11):
        model = KMeans(n_clusters=k, random_state=42, n_init=20)
        labels = model.fit_predict(matrix)
        candidates.append((silhouette_score(matrix, labels, metric="cosine"), k, model, labels))
    best_score, best_k, model, labels = max(candidates, key=lambda row: row[0])
    terms = vectorizer.get_feature_names_out()
    top_terms = {
        cluster: [terms[index] for index in model.cluster_centers_[cluster].argsort()[-8:][::-1]]
        for cluster in range(best_k)
    }
    rows = []
    for meeting, label in zip(meetings, labels):
        rows.append({
            "meeting_id": meeting["meeting_id"],
            "title": meeting["title"],
            "cluster": int(label),
            "cluster_top_terms": "; ".join(top_terms[int(label)]),
        })
    metrics = {
        "selected_clusters": best_k,
        "silhouette_score": round(float(best_score), 4),
        "candidate_scores": {str(k): round(float(score), 4) for score, k, _, _ in candidates},
        "top_terms": top_terms,
    }
    return rows, metrics


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    root = Path(__file__).resolve().parents[2]
    parser.add_argument("--data-dir", type=Path, default=root / "data" / "raw")
    parser.add_argument("--analysis-dir", type=Path, default=root / "analysis" / "advanced")
    parser.add_argument("--runtime-dir", type=Path, default=root / "runtime")
    args = parser.parse_args()
    args.analysis_dir.mkdir(parents=True, exist_ok=True)
    args.runtime_dir.mkdir(parents=True, exist_ok=True)

    chunks = load_corpus(args.data_dir)
    retriever = HybridRetriever(chunks)
    clusters, cluster_metrics = cluster_meetings(args.data_dir)
    write_csv(args.analysis_dir / "cluster_assignments.csv", clusters)

    agent = TranscriptAgentSystem(args.data_dir, retriever, args.runtime_dir)
    admin = AccessContext(subject="offline-evaluation", role="admin")
    sample_ids = [path.name for path in sorted(args.data_dir.iterdir()) if path.is_dir()][:12]
    results = [agent.analyze(meeting_id, admin) for meeting_id in sample_ids]
    reports = [state.data["report"] for state in results]
    (args.analysis_dir / "sample_agent_reports.json").write_text(json.dumps(reports, indent=2), encoding="utf-8")
    metrics = {
        "meeting_count": len({chunk.meeting_id for chunk in chunks}),
        "evidence_chunk_count": len(chunks),
        "retrieval_dimensions": int(retriever.semantic.shape[1]),
        "cluster_validation": cluster_metrics,
        "sample_agent_runs": len(results),
        "sample_human_review_rate": round(sum(state.review_required for state in results) / max(len(results), 1), 3),
        "audit_chain_valid": agent.audit.verify()[0],
        "audit_entries": agent.audit.verify()[1],
    }
    (args.analysis_dir / "advanced_metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
