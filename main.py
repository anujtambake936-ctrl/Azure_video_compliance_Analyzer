"""Main execution entry point for compliance analyzer.

This file is the "control center" that starts and manages the entire compliance
audit workflow. It:
1. Sets up the audit request payload.
2. Runs the LangGraph AI workflow.
3. Displays the final compliance report.
"""

import uuid
import json
import logging
from pprint import pprint


from dotenv import load_dotenv

load_dotenv(override=True)

# Import compiled workflow graph
from backend.src.graph.workflow import app

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger("compliance-analyzer-runner")


def run_cli_simulation():
    """Simulates a video compliance audit request.

    - Generates a unique session ID
    - Prepares the video URL and metadata
    - Runs it through the AI workflow
    - Displays the compliance results
    """
    # ======== STEP 1: GENERATE SESSION ID ========
    session_id = str(uuid.uuid4())
    logger.info(f"Starting Audit Session: {session_id}")

    # ======== STEP 2: DEFINE INITIAL STATE ========
    initial_inputs = {
        # Target YouTube video URL
        "video_url": "https://youtu.be/dT7S75eYhcQ?si=iTxndT1i-On1zQSD",
        # Shortened video ID for tracking
        "video_id": f"vid_{session_id[:8]}",
        # Empty list to store compliance violations
        "compliance_results": [],
        # Empty list for system error tracking
        "errors": [],
    }

    # ======== DISPLAY SECTION: INPUT SUMMARY ========
    print("\n--- 1. INITIALIZING WORKFLOW ---")
    print(f"Input Payload: {json.dumps(initial_inputs, indent=2)}")

    # ======== STEP 3: EXECUTE GRAPH ========
    try:
        # app.invoke() triggers the LangGraph workflow
        # Flow: START -> Indexer -> Auditor -> END
        final_state = app.invoke(initial_inputs)

        # ======== DISPLAY SECTION: EXECUTION COMPLETE ========
        print("\n--- 2. WORKFLOW EXECUTION COMPLETE ---")

        # ======== STEP 4: OUTPUT RESULTS ========
        print("\n=== COMPLIANCE AUDIT REPORT ===")
        print(f"Video ID:    {final_state.get('video_id', 'N/A')}")
        
        # Support either 'final_status' or 'status' key from state
        status = final_state.get("final_status") or final_state.get("status", "UNKNOWN")
        print(f"Status:      {status}")
        print(f"Risk Score:  {final_state.get('risk_score', 0)}/100")

        print("\n[ VIDEO SUMMARY ]")
        print(final_state.get("video_summary", "No summary available."))

        # ======== VIOLATIONS SECTION ========
        print("\n[ VIOLATIONS DETECTED ]")
        results = final_state.get("compliance_results", [])

        if results:
            for issue in results:
                print(f"- [{issue.get('severity')}] [{issue.get('category')}] : [{issue.get('description')}]")
                      
        else:
            print("No violations found.")

        # ======== FINAL SUMMARY ========
        print("\n[ FINAL SUMMARY ]")
        print(final_state.get("final_report"))

    except Exception as e:
        logger.error(f"Workflow execution failed: {str(e)}")
        raise e


if __name__ == "__main__":
    run_cli_simulation()
