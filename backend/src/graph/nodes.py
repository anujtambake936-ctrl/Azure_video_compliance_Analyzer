import json
import logging
import os
import re
import uuid
from typing import Any, Dict, List

from langchain_openai import AzureChatOpenAI, AzureOpenAIEmbeddings
from langchain_community.vectorstores import AzureSearch
from langchain_core.messages import HumanMessage, SystemMessage

# Import state schema
from backend.src.graph.state import ComplianceIssue, VideoAuditState

# Import service
from backend.src.services.video_indexer import VideoIndexerService

logger = logging.getLogger("nodes")
logging.basicConfig(level=logging.INFO)




# ============================================================================
# NODE 1: Indexer
# ============================================================================
def index_video_node(state: VideoAuditState) -> Dict[str, Any]:
    """Downloads YouTube video from URL, uploads to Azure Video Indexer, and extracts insights."""
    video_url = state.get("video_url")
    video_id_input = state.get("video_id", "vid_demo")
    logger.info(f"--- [Node: Indexer] Processing: {video_url} ---")
    local_filename = f"temp_audit_video_{uuid.uuid4().hex}.mp4"

    try:
        vi_service = VideoIndexerService()

        # Download video via yt-dlp
        if "youtube.com" in video_url or "youtu.be" in video_url:
            local_path = vi_service.download_youtube_video(
                video_url, output_path=local_filename
            )
        else:
            raise ValueError(
                "Please provide a valid YouTube URL for this test."
            )

        # Upload to Azure Video Indexer
        azure_video_id = vi_service.upload_video(
            local_path, video_name=video_id_input
        )
        logger.info(f"Upload Success. Azure ID: {azure_video_id}")

        # Wait for processing & extract data
        raw_insights = vi_service.wait_for_processing(azure_video_id)
        clean_data = vi_service.extract_data(raw_insights)

        logger.info("--- [Node: Indexer] Extraction Complete ---")
        return clean_data

    except Exception as e:
        logger.error(f"Video Indexer failed: {e}")
        return {
            "errors": [str(e)],
            "final_status": "FAIL",
            "transcript": "",
            "transcript_segments": [],
            "ocr_text": [],
           
        }

# ============================================================================
# NODE 2: Compliance Auditor
# ============================================================================
def audit_content_node(state: VideoAuditState) -> Dict[str, Any]:
    """Performs RAG to audit brand video content using Azure OpenAI LLM."""

    logger.info("--- [Node: Auditor] Querying Knowledge Base & LLM ---")

    transcript = state.get("transcript", "")
    
    if not transcript:
        logger.warning("No transcript or OCR text available. Skipping audit.")
        return {
            "final_status": "FAIL",
            "final_report": (
                "Audit skipped because video processing failed."
            )
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


        # ------------------------------------------------------------
        # 2. RAG Retrieval
        # ------------------------------------------------------------
    ocr_text=state.get("ocr_text",[])
    query_text = f"{transcript[:6000]} {' '.join(ocr_text)[:3000]}"

    docs = vector_store.similarity_search(
            query_text,
            k=3
        )

    if not docs:
        logger.warning(
            "--- [Node: Auditor] WARNING: No documents retrieved from Azure Search. "
            "The knowledge base may be empty. Run backend/scripts/index_documents.py first."
        )

    retrieved_rules = "\n\n".join(
           [doc.page_content for doc in docs]
        )


    

    # ------------------------------------------------------------
     # 3. Prompt
    # ------------------------------------------------------------

    system_prompt = f"""
   You are a senior  video compliance auditor.
OFFICIAL REGULATORY RULES:
{retrieved_rules}

Instructions:
1. Analyze the Transcript and OCT text below 
2. Identify any vilations of the rules
3.Return strictly JSON in the following format
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
 if no violations are found ,set "status" to  "PASS" and compliance results to []

"""


    user_message = f"""
        VIDEO METADATA:{json.dumps(state.get('video_metadata', {}))}
        TRANSCRIPT:{transcript}
        ON_SCREEN TEXT(OCR):{ocr_text}
"""


        # ------------------------------------------------------------
        # 4. LLM Call
        # ------------------------------------------------------------
    try:
        response = llm.invoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_message),
            ]
        )
        content=response.content
        if "```" in content:
            content=re.search(r"```(?:json)?(.*?)```",content,re.DOTALL).group(1)

        audit_data=json.loads(content.strip())
        return{
            "compliance_results": audit_data.get("compliance_results",[]),
            "final_status": audit_data.get("status","FAIL"),
            "final_report":audit_data.get("final_report","No report generated"),
            "video_summary": audit_data.get("video_summary", ""),
            "risk_score": audit_data.get("risk_score", 0),
            "retrieved_rules": [doc.page_content for doc in docs],
        }

    except Exception as e:

        logger.error(
            f"System Error in Auditor Node: {str(e)}"
        )
        logger.error(f"Raw LLM response:{response.content if 'response' in locals() else 'None'}")


        return {
            "errors": [str(e)],
            "final_status": "FAIL",
            "retrieved_rules": [doc.page_content for doc in docs],
        }
