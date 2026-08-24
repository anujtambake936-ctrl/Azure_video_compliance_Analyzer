import logging
import os
import uuid
from typing import Any, Dict, List, Literal, Optional
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv

load_dotenv(override=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("api-server")

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, HttpUrl

from backend.src.api.telemetry import setup_telemetry
setup_telemetry()

from backend.src.graph.workflow import app as compliance_graph
from backend.src.graph.workflow_fast import app as compliance_graph_fast
from backend.src.services.report_store import (
    delete_report,
    get_report,
    list_reports,
    save_report,
)

# Choose which workflow to use based on env var
USE_FAST_MODE = os.getenv("USE_FAST_TRANSCRIPTION", "false").lower() == "true"
DEFAULT_MODE = "fast" if USE_FAST_MODE else "full"

if USE_FAST_MODE:
    logger.info("Fast mode enabled: Using Azure Speech transcription")
else:
    logger.info("Full mode: Using Azure Video Indexer (~5-10min)")

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

# In-memory job store (use Redis/PostgreSQL in production)
job_store: Dict[str, Dict[str, Any]] = {}

# Thread pool for background jobs
executor = ThreadPoolExecutor(max_workers=4)


# ── Request / Response models ────────────────────────────────────────────────

class AuditRequest(BaseModel):
    video_url: HttpUrl
    processing_mode: Optional[Literal["fast", "full"]] = None


class ComplianceFinding(BaseModel):
    category: str
    severity: str
    description: str


class AuditJobResponse(BaseModel):
    """Immediate response when audit is submitted"""
    job_id: str
    status: str  # "pending", "processing", "completed", "failed"
    message: str
    processing_mode: str


class AuditStatusResponse(BaseModel):
    """Response when polling for job status"""
    job_id: str
    status: str
    video_url: str
    video_id: Optional[str] = None
    created_at: str
    completed_at: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    processing_mode: str = "full"


class AuditResponse(BaseModel):
    """Final audit result"""
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
    ]
    if USE_FAST_MODE:
        required.extend([
            "AZURE_SPEECH_ENDPOINT",
            "AZURE_SPEECH_KEY",
            "AZURE_SPEECH_REGION",
        ])
    else:
        required.extend([
            "AZURE_VI_NAME",
            "AZURE_VI_LOCATION",
            "AZURE_VI_ACCOUNT_ID",
            "AZURE_SUBSCRIPTION_ID",
            "AZURE_RESOURCE_GROUP",
        ])
    return [name for name in required if not os.getenv(name)]


def run_audit_sync(
    job_id: str, video_url: str, video_id_short: str, processing_mode: str
):
    """Background job that runs the audit workflow"""
    try:
        job_store[job_id]["status"] = "processing"
        logger.info(f"[Job {job_id}] Starting audit for {video_url}")

        initial_inputs = {
            "video_url": video_url,
            "video_id": video_id_short,
            "compliance_results": [],
            "errors": [],
        }

        graph = compliance_graph_fast if processing_mode == "fast" else compliance_graph
        final_state = graph.invoke(initial_inputs)

        result = {
            "session_id": job_id,
            "video_id": video_id_short,
            "video_url": video_url,
            "processing_mode": processing_mode,
            "created_at": job_store[job_id]["created_at"],
            "completed_at": datetime.utcnow().isoformat(),
            "status": final_state.get("final_status", "UNKNOWN"),
            "risk_score": final_state.get("risk_score", 0),
            "video_summary": final_state.get("video_summary", ""),
            "final_report": final_state.get("final_report", ""),
            "compliance_results": final_state.get("compliance_results", []),
            "retrieved_rules": final_state.get("retrieved_rules", []),
            "errors": final_state.get("errors", []),
        }

        job_store[job_id]["status"] = "completed"
        job_store[job_id]["result"] = result
        job_store[job_id]["completed_at"] = result["completed_at"]
        save_report(job_id, result)

        logger.info(f"[Job {job_id}] Completed successfully")

    except Exception as e:
        logger.exception(f"[Job {job_id}] Audit failed")
        job_store[job_id]["status"] = "failed"
        job_store[job_id]["error"] = str(e)
        job_store[job_id]["completed_at"] = datetime.utcnow().isoformat()


# ── Endpoints ────────────────────────────────────────────────────────────────

@app.get("/health")
def health() -> Dict[str, Any]:
    missing = _missing_env_vars()
    return {
        "status": "ok" if not missing else "degraded",
        "missing_environment_variables": missing,
        "active_jobs": len([j for j in job_store.values() if j["status"] in ["pending", "processing"]]),
    }


@app.post("/audit", response_model=AuditJobResponse, status_code=202)
async def submit_audit(request: AuditRequest, background_tasks: BackgroundTasks):
    """Submit a video for audit. Returns immediately with a job ID."""
    job_id = str(uuid.uuid4())
    video_id_short = f"vid_{job_id[:8]}"
    processing_mode = request.processing_mode or DEFAULT_MODE

    logger.info(f"[Job {job_id}] Received audit request: {request.video_url}")

    # Store job metadata
    job_store[job_id] = {
        "job_id": job_id,
        "status": "pending",
        "video_url": str(request.video_url),
        "video_id": video_id_short,
        "created_at": datetime.utcnow().isoformat(),
        "completed_at": None,
        "result": None,
        "error": None,
        "processing_mode": processing_mode,
    }

    # Schedule background job
    background_tasks.add_task(
        lambda: executor.submit(
            run_audit_sync,
            job_id,
            str(request.video_url),
            video_id_short,
            processing_mode,
        )
    )

    return AuditJobResponse(
        job_id=job_id,
        status="pending",
        message="Audit job submitted. Use GET /audit/{job_id} to check status.",
        processing_mode=processing_mode,
    )


@app.get("/reports")
def get_saved_reports() -> List[Dict[str, Any]]:
    """Return completed reports persisted on this service instance."""
    return list_reports()


@app.get("/audit/{job_id}", response_model=AuditStatusResponse)
def get_audit_status(job_id: str):
    """Poll for audit job status and result."""
    if job_id not in job_store:
        raise HTTPException(status_code=404, detail="Job not found")

    job = job_store[job_id]
    result = job.get("result") or get_report(job_id)

    return AuditStatusResponse(
        job_id=job["job_id"],
        status=job["status"],
        video_url=job["video_url"],
        video_id=job.get("video_id"),
        created_at=job["created_at"],
        completed_at=job.get("completed_at"),
        result=result,
        error=job.get("error"),
        processing_mode=job.get("processing_mode", DEFAULT_MODE),
    )


@app.delete("/audit/{job_id}")
def delete_audit_job(job_id: str):
    """Delete a completed or failed job from the store."""
    if job_id not in job_store:
        raise HTTPException(status_code=404, detail="Job not found")

    job = job_store[job_id]
    if job["status"] in ["pending", "processing"]:
        raise HTTPException(status_code=400, detail="Cannot delete a running job")

    del job_store[job_id]
    delete_report(job_id)
    return {"message": "Job deleted", "job_id": job_id}
