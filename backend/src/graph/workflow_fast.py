"""Fast workflow using Azure Speech instead of Azure Video Indexer.

Expected latency: 20-60 seconds (vs 5-10 minutes with Azure VI).
"""
from langgraph.graph import StateGraph, END

from backend.src.graph.state import VideoAuditState
from backend.src.graph.nodes_fast import index_video_node_fast, audit_content_node


def create_fast_graph():
    """Constructs the fast LangGraph workflow using Azure Speech."""
    workflow = StateGraph(VideoAuditState)

    # Add nodes
    workflow.add_node("indexer", index_video_node_fast)
    workflow.add_node("auditor", audit_content_node)

    # Define edges
    workflow.set_entry_point("indexer")
    workflow.add_edge("indexer", "auditor")
    workflow.add_edge("auditor", END)

    # Compile
    app = workflow.compile()
    return app


app = create_fast_graph()
