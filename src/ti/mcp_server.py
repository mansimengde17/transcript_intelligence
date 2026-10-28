"""MCP server exposing governed transcript tools through the official Python SDK.

Install the optional agent dependencies, then run:
    python -m ti.mcp_server
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from .agents import TranscriptAgentSystem
from .corpus import load_corpus
from .governance import AccessContext
from .retrieval import HybridRetriever


ROOT = Path(__file__).resolve().parents[2]


@lru_cache(maxsize=1)
def _services() -> tuple[HybridRetriever, TranscriptAgentSystem]:
    chunks = load_corpus(ROOT / "data" / "raw")
    retriever = HybridRetriever(chunks)
    agent = TranscriptAgentSystem(ROOT / "data" / "raw", retriever, ROOT / "runtime")
    return retriever, agent


def build_server():
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise RuntimeError("Install requirements-agentic.txt to run the MCP server") from exc

    server = FastMCP("Transcript Intelligence")

    @server.tool()
    def search_transcripts(query: str, top_k: int = 5, account_domain: str = "") -> list[dict[str, Any]]:
        """Search redacted transcript evidence with hybrid BM25, TF-IDF, and LSA retrieval."""
        retriever, _ = _services()
        context = AccessContext(subject="mcp-local", role="analyst")
        return retriever.search(query, context, top_k=max(1, min(top_k, 10)), account_domain=account_domain)

    @server.tool()
    def analyze_meeting(meeting_id: str) -> dict[str, Any]:
        """Run the governed agent graph and return evidence-linked analysis."""
        _, agent = _services()
        context = AccessContext(subject="mcp-local", role="analyst")
        state = agent.analyze(meeting_id, context)
        return {
            "run_id": state.run_id,
            "status": state.status,
            "report": state.data.get("report"),
            "decisions": state.decisions,
            "policy_flags": state.policy_flags,
        }

    @server.tool()
    def submit_human_feedback(run_id: str, verdict: str, correction: dict[str, Any]) -> dict[str, str]:
        """Persist an analyst verdict and corrected fields for future evaluation sets."""
        _, agent = _services()
        feedback_id = agent.checkpoints.submit_feedback(run_id, "mcp-local", verdict, correction)
        agent.audit.append("human_feedback", "mcp-local", {"run_id": run_id, "feedback_id": feedback_id, "verdict": verdict})
        return {"feedback_id": feedback_id}

    return server


def main() -> None:
    build_server().run()


if __name__ == "__main__":
    main()
