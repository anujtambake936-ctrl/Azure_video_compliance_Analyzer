import logging
import os
import uuid
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

load_dotenv(override=True)

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, HttpUrl

from backend.src.api.telemetry import setup_telemetry
setup_telemetry()

from backend.src.graph.workflow import app as compliance_graph

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("api-server")

app = FastAPI(
    title="Video Compliance Analyzer",
    version="0.1.0",
    description="Audits YouTube videos against indexed compliance guidance.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request / Response models ────────────────────────────────────────────────

class AuditRequest(BaseModel):
    video_url: str


class ComplianceFinding(BaseModel):
    category: str
    severity: str
    description: str


class AuditResponse(BaseModel):
    session_id: str
    video_id: str
    video_url: str
    status: str
    risk_score: int = 0
    video_summary: str = ""
    final_report: str = ""
    compliance_results: List[ComplianceFinding] = Field(default_factory=list)
    retrieved_rules: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)


# ── Helper ───────────────────────────────────────────────────────────────────

def _missing_env_vars() -> List[str]:
    required = [
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_API_KEY",
        "AZURE_OPENAI_CHAT_DEPLOYMENT",
        "AZURE_OPENAI_EMBEDDING_DEPLOYMENT",
        "AZURE_SEARCH_ENDPOINT",
        "AZURE_SEARCH_API_KEY",
        "AZURE_SEARCH_INDEX_NAME",
        "AZURE_VI_NAME",
        "AZURE_VI_LOCATION",
        "AZURE_VI_ACCOUNT_ID",
        "AZURE_SUBSCRIPTION_ID",
        "AZURE_RESOURCE_GROUP",
    ]
    return [name for name in required if not os.getenv(name)]


# ── Endpoints ────────────────────────────────────────────────────────────────

@app.get("/health")
def health() -> Dict[str, Any]:
    missing = _missing_env_vars()
    return {
        "status": "ok" if not missing else "degraded",
        "missing_environment_variables": missing,
    }


@app.post("/audit", response_model=AuditResponse)
async def audit_video(request: AuditRequest):
    session_id = str(uuid.uuid4())
    video_id_short = f"vid_{session_id[:8]}"

    logger.info(f"Received audit request: {request.video_url} (Session: {session_id})")

    initial_inputs = {
        "video_url": str(request.video_url),
        "video_id": video_id_short,
        "compliance_results": [],
        "errors": [],
    }

    try:
        final_state = compliance_graph.invoke(initial_inputs)

        return AuditResponse(
            session_id=session_id,
            video_id=video_id_short,
            video_url=str(request.video_url),
            status=final_state.get("final_status", "UNKNOWN"),
            risk_score=final_state.get("risk_score", 0),
            video_summary=final_state.get("video_summary", ""),
            final_report=final_state.get("final_report", ""),
            compliance_results=final_state.get("compliance_results", []),
            retrieved_rules=final_state.get("retrieved_rules", []),
            errors=final_state.get("errors", []),
        )

    except Exception as e:
        logger.exception("Audit graph failed")
        raise HTTPException(
            status_code=500,
            detail=f"Audit workflow failed: {str(e)}",
        )
