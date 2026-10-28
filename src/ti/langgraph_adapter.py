"""Optional LangGraph adapter for the framework-neutral agent nodes.

The core workflow remains independently testable. Install requirements-agentic.txt to
compile the same nodes with LangGraph durable execution and a production checkpointer.
"""

from __future__ import annotations

from typing import Any, TypedDict

from .agents import AgentState, TranscriptAgentSystem


class WorkflowState(TypedDict):
    agent_state: AgentState


def build_langgraph(system: TranscriptAgentSystem, checkpointer: Any = None):
    try:
        from langgraph.graph import END, START, StateGraph
    except ImportError as exc:
        raise RuntimeError("Install requirements-agentic.txt to use the LangGraph adapter") from exc

    builder = StateGraph(WorkflowState)

    def wrap(node_name: str):
        def execute(payload: WorkflowState) -> WorkflowState:
            state = payload["agent_state"]
            next_node = system.graph.nodes[node_name](state)
            state.current_node = next_node
            return {"agent_state": state}

        return execute

    for node_name in ("ingest", "policy", "classify", "retrieve", "risk", "synthesize"):
        builder.add_node(node_name, wrap(node_name))
    builder.add_edge(START, "ingest")
    builder.add_edge("ingest", "policy")
    builder.add_edge("policy", "classify")
    builder.add_edge("classify", "retrieve")
    builder.add_edge("retrieve", "risk")
    builder.add_edge("risk", "synthesize")
    builder.add_edge("synthesize", END)
    return builder.compile(checkpointer=checkpointer)
