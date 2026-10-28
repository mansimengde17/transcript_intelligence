"""Gated multi-agent workflow with durable checkpoints and human review routing."""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from .corpus import read_json
from .governance import AccessContext, AuditLedger, Authorizer, LineageRecord, Redactor
from .observability import TraceRecorder
from .retrieval import HybridRetriever


THEME_RULES = {
    "Reliability & incidents": ("outage", "incident", "reliability", "latency", "failure", "data gap", "alert", "root cause"),
    "Compliance & reporting": ("compliance", "soc 2", "hipaa", "pci", "iso 27001", "audit", "report"),
    "Identity & access": ("identity", "sso", "saml", "scim", "ldap", "mfa", "provisioning", "login"),
    "Commercial & renewal": ("renewal", "contract", "churn", "retention", "pricing", "expansion", "upsell"),
    "Backup & recovery": ("backup", "restore", "recovery", "rpo", "rto"),
    "Product adoption & launch": ("adoption", "launch", "early access", "demo", "deployment", "onboarding"),
    "Integrations & APIs": ("integration", "connector", "api", "siem", "logvault", "webhook"),
    "Billing & pricing": ("billing", "invoice", "overage", "charge", "license", "pricing", "dispute"),
    "Competitive intelligence": ("competitive", "competitor", "vendor comparison", "win/loss"),
    "Product planning & delivery": ("roadmap", "sprint", "planning", "standup", "feature request", "technical debt"),
}


@dataclass
class AgentState:
    run_id: str
    meeting_id: str
    actor: str
    status: str = "running"
    current_node: str = "ingest"
    data: dict[str, Any] = field(default_factory=dict)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    decisions: list[dict[str, Any]] = field(default_factory=list)
    policy_flags: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    review_required: bool = False


class CheckpointStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS checkpoints (
                    run_id TEXT NOT NULL,
                    step INTEGER NOT NULL,
                    node TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (run_id, step)
                );
                CREATE TABLE IF NOT EXISTS feedback (
                    feedback_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    verdict TEXT NOT NULL,
                    correction_json TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def save(self, state: AgentState, step: int) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO checkpoints(run_id, step, node, state_json) VALUES (?, ?, ?, ?)",
                (state.run_id, step, state.current_node, json.dumps(asdict(state), sort_keys=True)),
            )

    def submit_feedback(self, run_id: str, actor: str, verdict: str, correction: dict[str, Any]) -> str:
        feedback_id = uuid.uuid4().hex
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO feedback(feedback_id, run_id, actor, verdict, correction_json) VALUES (?, ?, ?, ?, ?)",
                (feedback_id, run_id, actor, verdict, json.dumps(correction, sort_keys=True)),
            )
        return feedback_id


Node = Callable[[AgentState], str]


class AgentGraph:
    """Small state graph with retries, trace spans, and checkpointing.

    The graph is intentionally framework-neutral. A LangGraph adapter can wrap the same node
    functions in production, while tests exercise the core behavior without network services.
    """

    def __init__(self, nodes: dict[str, Node], checkpoint_store: CheckpointStore, tracer: TraceRecorder, max_steps: int = 20):
        self.nodes = nodes
        self.checkpoints = checkpoint_store
        self.tracer = tracer
        self.max_steps = max_steps

    def run(self, state: AgentState) -> AgentState:
        for step in range(self.max_steps):
            if state.current_node in {"complete", "human_review", "failed"}:
                break
            node_name = state.current_node
            node = self.nodes[node_name]
            try:
                with self.tracer.span(f"agent.{node_name}", trace_id=state.run_id, meeting_id=state.meeting_id) as attributes:
                    started = time.perf_counter()
                    next_node = node(state)
                    attributes["next_node"] = next_node
                    attributes["node_latency_ms"] = round((time.perf_counter() - started) * 1000, 3)
                # Save progress after each completed step so its decisions can be inspected.
                state.current_node = next_node
                self.checkpoints.save(state, step)
            except Exception as exc:
                # Send unexpected failures for review rather than continuing with partial results.
                state.errors.append(f"{node_name}: {type(exc).__name__}: {exc}")
                state.review_required = True
                state.current_node = "human_review"
                self.checkpoints.save(state, step)
                break
        else:
            state.errors.append("Graph exceeded maximum step count")
            state.current_node = "failed"
        state.status = "awaiting_review" if state.current_node == "human_review" else state.current_node
        return state


class TranscriptAgentSystem:
    def __init__(self, data_dir: Path, retriever: HybridRetriever, runtime_dir: Path):
        self.data_dir = data_dir
        self.retriever = retriever
        self.redactor = Redactor()
        self.authorizer = Authorizer()
        self.audit = AuditLedger(runtime_dir / "audit.jsonl")
        self.tracer = TraceRecorder(runtime_dir / "traces.jsonl")
        self.checkpoints = CheckpointStore(runtime_dir / "memory.sqlite3")
        self.graph = AgentGraph(
            {
                "ingest": self._ingest,
                "policy": self._policy,
                "classify": self._classify,
                "retrieve": self._retrieve,
                "risk": self._risk,
                "synthesize": self._synthesize,
            },
            self.checkpoints,
            self.tracer,
        )
        self._context: AccessContext | None = None

    def analyze(self, meeting_id: str, context: AccessContext) -> AgentState:
        self.authorizer.require(context, "analyze")
        self._context = context
        state = AgentState(run_id=uuid.uuid4().hex, meeting_id=meeting_id, actor=context.subject)
        result = self.graph.run(state)
        self.audit.append(
            "agent_run",
            context.subject,
            {"run_id": result.run_id, "meeting_id": meeting_id, "status": result.status, "review_required": result.review_required},
        )
        return result

    def _meeting_folder(self, meeting_id: str) -> Path:
        folder = self.data_dir / meeting_id
        if not folder.exists():
            raise FileNotFoundError(f"Unknown meeting {meeting_id}")
        return folder

    def _ingest(self, state: AgentState) -> str:
        folder = self._meeting_folder(state.meeting_id)
        info = read_json(folder / "meeting-info.json")
        summary = read_json(folder / "summary.json")
        transcript = read_json(folder / "transcript.json").get("data", [])
        state.data.update({"info": info, "summary": summary, "transcript": transcript})
        return "policy"

    def _policy(self, state: AgentState) -> str:
        transcript_text = " ".join(str(row.get("sentence", "")) for row in state.data["transcript"])
        redacted, pii_counts = self.redactor.redact(transcript_text)
        injection = self.redactor.prompt_injection_signals(transcript_text)
        state.data["redacted_transcript"] = redacted
        state.data["pii_counts"] = pii_counts
        if injection:
            state.policy_flags.extend(f"prompt_injection:{pattern}" for pattern in injection)
            state.review_required = True
        return "classify"

    def _classify(self, state: AgentState) -> str:
        info = state.data["info"]
        summary = state.data["summary"]
        emails = info.get("allEmails", [])
        external = [email for email in emails if not email.lower().endswith("@aegiscloud.com")]
        title_l = info.get("title", "").lower()
        call_type = "Internal" if not external else ("Support" if any(h in title_l for h in ("support case", "urgent:", "escalation:", "failures", "issue", "bug")) else "External")
        fields = [
            (title_l, 8.0),
            (" ".join(summary.get("topics", [])).lower(), 2.0),
            (str(summary.get("summary", "")).lower(), 1.0),
            (" ".join(str(moment.get("text", "")) for moment in summary.get("keyMoments", [])).lower(), 0.75),
        ]
        scored = []
        for theme, keywords in THEME_RULES.items():
            matches = set()
            weighted_score = 0.0
            for text, weight in fields:
                for keyword in keywords:
                    if keyword in text:
                        matches.add(keyword)
                        weighted_score += weight
            if weighted_score:
                scored.append((theme, weighted_score, sorted(matches)))
        scored.sort(key=lambda row: (-row[1], row[0]))
        primary = scored[0][0] if scored else "Other"
        confidence = round(scored[0][1] / max(sum(row[1] for row in scored), 1), 3) if scored else 0.0
        state.data.update({"call_type": call_type, "primary_theme": primary, "theme_confidence": confidence, "theme_matches": scored[:3]})
        state.decisions.append({"agent": "classification", "decision": call_type, "basis": "participant domains and title pattern"})
        state.decisions.append({"agent": "theme", "decision": primary, "confidence": confidence, "basis": scored[:3]})
        if confidence < 0.34:
            state.review_required = True
        return "retrieve"

    def _retrieve(self, state: AgentState) -> str:
        assert self._context is not None
        info = state.data["info"]
        summary = state.data["summary"]
        query = f"{info.get('title', '')} {summary.get('summary', '')}"
        state.evidence = self.retriever.search(query, self._context, top_k=4)
        if not state.evidence or state.evidence[0]["score"] < 0.2:
            state.review_required = True
        return "risk"

    def _risk(self, state: AgentState) -> str:
        summary = state.data["summary"]
        score = float(summary.get("sentimentScore", 3.0))
        counts: dict[str, int] = {}
        for moment in summary.get("keyMoments", []):
            kind = moment.get("type", "unknown")
            counts[kind] = counts.get(kind, 0) + 1
        raw = max(0.0, (3.0 - score) * 2.0)
        raw += 3.0 * counts.get("churn_signal", 0)
        raw += 1.2 * counts.get("concern", 0)
        raw += counts.get("technical_issue", 0)
        raw += 0.8 * counts.get("feature_gap", 0)
        raw -= 0.6 * counts.get("positive_pivot", 0)
        raw -= 0.8 * counts.get("praise", 0)
        risk = round(min(10.0, max(0.0, raw)), 1)
        state.data["risk_score"] = risk
        state.data["risk_factors"] = counts
        state.decisions.append({"agent": "risk", "decision": risk, "basis": counts})
        if risk >= 8.0:
            state.review_required = True
        return "synthesize"

    def _synthesize(self, state: AgentState) -> str:
        evidence_ids = [row["chunk_id"] for row in state.evidence]
        report = {
            "meeting_id": state.meeting_id,
            "call_type": state.data["call_type"],
            "primary_theme": state.data["primary_theme"],
            "risk_score": state.data["risk_score"],
            "evidence_chunk_ids": evidence_ids,
            "review_required": state.review_required,
            "policy_flags": state.policy_flags,
        }
        lineage = LineageRecord.create(
            artifact_id=f"analysis:{state.meeting_id}:{state.run_id}",
            sources={"meeting_info": state.data["info"], "summary": state.data["summary"]},
            transform="agent_graph_analysis",
            version="2.0.0",
            output=report,
        )
        state.data["report"] = report
        state.data["lineage"] = asdict(lineage)
        return "human_review" if state.review_required else "complete"
