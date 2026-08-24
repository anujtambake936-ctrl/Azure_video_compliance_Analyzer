"""Fast version of nodes.py using Azure Speech instead of Azure Video Indexer.

This bypasses the 3-10 minute Video Indexer processing time.
"""
import json
import logging
import os
import re
import uuid
from typing import Any, Dict

from langchain_openai import AzureChatOpenAI, AzureOpenAIEmbeddings
from langchain_community.vectorstores import AzureSearch
from langchain_core.messages import HumanMessage, SystemMessage

# Import state schema
from backend.src.graph.state import VideoAuditState

# Import services
from backend.src.services.video_indexer import VideoIndexerService, is_youtube_url
from backend.src.services.azure_speech_transcriber import AzureSpeechTranscriber
from backend.src.services.video_cache import get_cached_result, save_to_cache

logger = logging.getLogger("nodes-fast")
logging.basicConfig(level=logging.INFO)


# ============================================================================
# NODE 1: Fast Indexer (Azure Speech)
# ============================================================================
def index_video_node_fast(state: VideoAuditState) -> Dict[str, Any]:
    """Fast video processing using Azure Speech instead of Video Indexer."""
    video_url = state.get("video_url")
    video_id_input = state.get("video_id", "vid_demo")
    logger.info(f"--- [Node: Fast Indexer] Processing: {video_url} ---")

    if not isinstance(video_url, str) or not is_youtube_url(video_url):
        return {
            "errors": ["Please provide a valid YouTube URL."],
            "final_status": "FAIL",
            "transcript": "",
            "ocr_text": [],
        }

    # Check cache first
    cached = get_cached_result(video_url, mode="fast")
    if cached:
        logger.info("--- [Node: Fast Indexer] Using cached result ---")
        return cached

    local_filename = f"temp_audit_video_{uuid.uuid4().hex}.mp4"
    local_path = local_filename

    try:
        # Download video (same as before)
        vi_service = VideoIndexerService()
        local_path = vi_service.download_youtube_video(
            video_url, output_path=local_filename
        )

        transcriber = AzureSpeechTranscriber()
        result = transcriber.process_video(local_path)

        # Add video_id to result
        result["video_id"] = video_id_input

        # Do not cache empty recognition results so transient failures can retry.
        if result.get("transcript", "").strip():
            save_to_cache(video_url, result, mode="fast")

        logger.info("--- [Node: Fast Indexer] Complete ---")
        return result

    except Exception as e:
        logger.error(f"Fast indexer failed: {e}")
        return {
            "errors": [str(e)],
            "final_status": "FAIL",
            "transcript": "",
            "ocr_text": [],
        }
    finally:
        if os.path.exists(local_path):
            os.remove(local_path)


# ============================================================================
# NODE 2: Compliance Auditor (same as before)
# ============================================================================
def audit_content_node(state: VideoAuditState) -> Dict[str, Any]:
    """Performs RAG to audit brand video content using Azure OpenAI LLM."""

    logger.info("--- [Node: Auditor] Querying Knowledge Base & LLM ---")

    transcript = state.get("transcript", "")

    if not transcript:
        logger.warning("No transcript available. Skipping audit.")
        return {
            "final_status": "FAIL",
            "final_report": "Audit skipped because video processing failed."
        }

    llm = AzureChatOpenAI(
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        azure_deployment=os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT"),
        api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
    )

    embeddings = AzureOpenAIEmbeddings(
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        azure_deployment=os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT"),
        api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
    )

    vector_store = AzureSearch(
        azure_search_endpoint=os.getenv("AZURE_SEARCH_ENDPOINT"),
        azure_search_key=os.getenv("AZURE_SEARCH_API_KEY"),
        index_name=os.getenv("AZURE_SEARCH_INDEX_NAME"),
        embedding_function=embeddings.embed_query,
    )

    # RAG Retrieval
    ocr_text = state.get("ocr_text", [])
    query_text = f"{transcript[:6000]} {' '.join(ocr_text)[:3000]}"

    docs = vector_store.similarity_search(query_text, k=3)

    if not docs:
        logger.warning(
            "--- [Node: Auditor] WARNING: No documents retrieved from Azure Search. "
            "Run backend/scripts/index_documents.py first."
        )

    retrieved_rules = "\n\n".join([doc.page_content for doc in docs])

    # Prompt
    system_prompt = f"""
You are a senior video compliance auditor.
OFFICIAL REGULATORY RULES:
{retrieved_rules}

Instructions:
1. Analyze the Transcript and OCR text below
2. Identify any violations of the rules
3. Return strictly JSON in the following format
JSON FORMAT SPECIFICATION:
{{
  "video_summary": "<2-4 sentence factual summary of what the video says/shows>",
  "risk_score": <integer from 0 to 100 where 0 is no risk and 100 is severe compliance risk>,
  "compliance_results": [
    {{
      "severity": "CRITICAL",
      "category": "<Category Name, e.g., Claim Validation, Endorsement Disclosure>",
      "description": "<Detailed explanation of the specific violation found and why it matters>",
    }}
  ],
  "status": "FAIL",
  "final_report": "summary of findings"
}}
If no violations are found, set "status" to "PASS" and compliance_results to []
"""

    user_message = f"""
VIDEO METADATA: {json.dumps(state.get('video_metadata', {}))}
TRANSCRIPT: {transcript}
ON_SCREEN TEXT (OCR): {ocr_text}
"""

    # LLM Call
    try:
        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_message),
        ])

        content = response.content
        if "```" in content:
            content = re.search(r"```(?:json)?(.*?)```", content, re.DOTALL).group(1)

        audit_data = json.loads(content.strip())

        return {
            "compliance_results": audit_data.get("compliance_results", []),
            "final_status": audit_data.get("status", "FAIL"),
            "final_report": audit_data.get("final_report", "No report generated"),
            "video_summary": audit_data.get("video_summary", ""),
            "risk_score": audit_data.get("risk_score", 0),
            "retrieved_rules": [doc.page_content for doc in docs],
        }

    except Exception as e:
        logger.error(f"System Error in Auditor Node: {str(e)}")
        logger.error(f"Raw LLM response: {response.content if 'response' in locals() else 'None'}")

        return {
            "errors": [str(e)],
            "final_status": "FAIL",
            "retrieved_rules": [doc.page_content for doc in docs],
        }
