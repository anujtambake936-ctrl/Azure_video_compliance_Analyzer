import operator
from typing import Annotated, Any, Dict, List, Optional, TypedDict


# Define the schema for a single compliance issue or violation
class ComplianceIssue(TypedDict):
    category: str
    description: str  # Specific detail of violation
    timestamp: Optional[str]
    severity: str  # e.g., "CRITICAL", "WARNING", "INFO"
    


# DEFINE THE GLOBAL GRAPH STATE
# This schema defines the data passed between nodes in the agentic workflow
class VideoAuditState(TypedDict):
    """Defines the data schema for the LangGraph execution context.

    Main Container: Holds all information about the video audit right from
    the initial input URL to the final compliance report.
    """

    # Input parameters
    video_url: str
    video_id: str

    # Ingestion & Extraction outputs
    local_file_path: Optional[str]
    video_metadata: Dict[str, Any]
    transcript: Optional[str]
    ocr_text: List[str]
   
    # Analysis outputs (Appended across graph steps)
    compliance_results: Annotated[List[ComplianceIssue], operator.add]

    # RAG retrieval output (rule chunks surfaced from the knowledge base)
    retrieved_rules: List[str]

    # Final deliverables
    final_status: str  # "PASS" or "FAIL"
    final_report: str  # Markdown summary report
    video_summary: str
    risk_score: int

    # System observability & Error tracking
    errors: Annotated[List[str], operator.add]
